from __future__ import annotations

from typing import Any


def datatable_request(ctx: dict[str, Any]) -> tuple[int, int, dict[str, Any]]:
    page = max(0, int(ctx.get("page", 0)))
    page_size = max(1, min(int(ctx.get("pageSize", 25)), 200))
    return page, page_size, normalized_filters(ctx.get("filters"))


def datatable_payload(
    listing: dict[str, Any],
    *,
    page: int,
    page_size: int,
    filters: dict[str, Any],
    sort: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "ok": True,
        "rows": list(listing.get("rows") or []),
        "total_rows": int(listing.get("total_rows") or 0),
        "page": int(listing.get("page") or page),
        "page_size": int(listing.get("page_size") or page_size),
        "filters": filters,
    }
    if sort is not None:
        payload["sort"] = dict(listing.get("sort") or sort)
    return payload


def datatable_response(
    module_sdk,
    table_id: str,
    payload: dict[str, Any],
):
    return module_sdk.effects.respond(
        *datatable_update_effects(module_sdk, table_id, payload)
    )


def datatable_update_effects(
    module_sdk,
    table_id: str,
    payload: dict[str, Any],
) -> list[dict]:
    effects = [
        module_sdk.effects.ui_property_update(
            table_id,
            "rows",
            payload["rows"],
            action="set",
        ),
        module_sdk.effects.ui_property_update(table_id, "page", payload["page"]),
        module_sdk.effects.ui_property_update(
            table_id,
            "page_size",
            payload["page_size"],
        ),
        module_sdk.effects.ui_property_update(
            table_id,
            "total_rows",
            payload["total_rows"],
        ),
    ]
    if "sort" in payload:
        effects.append(
            module_sdk.effects.ui_property_update(table_id, "sort", payload["sort"])
        )
    return effects


def datatable_remote_request(
    ctx: dict[str, Any],
) -> tuple[int, int, dict[str, Any], dict[str, Any]]:
    page, page_size, filters = datatable_request(ctx)
    sort = ctx.get("sort") or {}
    if not isinstance(sort, dict):
        sort = {}
    if not sort and (ctx.get("sortField") or ctx.get("sortDirection")):
        sort = {
            "field": str(ctx.get("sortField") or "").strip(),
            "direction": str(ctx.get("sortDirection") or "").strip(),
        }
    return page, page_size, filters, sort


def normalized_filters(raw_filters: Any) -> dict[str, Any]:
    if not isinstance(raw_filters, dict):
        return {}
    normalized: dict[str, Any] = {}
    for key, value in raw_filters.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        normalized[str(key)] = value
    return normalized


__all__ = [
    "datatable_payload",
    "datatable_request",
    "datatable_remote_request",
    "datatable_response",
    "datatable_update_effects",
    "normalized_filters",
]
