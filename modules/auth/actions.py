import re
from typing import Any
from democrai.sdk.decorators import action, event_slot, validate
from democrai.sdk.auth import get_user_permissions, public
from democrai.sdk.auth import SessionService
from democrai.sdk.auth import SessionKey
from democrai.sdk.system import to_optional_int
from democrai.sdk.system import current_request_profiler
from pydantic import BaseModel, Field, field_validator

_LOG_SANITIZE_RE = re.compile(r"[\r\n\x1b].*", re.DOTALL)


def _sanitize_for_log(value: str) -> str:
    return _LOG_SANITIZE_RE.sub("[sanitized]", value)


class LoginFormPayload(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username


class LoginSubmitPayload(BaseModel):
    login_form: LoginFormPayload


def _toast_message(title: str, text: str, *, variant: str = "destructive") -> dict[str, Any]:
    return {
        "eventNotification": {
            "kind": "toast",
            "title": title.strip(),
            "text": text.strip(),
            "variant": variant.strip(),
        }
    }


def _respond_toast(module_sdk: Any, title: str, text: str, *, variant: str = "destructive") -> dict[str, Any]:
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([_toast_message(title, text, variant=variant)])
    )


@event_slot(
    "login.succeeded",
    params=["user_id", "role", "organization_id"],
    optional=True,
    description="Triggered after a user successfully authenticates.",
)
def register_login_succeeded_event():
    return None


@action("register")
async def register(username: str, password: str, role: str = "user", module_sdk=None):
    """Registers a new user (Stub for now, should call core service)."""
    # In a real scenario, this would call sdk.models.users.create or similar
    return {
        "ok": False,
        "type": "error",
        "error": "not_implemented",
        "details": "Registration is not yet implemented in core.",
    }


@action("login_submit")
@validate(LoginSubmitPayload, strip_extra=True)
@public
async def login(ctx: dict, session: dict, module_sdk):
    """Authenticates a user using Core SDK."""
    credentials = ctx["login_form"]
    username = credentials["username"]
    password = credentials["password"]

    module_sdk.system.log(f"Login attempt for user: {_sanitize_for_log(username)}")
    profiler = current_request_profiler()

    if profiler is not None:
        with profiler.span("auth.action.login"):
            login_result = module_sdk.auth.login(username, password)
    else:
        login_result = module_sdk.auth.login(username, password)

    if not bool(login_result.get("ok")):
        error = str(login_result.get("error") or "")
        if error == "rate_limited":
            return _respond_toast(
                module_sdk,
                "Login blocked",
                "Too many attempts. Please try again later.",
            )
        return _respond_toast(
            module_sdk,
            "Login failed",
            str(login_result.get("details") or "Invalid credentials."),
        )

    user_info = dict(login_result.get("user_info") or {})
    token_payload = dict(login_result.get("token_payload") or {})
    token = str(login_result.get("token") or "")
    user_id = to_optional_int(login_result.get("user_id"))
    role = str(token_payload.get("role") or "")
    organization_id = to_optional_int(token_payload.get("organization_id"))
    resolved_access_level = to_optional_int(token_payload.get("access_level"))
    language = (
        str(module_sdk.i18n.get_user_language(user_id) or "en").strip().lower()
        or "en"
    )
    module_sdk.system.log(f"User {_sanitize_for_log(username)} verified. Updating session...")
    session[SessionKey.USER] = {
        "username": str(user_info.get("username") or username),
        "id": user_id,
        "role": role,
        "access_level": resolved_access_level,
        "organization_id": organization_id,
        "avatar": "user",
        "language": language,
    }
    session[SessionKey.USER_LANGUAGE] = language
    session[SessionKey.CURRENT_PATH] = module_sdk.pages.get_post_login_redirect_path()

    if profiler is not None:
        with profiler.span("auth.action.emit_event"):
            await module_sdk.events.emit(
                "login.succeeded",
                payload={
                    "user_id": user_id,
                    "role": role,
                    "organization_id": organization_id,
                },
                session=session,
            )
    else:
        await module_sdk.events.emit(
            "login.succeeded",
            payload={
                "user_id": user_id,
                "role": role,
                "organization_id": organization_id,
            },
            session=session,
        )

    return module_sdk.effects.respond(
        module_sdk.effects.render(),
        module_sdk.effects.refresh_modules(),
        module_sdk.effects.set_jwt(token),
    )


@action("refresh_token")
async def refresh_token(session: dict, module_sdk):
    """Refreshes the JWT for the authenticated session user."""
    refreshed = module_sdk.auth.refresh_current_session_token()
    if not bool(refreshed.get("ok")):
        return refreshed

    token = refreshed["token"]
    return module_sdk.effects.respond(module_sdk.effects.set_jwt(token))


@action("go_login")
@public
async def go_login(session: dict, module_sdk):
    """
    Force a clean unauthenticated state and render the login page.
    Useful to recover from stale guest/user sessions.
    """
    language = str(session.get(SessionKey.USER_LANGUAGE) or "").strip().lower() or "en"
    session.clear()
    session[SessionKey.CURRENT_PATH] = module_sdk.pages.get_guest_path()
    session[SessionKey.USER] = SessionService.build_guest_session_user()
    session[SessionKey.USER_LANGUAGE] = language

    return module_sdk.effects.respond(
        module_sdk.effects.render(),
        module_sdk.effects.refresh_modules(),
        module_sdk.effects.set_jwt(""),
    )


