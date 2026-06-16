import json

from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.application.observability.service import observability_service
from democrai.core.application.home import clear_post_login_path, resolve_guest_page_path
from democrai.core.application.session.service import SessionService
from democrai.core.application.session_keys import SessionKey
from democrai.core.application.auth.roles import (
    ACCESS_LEVEL_FULL,
    ACCESS_LEVEL_ORGANIZATION,
    ACCESS_LEVEL_USER,
)
from democrai.core.application.auth.action import public
from democrai.core.application.auth.module_access import is_module_locked_for_session
from democrai.core.application.services.media_uploads import can_access_media_upload
from democrai.core.infrastructure.database.media_uploads import (
    get_media_upload_by_file_id,
    get_media_upload_by_storage_path,
)
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.identity import to_required_int
from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.app import req_ctx

SUPPORTED_LANGUAGES: tuple[dict[str, str], ...] = (
    {"label": "EN", "value": "en"},
    {"label": "IT", "value": "it"},
    {"label": "ES", "value": "es"},
    {"label": "FR", "value": "fr"},
    {"label": "DE", "value": "de"},
    {"label": "ZH", "value": "zh"},
)
SUPPORTED_LANGUAGE_VALUES = {entry["value"] for entry in SUPPORTED_LANGUAGES}


def _first_payload_item(action_ctx: dict) -> dict:
    for value in action_ctx.values():
        if isinstance(value, dict):
            return value
    return {}


def _audio_upload_ref(action_ctx: dict) -> dict:
    payload = _first_payload_item(action_ctx)
    audio = payload.get("audio")
    if isinstance(audio, list) and audio and isinstance(audio[0], dict):
        return audio[0]
    if isinstance(audio, dict):
        return audio
    return {}


def _upload_storage_path(upload: dict) -> str:
    return str(upload.get("storage_path") or upload.get("path") or "").strip()


def _upload_file_id(upload: dict) -> str:
    return str(upload.get("file_id") or "").strip()


def _response_text(response) -> str:
    result = getattr(response, "result", response)
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    return str(getattr(result, "text", "") or "").strip()


def _require_media_upload_access(upload: dict) -> str:
    file_id = _upload_file_id(upload)
    storage_path = _upload_storage_path(upload)
    row = None
    if file_id:
        row = get_media_upload_by_file_id(file_id=file_id)
    if row is None and storage_path:
        row = get_media_upload_by_storage_path(storage_path=storage_path)
    if row is None:
        raise RuntimeError("media_upload_not_found")
    try:
        request_context = req_ctx()
    except LookupError as exc:
        raise RuntimeError("missing_request_context") from exc
    user_id = to_required_int(request_context.user, "user_id")
    if not can_access_media_upload(
        owner_user_id=row.owner_user_id,
        organization_id=row.organization_id,
        user_id=user_id,
        user_access_level=request_context.access_level,
        user_organization_id=request_context.organization_id,
    ):
        raise PermissionError("media_upload_access_denied")
    return row.storage_path or storage_path


def _build_inline_route_surface_messages(
    builder,
    surface_id: str,
    sdk,
    *,
    options: dict | None = None,
    unwrap_dialogs: bool = True,
) -> list[dict]:
    root_ids = [component.id for component in builder.get_roots() if component.id]

    if not root_ids:
        return [{"deleteSurface": {"surfaceId": surface_id}}]

    render_roots: list[str] = []
    component_index = {
        component.id: component
        for component in builder._components
    }
    for root_id in root_ids:
        component = component_index.get(root_id)
        root_data = component.to_dict() if component is not None else {}
        component_def = (
            root_data.get("component") if isinstance(root_data, dict) else {}
        )
        component_type = ""
        if isinstance(component_def, dict) and component_def:
            component_type = next(iter(component_def.keys()))
        if component_type != "Dialog" or not unwrap_dialogs:
            render_roots.append(root_id)
            continue
        children = root_data.get("children") if isinstance(root_data, dict) else {}
        explicit = children.get("explicitList") if isinstance(children, dict) else None
        if isinstance(explicit, list):
            extracted = [
                item
                for item in explicit
                if isinstance(item, str) and item
            ]
            if extracted:
                render_roots.extend(extracted)
                continue
        render_roots.append(root_id)

    if not render_roots:
        return [{"deleteSurface": {"surfaceId": surface_id}}]

    target_builder = builder
    target_roots = render_roots
    if len(target_roots) > 1:
        wrapper = builder.__class__()
        wrapper.merge(builder, components=True, replace=True)
        wrapper.add(sdk.ui.Column(f"{surface_id}_root", target_roots))
        target_builder = wrapper
        target_roots = [f"{surface_id}_root"]

    data_model = builder._data_model
    messages = list(target_builder.build_surface_update_payload(surface_id))
    if isinstance(data_model, dict) and data_model:
        messages.append(
            builder.__class__.build_data_model_update_payload(
                surface_id=surface_id,
                data=data_model,
            )
        )
    store_data = builder._store_data
    if isinstance(store_data, dict):
        for scope in ("page", "global"):
            values = store_data.get(scope)
            if isinstance(values, dict) and values:
                messages.append(
                    builder.__class__.build_state_update_payload(
                        values,
                        scope=scope,
                    )
                )
    begin_rendering = {"root": target_roots[0], "surfaceId": surface_id}
    if options:
        begin_rendering["options"] = options
    messages.append({"beginRendering": begin_rendering})
    return messages


