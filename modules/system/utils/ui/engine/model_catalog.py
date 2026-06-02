from __future__ import annotations

from typing import Any

from modules.system.utils.actions.model.catalog import (
    catalog_statuses_from_inventory,
    load_static_model_catalog,
)
from modules.system.utils.ui.model.catalog import catalog_list_page


ENGINE_CATALOG_PAGE_SIZE = 20


def engine_catalog_entries(entries: list[dict[str, Any]], provider: str) -> list[dict[str, Any]]:
    normalized_provider = str(provider or "").strip().lower()
    if not normalized_provider:
        return []
    return [
        entry
        for entry in entries
        if bool(entry.get("downloadable"))
        and normalized_provider
        in {
            str(engine or "").strip().lower()
            for engine in list(entry.get("source_engines") or [entry.get("source_engine")])
        }
    ]


async def load_engine_catalog_page(
    module_sdk,
    provider: str,
    *,
    engine_id: int | None = None,
    search: str = "",
    status_filter: str = "",
    page: int = 0,
    page_size: int = ENGINE_CATALOG_PAGE_SIZE,
) -> dict[str, Any]:
    inventory_rows = (
        module_sdk.models.available_model_registry.all(
            sort={"field": "label", "direction": "asc"},
        ).get("rows")
        or []
    )
    catalog_entries = await load_static_model_catalog(module_sdk)
    scoped_entries = engine_catalog_entries(catalog_entries, provider)
    catalog_statuses = catalog_statuses_from_inventory(
        module_sdk,
        inventory_rows,
        scoped_entries,
    )
    page_data = catalog_list_page(
        module_sdk,
        scoped_entries,
        catalog_statuses,
        search=search,
        status_filter=status_filter,
        engine_filter=str(provider or "").strip().lower(),
        page=page,
        page_size=page_size,
    )
    if engine_id is not None:
        resolved_items = []
        for item in list(page_data.get("items") or []):
            if not isinstance(item, dict):
                continue
            catalog_id = str(item.get("id") or "").strip()
            resolved_items.append(
                {
                    **item,
                    "detail_path": (
                        f"/system/engine/instance/{int(engine_id)}"
                        f"/model/catalog/{catalog_id}/view"
                    ),
                }
            )
        page_data["items"] = resolved_items
    return page_data
