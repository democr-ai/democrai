from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field, field_validator

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
from modules.system.utils.actions.role.module import module_rows_for_role

TABLE_ID = "role_list_table"


class RoleFormPayload(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("role name is required")
        return name


class RoleCreatePayload(BaseModel):
    role_create_form: RoleFormPayload


class RoleUpdatePayload(BaseModel):
    role_id: int
    role_update_form: RoleFormPayload


def _is_protected_role_error(exc: Exception) -> bool:
    return "super role cannot be modified or deleted" in str(exc).strip().lower()


def _toggle_checked_effect(module_sdk, toggle_id: str, checked: bool):
    return module_sdk.effects.ui_property_update(toggle_id, "checked", checked)


@action("list_role")
@permission_required(["system.role.list"])
async def list_role(ctx: Dict, session: dict, module_sdk):
    page, page_size, filters = datatable_request(ctx)
    listing = module_sdk.models.roles.list(
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
    rows = payload["rows"]
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["is_super_role"] = str(row.get("name") or "").strip().lower() == "super"
    return datatable_response(module_sdk, TABLE_ID, payload)


@action("view_role")
@permission_required(["system.role.view"])
async def view_role(ctx: Dict, session: dict, module_sdk):
    if str(ctx.get("op") or "").strip() == "open":
        item = ctx["item"]
        role_id = int(item["id"])
        return module_sdk.effects.respond(
            module_sdk.effects.navigate(f"/system/role/{role_id}/view", render=True)
        )

    if "role_id" not in ctx:
        return module_sdk.effects.respond()

    role_id = int(ctx["role_id"])
    role = module_sdk.models.roles.view(role_id)
    if role is None:
        return {"ok": False, "error": "role_not_found"}
    return {"ok": True, "role": role}


@action("create_role")
@validate(RoleCreatePayload, strip_extra=True)
@permission_required(["system.role.create"])
async def create_role(ctx: Dict, session: dict, module_sdk):
    payload = ctx["role_create_form"]

    try:
        created = module_sdk.models.roles.create(payload)
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.created.title"),
                    "text": t(
                        module_sdk,
                        "system.role.toast.created.text",
                        context={"name": created["name"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        message = str(exc).strip().lower()
        text = (
            t(module_sdk, "system.role.toast.create_error.name_taken")
            if "already in use" in message
            else t(module_sdk, "system.role.toast.create_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.create_error.title"),
                    "text": text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.role] create_role error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.create_error.title"),
                    "text": t(module_sdk, "system.role.toast.create_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("update_role")
@validate(RoleUpdatePayload, strip_extra=True)
@permission_required(["system.role.update"])
async def update_role(ctx: Dict, session: dict, module_sdk):
    role_id = ctx["role_id"]
    payload = ctx["role_update_form"]

    try:
        updated = module_sdk.models.roles.update(role_id, payload)
        if updated is None:
            return module_sdk.effects.respond()
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.updated.title"),
                    "text": t(
                        module_sdk,
                        "system.role.toast.updated.text",
                        context={"name": updated["name"]},
                    ),
                    "variant": "success",
                },
            ),
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.render(),
        )
    except ValueError as exc:
        message = str(exc).strip().lower()
        if _is_protected_role_error(exc):
            text = t(module_sdk, "system.role.toast.update_error.super_protected")
        else:
            text = (
                t(module_sdk, "system.role.toast.update_error.name_taken")
                if "already in use" in message
                else t(module_sdk, "system.role.toast.update_error.text")
            )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.update_error.title"),
                    "text": text,
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.role] update_role error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.update_error.title"),
                    "text": t(module_sdk, "system.role.toast.update_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("delete_role")
@permission_required(["system.role.delete"])
async def delete_role(ctx: Dict, session: dict, module_sdk):
    item = ctx["item"]
    role_id = int(item["id"])
    try:
        deleted = bool(module_sdk.models.roles.delete(role_id))
        if deleted:
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {
                        "title": t(module_sdk, "system.role.toast.deleted.title"),
                        "text": t(module_sdk, "system.role.toast.deleted.text"),
                        "variant": "success",
                    },
                ),
                module_sdk.effects.render(),
            )
        return module_sdk.effects.respond()
    except ValueError as exc:
        if _is_protected_role_error(exc):
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {
                        "title": t(module_sdk, "system.role.toast.delete_error.title"),
                        "text": t(
                            module_sdk, "system.role.toast.delete_error.super_protected"
                        ),
                        "variant": "destructive",
                    },
                )
            )
        module_sdk.system.log(f"[system.role] delete_role value error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.delete_error.title"),
                    "text": t(module_sdk, "system.role.toast.delete_error.text"),
                    "variant": "destructive",
                },
            )
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.role] delete_role error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.delete_error.title"),
                    "text": t(module_sdk, "system.role.toast.delete_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("toggle_role_permission")
@permission_required(["system.role.update"])
async def toggle_role_permission(ctx: Dict, session: dict, module_sdk):
    permission_name = str(ctx["permission"]).strip()
    if not permission_name:
        raise ValueError("toggle_role_permission requires permission")
    checked = bool(ctx["checked"])
    toggle_id = str(ctx["toggle_id"])
    role_id = int(ctx["role_id"])
    role = module_sdk.models.roles.view(role_id)
    if role is None:
        return module_sdk.effects.respond(
            _toggle_checked_effect(module_sdk, toggle_id, not checked)
        )

    permissions = []
    seen: set[str] = set()
    for item in list(role.get("permissions") or []):
        value = str(item or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        permissions.append(value)

    currently_assigned = permission_name in seen

    if checked:
        if permission_name not in seen:
            permissions.append(permission_name)
    else:
        permissions = [item for item in permissions if item != permission_name]

    try:
        module_sdk.models.roles.update(role_id, {"permissions": permissions})
        return module_sdk.effects.respond(module_sdk.effects.render())
    except ValueError as exc:
        text = (
            t(module_sdk, "system.role.toast.update_error.super_protected")
            if _is_protected_role_error(exc)
            else t(module_sdk, "system.role.toast.update_error.text")
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.update_error.title"),
                    "text": text,
                    "variant": "destructive",
                },
            ),
            _toggle_checked_effect(module_sdk, toggle_id, currently_assigned),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.role] toggle_role_permission error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.toast.update_error.title"),
                    "text": t(module_sdk, "system.role.toast.update_error.text"),
                    "variant": "destructive",
                },
            ),
            _toggle_checked_effect(module_sdk, toggle_id, currently_assigned),
        )