def _surface_delete(sdk, surface_id: str) -> dict:
    return sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": surface_id}}])


def _parse_dim(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        dim = int(value)
    except (TypeError, ValueError):
        return None
    return dim if dim > 0 else None


def _parse_drawer_position(value) -> str:
    position = str(value or "right").strip().lower()
    if position not in {"right", "left", "top", "bottom"}:
        return "right"
    return position


def _parse_modal_width(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        width = int(value)
    except (TypeError, ValueError):
        return None
    return width if width > 0 else None


async def _resolve_route_builder(path: str, session: dict, sdk):
    current_path = session.get("current_path") or ""
    parent_params = {}
    if current_path:
        from democrai.sdk.ui import Router

        _, _, parent_params = Router.parse_path(current_path)
    return await sdk.ui.resolve_route(path, session, extra_params=parent_params)


@public
async def nav(action_ctx: dict, session: dict, sdk) -> dict:
    """Handles navigation updates in the session."""
    path = action_ctx.get("path")
    render_value = action_ctx.get("render", True)
    render_flag = normalize_bool(
        render_value,
        default=bool(render_value) if render_value is not None else True,
    )
    app_ctx().logger.debug(f"[Core] Navigating to: {path}")
    # Prevent stale overlays from reappearing after route changes.
    if render_flag:
        session[SessionKey.PENDING_MODAL] = None
        if normalize_bool(action_ctx.get("client_surface_reset"), default=False):
            session["_client_surface_reset"] = True
    effects = [sdk.effects.navigate(path, render=render_flag)]
    if render_flag:
        effects.append(
            sdk.effects.ui_messages(
                [
                    {"deleteSurface": {"surfaceId": "drawer"}},
                    {"deleteSurface": {"surfaceId": "modal"}},
                ]
            )
        )
    return sdk.effects.respond(*effects)


@public
async def navigate(action_ctx: dict, session: dict, sdk) -> dict:
    """Alias for nav — kept for backward compatibility."""
    return await nav(action_ctx, session, sdk)


async def render_route_surface(action_ctx: dict, session: dict, sdk) -> dict:
    path = str(action_ctx.get("path") or "").strip()
    surface_id = str(action_ctx.get("surface_id") or "").strip()
    if not path or not surface_id:
        raise ValueError("render_route_surface requires path and surface_id")
    builder = await _resolve_route_builder(path, session, sdk)
    active_aux = session.get("_active_aux_surfaces")
    if not isinstance(active_aux, list):
        active_aux = []
    if surface_id not in active_aux:
        active_aux.append(surface_id)
    session["_active_aux_surfaces"] = active_aux
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            _build_inline_route_surface_messages(builder, surface_id, sdk)
        )
    )


