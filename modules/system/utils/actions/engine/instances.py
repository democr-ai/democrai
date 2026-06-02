from __future__ import annotations

from typing import Any

from democrai.sdk.engines import provider_requirements


def ensure_default_engine_row(module_sdk, provider: str) -> dict[str, Any] | None:
    normalized = str(provider or "").strip().lower()
    requirements = provider_requirements(provider_id=normalized)
    if not normalized or bool(requirements.get("configurable")):
        return None

    listing = module_sdk.models.engine_registry.list(page=0, page_size=200, filters={})
    rows = listing.get("rows") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("provider") or "").strip().lower() == normalized:
            return row

    created = module_sdk.models.engine_registry.create(
        {
            "name": normalized,
            "provider": normalized,
            "config": {},
            "status": "uninstalled",
            "supported": True,
        }
    )
    return created if isinstance(created, dict) else None