@action("disable_role_module")
@permission_required(["system.role.update"])
async def disable_role_module(ctx: Dict, session: dict, module_sdk):
    item = ctx["item"]
    role_id = int(item["role_id"])
    role = module_sdk.models.roles.view(role_id)
    if role is None:
        return module_sdk.effects.respond()
    if str(role.get("name") or "").strip().lower() == "super":
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.modules.toast.disable_error.title"),
                    "text": t(module_sdk, "system.role.modules.toast.super_protected"),
                    "variant": "destructive",
                },
            )
        )

    module_name = str(item["module_name"]).strip()

    try:
        existing = module_sdk.models.module_locks.list(
            page=0,
            page_size=200,
            filters={"module_name": module_name, "role_id": role_id},
        )
        existing_rows = existing["rows"]
        already_locked = False
        for lock in existing_rows:
            if lock.get("user_id") is None and lock.get("organization_id") is None:
                already_locked = True
                break
        if not already_locked:
            module_sdk.models.module_locks.create(
                {
                    "module_name": module_name,
                    "user_id": None,
                    "organization_id": None,
                    "role_id": role_id,
                }
            )

        rows = module_rows_for_role(role_id, module_sdk)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_property_update(
                "role_modules_table", "rows", rows, action="set"
            ),
            module_sdk.effects.ui_property_update(
                "role_modules_table", "total_rows", len(rows)
            ),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.modules.toast.disable.title"),
                    "text": t(
                        module_sdk,
                        "system.role.modules.toast.disable.text",
                        context={"module_name": module_name},
                    ),
                    "variant": "success",
                },
            ),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.role] disable_role_module error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.modules.toast.disable_error.title"),
                    "text": t(module_sdk, "system.role.modules.toast.disable_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("enable_role_module")
@permission_required(["system.role.update"])
async def enable_role_module(ctx: Dict, session: dict, module_sdk):
    item = ctx["item"]
    role_id = int(item["role_id"])
    role = module_sdk.models.roles.view(role_id)
    if role is None:
        return module_sdk.effects.respond()
    if str(role.get("name") or "").strip().lower() == "super":
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.modules.toast.enable_error.title"),
                    "text": t(module_sdk, "system.role.modules.toast.super_protected"),
                    "variant": "destructive",
                },
            )
        )

    module_name = str(item["module_name"]).strip()

    try:
        existing = module_sdk.models.module_locks.list(
            page=0,
            page_size=50,
            filters={"module_name": module_name, "role_id": role_id},
        )
        existing_rows = existing["rows"]
        for lock in existing_rows:
            if lock.get("user_id") is not None or lock.get("organization_id") is not None:
                continue
            lock_id = lock.get("id")
            if lock_id is None:
                continue
            module_sdk.models.module_locks.delete(int(lock_id))

        rows = module_rows_for_role(role_id, module_sdk)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_property_update(
                "role_modules_table", "rows", rows, action="set"
            ),
            module_sdk.effects.ui_property_update(
                "role_modules_table", "total_rows", len(rows)
            ),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.modules.toast.enable.title"),
                    "text": t(
                        module_sdk,
                        "system.role.modules.toast.enable.text",
                        context={"module_name": module_name},
                    ),
                    "variant": "success",
                },
            ),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.role] enable_role_module error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": t(module_sdk, "system.role.modules.toast.enable_error.title"),
                    "text": t(module_sdk, "system.role.modules.toast.enable_error.text"),
                    "variant": "destructive",
                },
            )
        )


__all__ = [
    "list_role",
    "view_role",
    "create_role",
    "update_role",
    "delete_role",
    "toggle_role_permission",
    "disable_role_module",
    "enable_role_module",
]