async def open_modal(action_ctx: dict, session: dict, sdk) -> dict:
    path = str(action_ctx.get("path") or "").strip()
    if not path:
        raise ValueError("open_modal requires path")

    title = action_ctx.get("title") or "Modal"
    width = _parse_modal_width(action_ctx.get("width"))
    builder = await _resolve_route_builder(path, session, sdk)
    root_ids = [component.id for component in builder.get_roots() if component.id]
    if not root_ids:
        return sdk.effects.respond(_surface_delete(sdk, "modal"))

    dialog = sdk.ui.Dialog("modal_root", title, root_ids)
    wrapper = builder.__class__()
    wrapper.merge(builder, components=True, replace=True)
    wrapper.add(dialog)

    options = {}
    if width is not None:
        options["width"] = width
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            _build_inline_route_surface_messages(
                wrapper,
                "modal",
                sdk,
                options=options,
                unwrap_dialogs=False,
            )
        )
    )


async def close_modal(action_ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(_surface_delete(sdk, "modal"))


async def open_drawer(action_ctx: dict, session: dict, sdk) -> dict:
    path = str(action_ctx.get("path") or "").strip()
    if not path:
        raise ValueError("open_drawer requires path")

    options = {"position": _parse_drawer_position(action_ctx.get("position"))}
    dim = _parse_dim(action_ctx.get("dim"))
    if dim is not None:
        options["dim"] = dim

    builder = await _resolve_route_builder(path, session, sdk)
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            _build_inline_route_surface_messages(
                builder,
                "drawer",
                sdk,
                options=options,
            )
        )
    )


async def close_drawer(action_ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(_surface_delete(sdk, "drawer"))


@public
async def logout(action_ctx: dict, session: dict, sdk) -> dict:
    """Clears user session and redirects to login."""
    current_path = session.get(SessionKey.CURRENT_PATH, "")
    current_user = to_optional_int(((session or {}).get("user") or {}).get("id"))
    current_language = _resolve_user_language(session, current_user)
    observability_service.record_auth_event(
        event_type="auth.logout",
        subject_user_id=current_user,
        success=True,
        metadata={"current_path": current_path},
    )
    session.clear()
    clear_post_login_path(session)
    session[SessionKey.CURRENT_PATH] = current_path
    session[SessionKey.USER] = SessionService.build_guest_session_user()
    session[SessionKey.USER_LANGUAGE] = current_language
    return sdk.effects.respond(
        sdk.effects.refresh_modules(),
        sdk.effects.render(),
        sdk.effects.set_jwt(""),
    )


async def refresh_token(action_ctx: dict, session: dict, sdk) -> dict:
    refreshed = sdk.auth.refresh_current_session_token()
    if not refreshed.get("ok"):
        return refreshed

    token_payload = refreshed["token_payload"]
    token = refreshed["token"]

    observability_service.record_auth_event(
        event_type="auth.token.refresh",
        subject_user_id=to_required_int(refreshed.get("user_id"), "user_id"),
        success=True,
        metadata={
            "role": token_payload["role"],
            "organization_id": token_payload["organization_id"],
            "access_level": token_payload["access_level"],
        },
    )
    return sdk.effects.respond(sdk.effects.set_jwt(token))


@public
async def load_client_auth_context(action_ctx: dict, session: dict, sdk) -> dict:
    from democrai.core.application.auth.service import get_user_permissions
    user = session.get("user") or {}
    user_id = to_optional_int(user.get("id"))

    role = "Guest"
    permissions: list[str] = []

    if user_id is not None:
        role = user.get("role") or "User"
        try:
            raw_permissions = get_user_permissions(user_id)
            if isinstance(raw_permissions, list):
                permissions = [
                    permission
                    for permission in raw_permissions
                    if permission
                ]
        except Exception as exc:
            app_ctx().logger.error(
                f"[Core] load_client_auth_context failed to resolve permissions: {exc}"
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
    return sdk.effects.respond(sdk.effects.ui_messages([state_message]))


async def get_notifications_count(action_ctx: dict, session: dict, sdk) -> dict:
    from democrai.core.application.notifications import notification_state_values

    state_values = notification_state_values(session)
    count = state_values.get("/core/notifications/pending_count") or 0
    messages = [
        {"notificationsUpdate": {"count": count}},
        {
            "stateUpdate": {
                "scope": "global",
                "values": state_values,
            }
        },
    ]
    return sdk.effects.respond(
        sdk.effects.ui_messages(messages)
    )


async def background_task_get(action_ctx: dict, session: dict, sdk) -> dict:
    task_id = str(action_ctx.get("task_id") or "").strip()
    if not task_id:
        return {
            "ok": False,
            "type": "error",
            "error": "invalid_request",
            "details": "task_id is required",
        }

    task = sdk.models.background_tasks.view(task_id)
    if task is None:
        return sdk.effects.respond()

    snapshot = {
        "taskId": task["id"],
        "label": task["label"],
        "module": task["module"],
        "status": task["status"],
        "progress": task["progress"],
        "updatedAt": task["updated_at"],
    }
    if task["checkpoint"] is not None:
        snapshot["checkpoint"] = json.loads(task["checkpoint"])
    if task["result"] is not None:
        snapshot["result"] = json.loads(task["result"])
    if task["error"] is not None:
        snapshot["error"] = task["error"]

    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "global",
                        "values": {f"/background_tasks/{task_id}": snapshot},
                    }
                }
            ]
        )
    )


