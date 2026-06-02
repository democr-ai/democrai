from __future__ import annotations

from typing import Any


def environment_table_provider(
    sdk_instance,
    *,
    page: int = 0,
    page_size: int = 25,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    listing = sdk_instance.models.environment_variable_registry.list(
        page=page,
        page_size=page_size,
        filters=filters or {},
    )
    return {
        "model": sdk_instance.models.environment_variable_registry.table_model(),
        "rows": list(listing.get("rows") or []),
        "total_rows": int(listing.get("total_rows") or 0),
        "page": int(listing.get("page") or page),
        "page_size": int(listing.get("page_size") or page_size),
    }


__all__ = [
    "environment_table_provider",
]
