from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AIModelSourceKind

from modules.system.utils.actions.engine.models import parse_capabilities


def inventory_status(row: dict[str, Any]) -> str:
    status = str(row.get("status") or "available").strip().lower()
    if status in {"uploading", "downloading"}:
        return "downloading"
    return status or "available"


def inventory_list_items(
    module_sdk,
    rows: list[dict[str, Any]],
    *,
    search: str = "",
    status_filter: str = "",
) -> list[dict[str, Any]]:
    query = str(search or "").strip().lower()
    normalized_status_filter = str(status_filter or "").strip().lower()
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_kind = str(row.get("source_kind") or "").strip().lower()
        if source_kind == AIModelSourceKind.CATALOG:
            continue
        status = inventory_status(row)
        if normalized_status_filter and status != normalized_status_filter:
            continue
        capabilities = parse_capabilities(row.get("capabilities"))
        search_text = " ".join(
            [
                str(row.get("name") or ""),
                str(row.get("label") or ""),
                str(row.get("summary") or ""),
                str(row.get("format") or ""),
                source_kind,
                ", ".join(capabilities),
            ]
        ).lower()
        if query and query not in search_text:
            continue
        status_key = {
            "available": "system.model.inventory.status.available",
            "downloading": "system.model.inventory.status.downloading",
            "failed": "system.model.inventory.status.failed",
        }.get(status, "system.model.inventory.status.available")
        status_icon = {
            "available": "ric.checkbox-circle-line",
            "downloading": "ric.progress-3-line",
            "failed": "ric.error-warning-line",
        }.get(status, "ric.checkbox-circle-line")
        status_icon_color = {
            "available": "#22C55E",
            "downloading": "#3B82F6",
            "failed": "#EF4444",
        }.get(status, "#22C55E")
        meta = " | ".join(
            item
            for item in [
                str(row.get("summary") or ""),
                source_kind,
                str(row.get("format") or ""),
                f"{module_sdk.i18n.t('system.model.catalog.item.capabilities')}: {', '.join(capabilities)}",
                module_sdk.i18n.t(status_key),
            ]
            if item
        )
        items.append(
            {
                "id": int(row["id"]),
                "title": str(row.get("label") or row.get("name") or ""),
                "text": meta,
                "icon": status_icon,
                "icon_color": status_icon_color,
                "status": status,
                "retryable": status == "failed"
                and source_kind == AIModelSourceKind.CATALOG,
            }
        )
    return items
