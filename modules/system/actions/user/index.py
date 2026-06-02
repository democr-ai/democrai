from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel, Field, field_validator, model_validator

from democrai.sdk.decorators import action, validate
from democrai.sdk.auth import permission_required

from modules.system.utils.actions.datatable import (
    datatable_payload,
    datatable_request,
    datatable_response,
)
from modules.system.utils.actions.user.index import (
    t,
)

TABLE_ID = "user_list_table"


class UserUpdateFormPayload(BaseModel):
    username: str = Field(min_length=1)
    email: str = ""
    role: str = Field(min_length=1)
    access_level: int

    @field_validator("username")
    @classmethod
    def _clean_username(cls, value: str) -> str:
        username = value.strip()
        if not username:
            raise ValueError("username is required")
        return username


class UserUpdatePayload(BaseModel):
    user_id: int
    user_update_form: UserUpdateFormPayload


class UserCreateFormPayload(UserUpdateFormPayload):
    password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.password != self.confirm_password:
            raise ValueError("password confirmation does not match")
        return self


class UserCreatePayload(BaseModel):
    user_create_form: UserCreateFormPayload


class UserChangePasswordFormPayload(BaseModel):
    new_password: str = Field(min_length=8)
    confirm_password: str = Field(min_length=8)

    @model_validator(mode="after")
    def _passwords_match(self):
        if self.new_password != self.confirm_password:
            raise ValueError("password confirmation does not match")
        return self


class UserChangePasswordPayload(BaseModel):
    user_id: int
    user_change_password_form: UserChangePasswordFormPayload


class RowItemPayload(BaseModel):
    id: int


class RowActionPayload(BaseModel):
    item: RowItemPayload


@action("list_user")
@permission_required(["system.user.list"])
async def list_user(ctx: Dict[str, Any], session: dict, module_sdk):
    page, page_size, filters = datatable_request(ctx)
    listing = module_sdk.models.users.list(
        page=page,
        page_size=page_size,
        filters=filters,
    )
    payload = datatable_payload(
        listing,
        page=page,
        page_size=page_size,
        filters=filters,
    )
    return datatable_response(module_sdk, TABLE_ID, payload)


@action("view_user")
@permission_required(["system.user.view"])
async def view_user(ctx: Dict[str, Any], session: dict, module_sdk):
    if ctx.get("op") == "open":
        item = ctx["item"]
        user_id = item["id"]
        return module_sdk.effects.respond(
            module_sdk.effects.navigate(f"/system/user/{user_id}/view", render=True)
        )

    if "user_id" not in ctx:
        return module_sdk.effects.respond()

    user_id = int(ctx["user_id"])
    data = module_sdk.models.users.view(user_id)
    if data is None:
        return {"ok": False, "error": "user_not_found"}
    return {"ok": True, "user": data}


@action("update_user")
@validate(UserUpdatePayload, strip_extra=True)
@permission_required(["system.user.update"])
async def update_user(ctx: Dict[str, Any], session: dict, module_sdk):
    user_id = ctx["user_id"]
    payload = ctx["user_update_form"]

    try:
        updated = module_sdk.models.users.update(user_id, payload)
        if updated is None:
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {
                        "title": t(module_sdk, "system.user.toast.update_error.title"),
                        "text": t(module_sdk, "system.user.toast.user_not_found"),
                        "variant": "destructive",
                    },
                )
            )

        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.updated.title"),
                    "text": t(
                        module_sdk,
                        "system.user.toast.updated.text",
                        context={"username": updated["username"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        error_text = str(exc).strip().lower()
        mapped_text = (
            t(module_sdk, "system.user.toast.username_taken")
            if "already in use" in error_text
            else t(module_sdk, "system.user.toast.update_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.update_error.title"),
                    "text": mapped_text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.user] update_user error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.update_error.title"),
                    "text": t(module_sdk, "system.user.toast.update_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("create_user")
@validate(UserCreatePayload, strip_extra=True)
@permission_required(["system.user.create"])
async def create_user(ctx: Dict[str, Any], session: dict, module_sdk):
    form_payload = ctx["user_create_form"]
    payload = {
        "username": form_payload["username"],
        "email": form_payload["email"],
        "role": form_payload["role"],
        "access_level": form_payload["access_level"],
        "password": form_payload["password"],
    }

    try:
        created = module_sdk.models.users.create(payload)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.created.title"),
                    "text": t(
                        module_sdk,
                        "system.user.toast.created.text",
                        context={"username": created["username"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        error_text = str(exc).strip().lower()
        mapped_text = (
            t(module_sdk, "system.user.toast.username_taken")
            if "already in use" in error_text
            else t(module_sdk, "system.user.toast.create_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.create_error.title"),
                    "text": mapped_text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.user] create_user error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.create_error.title"),
                    "text": t(module_sdk, "system.user.toast.create_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("delete_user")
@validate(RowActionPayload, strip_extra=True)
@permission_required(["system.user.delete"])
async def delete_user(ctx: Dict[str, Any], session: dict, module_sdk):
    item = ctx["item"]
    user_id = item["id"]
    current_user_id = int(session["user"]["id"])
    if current_user_id == user_id:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.delete_error.title"),
                    "text": t(module_sdk, "system.user.toast.delete_error.self"),
                    "variant": "destructive",
                },
            )
        )

    try:
        deleted = bool(module_sdk.models.users.delete(user_id))
        if not deleted:
            return module_sdk.effects.respond()

        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.deleted.title"),
                    "text": t(
                        module_sdk,
                        "system.user.toast.deleted.text",
                        context={"user_id": user_id},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.user] delete_user error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.delete_error.title"),
                    "text": t(module_sdk, "system.user.toast.delete_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("change_password")
@validate(UserChangePasswordPayload, strip_extra=True)
@permission_required(["system.user.change_password"])
async def change_password(ctx: Dict[str, Any], session: dict, module_sdk):
    user_id = ctx["user_id"]
    payload = ctx["user_change_password_form"]

    try:
        updated = module_sdk.models.users.update(
            user_id,
            {"password": payload["new_password"]},
        )
        if updated is None:
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {
                        "title": t(module_sdk, "system.user.toast.password_error.title"),
                        "text": t(module_sdk, "system.user.toast.user_not_found"),
                        "variant": "destructive",
                    },
                )
            )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.password_updated.title"),
                    "text": t(module_sdk, "system.user.toast.password_updated.text"),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.user] change_password error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.user.toast.password_error.title"),
                    "text": t(module_sdk, "system.user.toast.password_error.text"),
                    "variant": "destructive",
                },
            )
        )


__all__ = [
    "list_user",
    "view_user",
    "update_user",
    "create_user",
    "delete_user",
    "change_password",
]
