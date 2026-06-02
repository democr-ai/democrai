from __future__ import annotations

from typing import Any


def user_table_provider(
    sdk_instance,
    *,
    page: int = 0,
    page_size: int = 25,
    filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = list(sdk_instance.models.users.table_model())
    headers = {
        "id": sdk_instance.i18n.t("system.user.table.id"),
        "username": sdk_instance.i18n.t("system.user.table.username"),
        "email": sdk_instance.i18n.t("system.user.table.email"),
        "role": sdk_instance.i18n.t("system.user.table.role"),
        "access_level": sdk_instance.i18n.t("system.user.table.access"),
        "organization_name": sdk_instance.i18n.t("system.user.table.organization"),
        "created_at": sdk_instance.i18n.t("system.user.table.created"),
    }
    for col in model:
        field_name = str(col.get("field") or "")
        if field_name in headers:
            col["header"] = headers[field_name]
    listing = sdk_instance.models.users.list(
        page=page,
        page_size=page_size,
        filters=filters,
    )
    rows = list(listing.get("rows") or [])
    total_rows = int(listing.get("total_rows") or 0)
    return {
        "model": model,
        "rows": rows,
        "total_rows": total_rows,
        "page": int(page),
        "page_size": int(page_size),
        "filters": dict(filters or {}),
        "filterable_fields": [col["field"] for col in model if col.get("filterable")],
    }


__all__ = [
    "user_table_provider",
]