async def list_notifications(action_ctx: dict, session: dict, sdk) -> dict:
    from democrai.core.application.notifications import list_notifications as _list

    return {
        "ok": True,
        "notifications": _list(session),
    }


async def approve_external_access(action_ctx: dict, session: dict, sdk) -> dict:
    from democrai.core.application.notifications import (
        apply_external_access_decision,
        notification_state_values,
    )

    try:
        apply_external_access_decision(action_ctx)
    except ValueError:
        return {
            "ok": False,
            "type": "error",
            "error": "invalid_request",
            "details": "Invalid external access request.",
        }
    except PermissionError as exc:
        return {
            "ok": False,
            "type": "error",
            "error": "permission_denied",
            "details": str(exc),
        }

    state_values = notification_state_values(session)
    count = state_values.get("/core/notifications/pending_count") or 0
    messages = [
        {"notificationsUpdate": {"count": count}},
        {
            "stateUpdate": {
                "scope": "global",
                "values": state_values,
            }
        },
    ]
    source_surface = str(action_ctx.get("_surface_id") or "").strip()
    view_path = state_values.get("/core/notifications/view_path") or ""
    if source_surface == "drawer" and view_path:
        try:
            builder = await _resolve_route_builder(view_path, session, sdk)
            messages.extend(
                _build_inline_route_surface_messages(
                    builder,
                    "drawer",
                    sdk,
                    options={"position": "right", "dim": 680},
                )
            )
        except Exception as exc:
            app_ctx().logger.error(
                f"[Core] Failed refreshing notification drawer: {exc}",
                "notifications",
            )
    return sdk.effects.respond(
        sdk.effects.ui_messages(messages)
    )


def _check_user_module_access(
    module: str,
    session: dict,
    user_id: int | None = None,
):
    return not is_module_locked_for_session(module, session, user_id=user_id)


def _build_active_condition(active_path: str):
    from democrai.core.platform.utils.conditions import Condition

    return Condition.OR(
        Condition(Condition.bound("/current_path"), "==", active_path),
        Condition(Condition.bound("/current_path"), "contains", f"{active_path}/"),
    )


def _legacy_sidebar_entries(module):
    label = module.label
    icon = module.icon
    action_name = "nav"
    action_ctx = {"path": f"/{module.name}/index"}
    guest_label = None
    guest_icon = None
    guest_action = None
    authenticated_label = None
    authenticated_icon = None
    authenticated_action = None

    if module.name == "auth":
        guest_action = {"name": "nav", "context": {"path": resolve_guest_page_path()}}
        authenticated_action = {"name": "logout", "context": {}}

    if getattr(module, "authenticated_label", None):
        authenticated_label = module.authenticated_label
    if getattr(module, "authenticated_icon", None):
        authenticated_icon = module.authenticated_icon

    return [
        {
            "id": module.name,
            "label": label,
            "icon": icon,
            "position": "bottom"
            if getattr(module, "sidebar_position", "top") == "bottom"
            else "top",
            "action": {"name": action_name, "context": action_ctx},
            "active_path": f"/{module.name}",
            "guest_label": guest_label,
            "guest_icon": guest_icon,
            "guest_action": guest_action,
            "authenticated_label": authenticated_label,
            "authenticated_icon": authenticated_icon,
            "authenticated_action": authenticated_action,
            "visible_for": "all",
            "priority": int(getattr(module, "priority", 0) or 0),
        }
    ]


