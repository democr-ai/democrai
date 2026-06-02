from __future__ import annotations

from typing import Any, Dict

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.utils.actions.user.module import module_rows_for_user


@action("disable_module")
@permission_required(["system.user.module.lock"])
async def disable_module(ctx: Dict[str, Any], session: dict, module_sdk):
    """
    Disable module for user (create lock with user_id only).
    """
    item = ctx["item"]
    user_id = int(item["user_id"])
    module_name = str(item["module_name"]).strip()

    try:
        existing = module_sdk.models.module_locks.list(
            page=0,
            page_size=200,
            filters={
                "module_name": module_name,
                "user_id": user_id,
            },
        )
        existing_rows = existing["rows"]
        already_locked = False
        for lock in existing_rows:
            if lock.get("organization_id") is None and lock.get("role_id") is None:
                already_locked = True
                break
        if not already_locked:
            module_sdk.models.module_locks.create(
                {
                    "module_name": module_name,
                    "user_id": user_id,
                    "organization_id": None,
                    "role_id": None,
                }
            )

        rows = module_rows_for_user(user_id, module_sdk)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_property_update(
                "user_modules_table", "rows", rows, action="set"
            ),
            module_sdk.effects.ui_property_update(
                "user_modules_table", "total_rows", len(rows)
            ),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("system.user.modules.toast.disable.title"),
                    "text": module_sdk.i18n.t(
                        "system.user.modules.toast.disable.text",
                        context={"module_name": module_name},
                    ),
                    "variant": "success",
                },
            ),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.user] disable_module error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("system.user.modules.toast.disable_error.title"),
                    "text": module_sdk.i18n.t("system.user.modules.toast.disable_error.text"),
                    "variant": "destructive",
                },
            )
        )


@action("enable_module")
@permission_required(["system.user.module.unlock"])
async def enable_module(ctx: Dict[str, Any], session: dict, module_sdk):
    """
    Enable module for user (remove user-only lock).
    """
    item = ctx["item"]
    user_id = int(item["user_id"])
    module_name = str(item["module_name"]).strip()

    try:
        existing = module_sdk.models.module_locks.list(
            page=0,
            page_size=50,
            filters={
                "module_name": module_name,
                "user_id": user_id,
            },
        )
        existing_rows = existing["rows"]
        for lock in existing_rows:
            if lock.get("organization_id") is not None or lock.get("role_id") is not None:
                continue
            lock_id = lock.get("id")
            if lock_id is None:
                continue
            module_sdk.models.module_locks.delete(int(lock_id))

        rows = module_rows_for_user(user_id, module_sdk)
        return module_sdk.effects.respond(
            module_sdk.effects.ui_property_update(
                "user_modules_table", "rows", rows, action="set"
            ),
            module_sdk.effects.ui_property_update(
                "user_modules_table", "total_rows", len(rows)
            ),
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("system.user.modules.toast.enable.title"),
                    "text": module_sdk.i18n.t(
                        "system.user.modules.toast.enable.text",
                        context={"module_name": module_name},
                    ),
                    "variant": "success",
                },
            ),
        )
    except Exception as exc:
        module_sdk.system.log(f"[system.user] enable_module error: {exc}", "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "title": module_sdk.i18n.t("system.user.modules.toast.enable_error.title"),
                    "text": module_sdk.i18n.t("system.user.modules.toast.enable_error.text"),
                    "variant": "destructive",
                },
            )
        )
__all__ = [
    "disable_module",
    "enable_module",
]