@action("load_client_auth_context")
@public
async def load_client_auth_context(ctx: dict, session: dict, module_sdk):
    user = session.get("user") or {}
    user_id = to_optional_int(user.get("id"))

    role = "Guest"
    permissions: list[str] = []

    if user_id is not None:
        role = str(user.get("role") or "User")
        try:
            raw_permissions = get_user_permissions(user_id)
            if isinstance(raw_permissions, list):
                permissions = [
                    str(permission)
                    for permission in raw_permissions
                    if str(permission).strip()
                ]
        except Exception as exc:
            module_sdk.system.log(
                f"[auth] load_client_auth_context failed to resolve permissions: {exc}",
                "error",
            )
            return {
                "ok": False,
                "type": "error",
                "error": "permissions_unavailable",
                "details": "Unable to load user permissions.",
            }

    state_message = {
        "stateUpdate": {
            "scope": "global",
            "values": {
                "/auth/role": role,
                "/auth/permissions": sorted(set(permissions)),
                "/auth/permissions_loaded": True,
            },
        }
    }
    return module_sdk.effects.respond(module_sdk.effects.ui_messages([state_message]))


def _session_user_id(session: dict) -> int | None:
    user = session.get(SessionKey.USER) if isinstance(session, dict) else None
    if not isinstance(user, dict):
        return None
    return to_optional_int(user.get("id"))


def _form_values(ctx: dict[str, Any]) -> dict[str, Any]:
    values = ctx.get("values")
    if isinstance(values, dict):
        return dict(values)

    payload = ctx.get("data")
    if isinstance(payload, dict):
        return dict(payload)

    return {
        key: value
        for key, value in ctx.items()
        if key
        not in {
            "action",
            "form_id",
            "id",
            "route_params",
            "session",
            "surface_id",
            "user_id",
        }
    }


def _close_drawer_message() -> dict[str, Any]:
    return {"deleteSurface": {"surfaceId": "drawer"}}


@action("update_profile")
async def update_profile(ctx: dict, session: dict, module_sdk):
    user_id = _session_user_id(session)
    if user_id is None:
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.auth_required.title"),
            module_sdk.i18n.t("profile.toast.auth_required.text"),
        )

    values = _form_values(ctx)
    payload = {
        "username": str(values.get("username") or "").strip(),
        "email": str(values.get("email") or "").strip(),
    }
    if not payload["username"]:
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.update_error.title"),
            module_sdk.i18n.t("profile.toast.username_required"),
        )

    try:
        updated = module_sdk.models.users.update(user_id, payload)
    except ValueError as exc:
        error_text = str(exc).strip().lower()
        text_key = (
            "profile.toast.username_taken"
            if "already in use" in error_text
            else "profile.toast.update_error.text"
        )
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.update_error.title"),
            module_sdk.i18n.t(text_key),
        )
    except Exception as exc:
        module_sdk.system.log(f"[auth.profile] update_profile error: {exc}", "error")
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.update_error.title"),
            module_sdk.i18n.t("profile.toast.update_error.text"),
        )

    if updated is None:
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.update_error.title"),
            module_sdk.i18n.t("profile.toast.user_not_found"),
        )

    session_user = session.get(SessionKey.USER)
    if isinstance(session_user, dict):
        session_user["username"] = str(updated.get("username") or payload["username"])

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([_close_drawer_message()]),
        module_sdk.effects.notify(
            "toast",
            {
                "title": module_sdk.i18n.t("profile.toast.updated.title"),
                "text": module_sdk.i18n.t("profile.toast.updated.text"),
                "variant": "success",
            },
        ),
        module_sdk.effects.render(),
    )


@action("change_own_password")
async def change_own_password(ctx: dict, session: dict, module_sdk):
    user_id = _session_user_id(session)
    if user_id is None:
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.auth_required.title"),
            module_sdk.i18n.t("profile.toast.auth_required.text"),
        )

    values = _form_values(ctx)
    new_password = str(values.get("new_password") or "")
    confirm_password = str(values.get("confirm_password") or "")
    if not new_password or new_password != confirm_password:
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.password_error.title"),
            module_sdk.i18n.t("profile.toast.password_mismatch"),
        )

    try:
        updated = module_sdk.models.users.update(user_id, {"password": new_password})
    except Exception as exc:
        module_sdk.system.log(f"[auth.profile] change_own_password error: {exc}", "error")
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.password_error.title"),
            module_sdk.i18n.t("profile.toast.password_error.text"),
        )

    if updated is None:
        return _respond_toast(
            module_sdk,
            module_sdk.i18n.t("profile.toast.password_error.title"),
            module_sdk.i18n.t("profile.toast.user_not_found"),
        )

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([_close_drawer_message()]),
        module_sdk.effects.notify(
            "toast",
            {
                "title": module_sdk.i18n.t("profile.toast.password_updated.title"),
                "text": module_sdk.i18n.t("profile.toast.password_updated.text"),
                "variant": "success",
            },
        ),
        module_sdk.effects.render(),
    )