def _resolve_sidebar_entries(module):
    declared = bool(getattr(module, "sidebar_init_declared", False))
    raw_entries = getattr(module, "sidebar_entries", [])
    if declared:
        if isinstance(raw_entries, list):
            return [entry for entry in raw_entries if isinstance(entry, dict)]
        return []
    return _legacy_sidebar_entries(module)


def _coerce_priority(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_language(language: str | None) -> str:
    value = str(language or "").strip().lower()
    if value in SUPPORTED_LANGUAGE_VALUES:
        return value
    return "en"


def _resolve_user_language(session: dict, user_id: int | None) -> str:
    stored_language = (session or {}).get(SessionKey.USER_LANGUAGE)
    if isinstance(stored_language, str) and stored_language.strip():
        return _normalize_language(stored_language)

    session_user = (session or {}).get(SessionKey.USER) or {}
    session_language = session_user.get("language")
    if isinstance(session_language, str) and session_language.strip():
        return _normalize_language(session_language)
    if bool(getattr(app_ctx(), "setup_mode", False)):
        return "en"

    from democrai.core.application.services.translation import get_translation_service

    service = get_translation_service()
    if user_id is not None:
        try:
            return _normalize_language(service.get_user_language(user_id))
        except Exception:
            app_ctx().logger.debug("[Core] Failed resolving language from user profile")
    return _normalize_language(getattr(service, "_default_language", "en"))


def _client_stubs() -> dict[str, list[dict[str, int | str]]]:
    return {
        "access_levels": [
            {"key": ACCESS_LEVEL_FULL, "value": "super"},
            {"key": ACCESS_LEVEL_ORGANIZATION, "value": "organization"},
            {"key": ACCESS_LEVEL_USER, "value": "user"},
        ]
    }


def _supported_languages() -> list[dict[str, str]]:
    return [dict(entry) for entry in SUPPORTED_LANGUAGES]


def _get_modules_list(session):
    user = "guest"
    user_id = None
    _user = session.get(SessionKey.USER, {})
    if session and _user:
        user = _user.get("username") or _user.get("name") or "guest"
        user_id = to_optional_int(_user.get("id"))

    from democrai.core.infrastructure.modules.manager import module_manager

    modules = module_manager.get_all_modules()

    top_modules: list[tuple[int, dict]] = []
    bottom_modules = []

    for p in modules:
        if not _check_user_module_access(p.name, session, user_id):
            continue

        for entry in _resolve_sidebar_entries(p):
            visible_for = entry.get("visible_for", "all")
            if visible_for == "guest" and user != "guest":
                continue
            if visible_for == "authenticated" and user == "guest":
                continue

            label = entry.get("label", p.label)
            icon = entry.get("icon")
            action = entry.get(
                "action", {"name": "nav", "context": {"path": f"/{p.name}/index"}}
            )

            if user == "guest":
                if entry.get("guest_label"):
                    label = entry["guest_label"]
                if entry.get("guest_icon"):
                    icon = entry["guest_icon"]
                if isinstance(entry.get("guest_action"), dict):
                    action = entry["guest_action"]
            else:
                if entry.get("authenticated_label"):
                    label = entry["authenticated_label"]
                if entry.get("authenticated_icon"):
                    icon = entry["authenticated_icon"]
                if isinstance(entry.get("authenticated_action"), dict):
                    action = entry["authenticated_action"]

            active_path = entry.get("active_path")
            if not isinstance(active_path, str) or not active_path:
                context = action.get("context") if isinstance(action, dict) else None
                path = context.get("path") if isinstance(context, dict) else None
                if isinstance(path, str) and path:
                    active_path = path
                else:
                    active_path = f"/{p.name}"

            p_data = {
                "id": entry.get("id", p.name),
                "label": label,
                "icon": icon,
                "action": action,
                "active_condition": _build_active_condition(active_path),
            }
            priority = _coerce_priority(
                entry.get("priority"), default=getattr(p, "priority", 0)
            )

            if entry.get("position") == "bottom":
                bottom_modules.append(p_data)
            else:
                top_modules.append((priority, p_data))

    top_modules.sort(key=lambda item: item[0], reverse=True)
    ordered_top_modules = [item for _, item in top_modules]

    app_ctx().logger.debug(
        f"[Core] Prepared {len(ordered_top_modules)} top and {len(bottom_modules)} bottom modules for global client state"
    )
    user_language = _resolve_user_language(session, user_id)
    return {
        "stateUpdate": {
            "scope": "global",
            "values": {
                "/system/modules/top": ordered_top_modules,
                "/system/modules/bottom": bottom_modules,
                "/core/user/language": user_language,
                "/core/supported_languages": _supported_languages(),
                "/stubs": _client_stubs(),
            },
        }
    }


@public
async def get_supported_languages(action_ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "global",
                        "values": {
                            "/core/supported_languages": _supported_languages(),
                        },
                    }
                }
            ]
        )
    )


