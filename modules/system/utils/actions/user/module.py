from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as runtime_sdk


def all_runtime_modules(module_sdk) -> list[dict[str, Any]]:
    return module_sdk.system.modules.list()


def module_rows_for_user(user_id: int, module_sdk=None) -> list[dict[str, Any]]:
    module_sdk = module_sdk or runtime_sdk
    locks_result = module_sdk.models.module_locks.list(
        page=0,
        page_size=500,
        filters={"user_id": user_id},
    )
    lock_rows = locks_result["rows"]
    locked_map: dict[str, int] = {}
    for lock in lock_rows:
        if lock.get("organization_id") is not None or lock.get("role_id") is not None:
            continue
        module_name = str(lock.get("module_name") or "").strip()
        if module_name:
            locked_map[module_name] = int(lock["id"])

    rows: list[dict[str, Any]] = []
    for module in all_runtime_modules(module_sdk):
        module_name = str(module["module_name"])
        lock_id = locked_map.get(module_name)
        rows.append(
            {
                "user_id": user_id,
                "module_name": module_name,
                "label": str(module.get("label") or module_name),
                "version": str(module.get("version") or ""),
                "locked": bool(lock_id),
                "lock_id": lock_id,
            }
        )

    return rows
