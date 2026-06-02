from __future__ import annotations

from typing import Any


def role_table_provider(
    sdk_instance,
    *,
    page: int = 0,
    page_size: int = 25,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = list(sdk_instance.models.roles.table_model() or [])
    headers = {
        "id": sdk_instance.i18n.t("system.role.table.id"),
        "name": sdk_instance.i18n.t("system.role.table.name"),
        "description": sdk_instance.i18n.t("system.role.table.description"),
        "permissions_count": sdk_instance.i18n.t(
            "system.role.table.permissions_count"
        ),
    }
    for column in model:
        field = str(column.get("field") or "")
        column["header"] = headers.get(field, field)

    listing = sdk_instance.models.roles.list(
        page=page,
        page_size=page_size,
        filters=filters or {},
    )
    rows = list(listing.get("rows") or [])
    for row in rows:
        if not isinstance(row, dict):
            continue
        row["is_super_role"] = str(row.get("name") or "").strip().lower() == "super"
    return {
        "model": model,
        "rows": rows,
        "total_rows": int(listing.get("total_rows") or 0),
        "page": int(listing.get("page") or page),
        "page_size": int(listing.get("page_size") or page_size),
    }


__all__ = [
    "role_table_provider",
]
