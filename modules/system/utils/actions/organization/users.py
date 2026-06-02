from __future__ import annotations

from typing import Any


def organization_user_rows(
    organization_id: int,
    module_sdk,
    *,
    page: int = 0,
    page_size: int = 500,
) -> tuple[list[dict[str, Any]], int]:
    listing = module_sdk.models.users.list(
        page=page,
        page_size=page_size,
        filters={"organization_id": organization_id},
    )
    rows = list(listing.get("rows") or [])
    total_rows = int(listing.get("total_rows") or len(rows))
    return rows, total_rows
