from __future__ import annotations

from typing import Any


def organization_table_provider(
    sdk_instance,
    *,
    page: int = 0,
    page_size: int = 25,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = list(sdk_instance.models.organizations.table_model() or [])
    headers = {
        "id": sdk_instance.i18n.t("system.organization.table.id"),
        "name": sdk_instance.i18n.t("system.organization.table.name"),
        "description": sdk_instance.i18n.t("system.organization.table.description"),
        "created_at": sdk_instance.i18n.t("system.organization.table.created_at"),
    }
    for column in model:
        field = str(column.get("field") or "")
        column["header"] = headers.get(field, field)
        if field == "id":
            column["filterable"] = True
            column["filter_type"] = "int"

    listing = sdk_instance.models.organizations.list(
        page=page,
        page_size=page_size,
        filters=filters or {},
    )
    return {
        "model": model,
        "rows": list(listing.get("rows") or []),
        "total_rows": int(listing.get("total_rows") or 0),
        "page": int(listing.get("page") or page),
        "page_size": int(listing.get("page_size") or page_size),
    }


__all__ = [
    "organization_table_provider",
]