@public
async def get_user_language(action_ctx: dict, session: dict, sdk) -> dict:
    user = session.get(SessionKey.USER) or {}
    user_id = to_optional_int(user.get("id"))
    language = _resolve_user_language(session, user_id)
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "global",
                        "values": {
                            "/core/user/language": language,
                        },
                    }
                }
            ]
        )
    )


@public
async def set_user_language(action_ctx: dict, session: dict, sdk) -> dict:
    raw_value = action_ctx.get("value")
    language = str(raw_value or "").strip().lower()
    if language not in SUPPORTED_LANGUAGE_VALUES:
        return {
            "ok": False,
            "type": "error",
            "error": "invalid_language",
            "details": f"Unsupported language '{language or raw_value}'.",
        }

    user = session.get(SessionKey.USER) or {}
    user_id = to_optional_int(user.get("id"))
    if user_id is not None:
        updated_user = sdk.models.users.update(user_id, {"language": language})
        if not isinstance(updated_user, dict):
            return {
                "ok": False,
                "type": "error",
                "error": "user_not_found",
                "details": "Unable to resolve current user.",
            }

    session.setdefault(SessionKey.USER, {})["language"] = language
    session[SessionKey.USER_LANGUAGE] = language
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "global",
                        "values": {
                            "/core/user/language": language,
                        },
                    }
                }
            ]
        ),
        sdk.effects.render(),
    )


@public
async def modules_list(action_ctx: dict, session: dict, sdk) -> dict:
    payload = _get_modules_list(session)
    return sdk.effects.respond(sdk.effects.ui_messages([payload]))


async def composer_transcribe_audio(action_ctx: dict, session: dict, sdk) -> dict:
    try:
        upload = _audio_upload_ref(action_ctx)
        storage_path = _require_media_upload_access(upload)
        provider_result = await sdk.ai.get_provider_for_objective(
            "stt",
            required_capabilities=["stt"],
        )
        if provider_result.get("status") != "ok" or not provider_result.get("provider"):
            message = str(provider_result.get("error") or "stt_provider_unavailable")
            return sdk.effects.respond(
                sdk.effects.notify("toast", {"level": "error", "message": message})
            )
        payload = _first_payload_item(action_ctx)
        language = str(payload.get("language") or "").strip()
        # The executing node loads the audio from the shared media storage:
        # the payload carries the path, never inline bytes.
        response = await provider_result["provider"].transcribe(
            media_storage_path=storage_path,
            language=language or None,
        )
        text = _response_text(response)
        target = str(payload.get("target") or payload.get("component_id") or "").strip()
        if not target:
            raise RuntimeError("composer_target_required")
        return sdk.effects.respond(
            sdk.effects.ui_property_update(target, "value", text),
        )
    except Exception as exc:
        return sdk.effects.respond(
            sdk.effects.notify("toast", {"level": "error", "message": str(exc)})
        )


async def orchestration_test(action_ctx: dict, session: dict, sdk) -> dict:
    """Example action to test GenAI orchestration."""
    from democrai.core.application.ai.orchestrator import model_orchestrator

    objective = action_ctx.get("objective", "chat")
    confirm = action_ctx.get("confirm", False)

    res = await model_orchestrator.get_provider_for_objective(
        objective, confirm_swap=confirm
    )

    # Pass through the orchestration result (status, etc)
    if res["status"] == "ok":
        session[
            "last_orchestration_result"
        ] = f"Model {res['provider'].model_name} ready!"
        return sdk.effects.respond(sdk.effects.render())

    return res  # Returns 'need_confirmation' status
