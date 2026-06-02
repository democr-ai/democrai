from __future__ import annotations

from typing import Any


def normalize_filters(raw_filters: Any) -> dict[str, Any]:
    if not isinstance(raw_filters, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw_filters.items():
        field = str(key or "").strip()
        if not field or value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        normalized[field] = value
    return normalized


def normalize_sort(raw_sort: Any, *, default_field: str) -> dict[str, str]:
    if not isinstance(raw_sort, dict):
        return {"field": default_field, "direction": "desc"}
    field = str(raw_sort.get("field") or raw_sort.get("sortField") or "").strip()
    direction = (
        str(raw_sort.get("direction") or raw_sort.get("sortDirection") or "desc")
        .strip()
        .lower()
    )
    if not field:
        field = default_field
    if direction not in {"asc", "desc"}:
        direction = "desc"
    return {"field": field, "direction": direction}


def list_remote_table(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
    *,
    model_name: str,
    table_id_default: str,
    default_sort_field: str,
):
    table_id = str(
        ctx.get("table_id") or ctx.get("tableId") or table_id_default
    ).strip()
    page = max(0, int(ctx.get("page", 0) or 0))
    page_size = max(1, min(int(ctx.get("pageSize", 40) or 40), 200))
    filters = normalize_filters(ctx.get("filters") or {})
    sort = normalize_sort(ctx.get("sort") or {}, default_field=default_sort_field)

    listing = getattr(module_sdk.models, model_name).list(
        page=page,
        page_size=page_size,
        filters=filters,
        sort=sort,
    )
    rows = listing["rows"]
    total_rows = listing["total_rows"]
    resolved_page = listing["page"]
    resolved_page_size = listing["page_size"]
    resolved_sort = listing["sort"]

    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(table_id, "rows", rows, action="set"),
        module_sdk.effects.ui_property_update(table_id, "page", resolved_page),
        module_sdk.effects.ui_property_update(
            table_id, "page_size", resolved_page_size
        ),
        module_sdk.effects.ui_property_update(table_id, "total_rows", total_rows),
        module_sdk.effects.ui_property_update(table_id, "sort", resolved_sort),
        # module_sdk.effects.navigate(next_path, render=False),
    )
