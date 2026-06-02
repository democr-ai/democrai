from __future__ import annotations

import asyncio
import time
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.utils.actions.model.catalog import (
    catalog_statuses_from_inventory,
    load_static_model_catalog,
    active_catalog_download_ids,
)
from modules.system.utils.ui.model.catalog import catalog_list_page, catalog_page_info


CATALOG_PAGE_SIZE = 20


def _toast(
    module_sdk,
    level: str,
    message_key: str,
    context: dict[str, Any] | None = None,
):
    return module_sdk.effects.notify(
        "toast",
        {
            "level": level,
            "message": module_sdk.i18n.t(message_key, context=context or {}),
        },
    )


def _catalog_items_with_status(
    module_sdk,
    items: Any,
    entry: dict[str, Any],
    status: str,
) -> list[dict[str, Any]]:
    current_items = [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    catalog_id = str(entry.get("catalog_id") or "").strip()
    if not current_items or not catalog_id:
        return current_items
    replacement = catalog_list_page(
        module_sdk,
        [entry],
        {catalog_id: status},
        page_size=1,
    ).get("items") or []
    if not replacement or not isinstance(replacement[0], dict):
        return current_items
    return [
        dict(replacement[0]) if str(item.get("id") or "") == catalog_id else item
        for item in current_items
    ]


@action("system.filter_model_catalog")
@permission_required(["system.engine.model.manage"])
async def filter_model_catalog(ctx: dict[str, Any], session: dict, module_sdk):
    page_size = max(1, min(int(ctx.get("page_size") or CATALOG_PAGE_SIZE), 100))
    page = max(0, int(ctx.get("page") or 0))
    direction = str(ctx["direction"]).strip() if "direction" in ctx else ""
    if direction == "next":
        page += 1
    elif direction == "prev":
        page -= 1

    search = str(ctx.get("system_model_catalog_search") or "").strip()
    status_filter = str(ctx.get("system_model_catalog_status_filter") or "").strip()
    engine_filter = str(ctx.get("system_model_catalog_engine_filter") or "").strip()
    inventory_rows = (
        module_sdk.models.available_model_registry.all(
            sort={"field": "label", "direction": "asc"},
        ).get("rows")
        or []
    )
    catalog_entries = await load_static_model_catalog(module_sdk)
    catalog_statuses = catalog_statuses_from_inventory(module_sdk, inventory_rows, catalog_entries)
    page_data = catalog_list_page(
        module_sdk,
        catalog_entries,
        catalog_statuses,
        search=search,
        status_filter=status_filter,
        engine_filter=engine_filter,
        page=page,
        page_size=page_size,
    )
    resolved_page = int(page_data.get("page") or 0)
    resolved_page_size = int(page_data.get("page_size") or page_size)
    total = int(page_data.get("total") or 0)
    surface_id = str(ctx["_surface_id"])
    button_params = {"page": resolved_page, "page_size": resolved_page_size}

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/system/model/catalog/show_pagination": total
                            > resolved_page_size,
                            "/system/model/catalog/items": list(page_data.get("items") or []),
                        },
                    }
                }
            ]
        ),
        module_sdk.effects.ui_property_update(
            "system_model_catalog_page_info",
            "text",
            catalog_page_info(
                module_sdk,
                page=resolved_page,
                page_size=resolved_page_size,
                total=total,
            ),
            surface_id=surface_id,
        ),
        module_sdk.effects.ui_property_update(
            "system_model_catalog_prev",
            "params",
            {**button_params, "direction": "prev"},
            surface_id=surface_id,
        ),
        module_sdk.effects.ui_property_update(
            "system_model_catalog_next",
            "params",
            {**button_params, "direction": "next"},
            surface_id=surface_id,
        ),
    )


@action("download_model")
@permission_required(["system.engine.model.manage"])
async def download_model(ctx: dict[str, Any], session: dict, module_sdk):
    catalog_id = str(ctx["catalog_id"]).strip()
    confirmed_resource_warning = bool(ctx.get("confirmed_resource_warning"))

    try:
        preflight = await module_sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=confirmed_resource_warning,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "catalog_already_added":
            return module_sdk.effects.respond(
                _toast(module_sdk, "warning", "system.model.toast.catalog_already_added")
            )
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.catalog_not_found")
        )

    entry = dict(preflight.get("entry") or {})
    active_downloads = active_catalog_download_ids(module_sdk)
    if catalog_id in active_downloads:
        return module_sdk.effects.respond(
            _toast(module_sdk, "warning", "system.model.toast.catalog_already_running")
        )

    if str(preflight.get("status") or "") == "requires_confirmation":
        return module_sdk.effects.respond(
            module_sdk.effects.confirm(
                via="dialog",
                path="/system/model/catalog/resource_warning",
                params={
                    "catalog_id": catalog_id,
                    "task_mount_id": str(ctx["task_mount_id"]).strip(),
                    "label": str(entry.get("label") or ""),
                    "resource_warning": dict(preflight.get("resource_warning") or {}),
                    "items": list(ctx.get("items") or []),
                },
            )
        )

    attempt_id = str(int(time.time() * 1000))
    task_ref = {"task_id": ""}

    async def _run_download():
        while not str(task_ref.get("task_id") or "").strip():
            await asyncio.sleep(0.05)
        return await module_sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=confirmed_resource_warning,
            task_id=str(task_ref["task_id"]),
        )

    task_id = await module_sdk.tasks.run_background(
        _run_download(),
        label=f"{module_sdk.i18n.t('system.model.catalog.action.download')}: {str(entry.get('label') or '')}",
        task_key=f"system.model.catalog.download.{catalog_id}.{attempt_id}",
    )
    task_ref["task_id"] = task_id

    mount_id = str(ctx["task_mount_id"]).strip()
    task_card = module_sdk.ui.BackgroundTask(
        f"model_catalog_download_{catalog_id}_{task_id}",
        task_id=task_id,
    )
    catalog_items = _catalog_items_with_status(
        module_sdk,
        ctx.get("items"),
        entry,
        "downloading",
    )
    messages = [
        {"deleteSurface": {"surfaceId": "drawer"}},
        {"deleteSurface": {"surfaceId": "modal"}},
        {
            "stateUpdate": {
                "scope": "page",
                "values": {
                    "/system/model/catalog_detail/imported": False,
                    "/system/model/catalog_detail/can_download": False,
                    "/system/model/catalog_detail/downloading": True,
                },
            }
        },
    ]
    if catalog_items:
        messages.append(
            {
                "stateUpdate": {
                    "scope": "page",
                    "values": {"/system/model/catalog/items": catalog_items},
                }
            }
        )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(messages),
        module_sdk.effects.ui_collection_append(
            mount_id,
            "children",
            task_card.to_dict(),
        ),
        _toast(
            module_sdk,
            "success",
            "system.model.toast.catalog_started",
            {"label": str(entry.get("label") or "")},
        ),
        module_sdk.effects.render(),
    )
