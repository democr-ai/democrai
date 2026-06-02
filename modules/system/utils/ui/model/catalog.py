from __future__ import annotations

from typing import Any


def _join_values(values: list[str]) -> str:
    return ", ".join(
        str(value or "").strip() for value in values if str(value or "").strip()
    )


def _requirement_value(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if number.is_integer():
        return f"{int(number)} GB"
    return f"{number:g} GB"


def _requirements_text(module_sdk, requirements: dict[str, Any]) -> str:
    parts = []
    for label, key in [("RAM", "ram_gb"), ("VRAM", "vram_gb"), ("Storage", "storage_gb")]:
        value = _requirement_value(requirements.get(key))
        if value:
            parts.append(f"{label}: {value}")
    if not parts:
        return ""
    return f"{module_sdk.i18n.t('system.model.detail.requirements')}: {', '.join(parts)}"


def _catalog_search_text(entry: dict[str, Any]) -> str:
    return " ".join(
        [
            str(entry.get("label") or ""),
            str(entry.get("summary") or ""),
            str(entry.get("format") or ""),
            str(entry.get("source_type") or ""),
            _join_values(list(entry.get("capabilities") or [])),
            _join_values(list(entry.get("source_engines") or [entry.get("source_engine")])),
        ]
    ).lower()


def _catalog_engine_values(entries: list[dict[str, Any]]) -> list[str]:
    engines: set[str] = set()
    for entry in entries:
        for engine in list(entry.get("source_engines") or [entry.get("source_engine")]):
            value = str(engine or "").strip()
            if value:
                engines.add(value)
    return sorted(engines)


def _engine_label(module_sdk, engine: str) -> str:
    key = f"system.engine.provider.{engine}.name"
    translated = module_sdk.i18n.t(key)
    if translated == key:
        return engine
    return translated


def catalog_engine_filter_options(
    module_sdk,
    entries: list[dict[str, Any]],
) -> list[dict[str, str]]:
    options = [
        {
            "label": module_sdk.i18n.t("system.model.filter.engine.all"),
            "value": "",
        }
    ]
    options.extend(
        {"label": _engine_label(module_sdk, engine), "value": engine}
        for engine in sorted(
            _catalog_engine_values(entries),
            key=lambda item: _engine_label(module_sdk, item).lower(),
        )
    )
    return options


def catalog_list_page(
    module_sdk,
    entries: list[dict[str, Any]],
    catalog_statuses: dict[str, str] | set[str],
    *,
    search: str = "",
    status_filter: str = "",
    engine_filter: str = "",
    page: int = 0,
    page_size: int = 20,
) -> dict[str, Any]:
    query = str(search or "").strip().lower()
    normalized_status_filter = str(status_filter or "").strip().lower()
    normalized_engine_filter = str(engine_filter or "").strip().lower()
    filtered = [
        entry
        for entry in entries
        if not query or query in _catalog_search_text(entry)
    ]
    resolved_entries: list[tuple[dict[str, Any], str]] = []
    for entry in filtered:
        catalog_id = str(entry.get("catalog_id") or "")
        if isinstance(catalog_statuses, dict):
            status = str(catalog_statuses.get(catalog_id) or "catalog_available").strip().lower()
        else:
            status = (
                "imported" if catalog_id in catalog_statuses else "catalog_available"
            )
        if normalized_status_filter and status != normalized_status_filter:
            continue
        if normalized_engine_filter:
            source_engines = {
                str(engine or "").strip().lower()
                for engine in list(entry.get("source_engines") or [entry.get("source_engine")])
            }
            if normalized_engine_filter not in source_engines:
                continue
        resolved_entries.append((entry, status))
    total = len(resolved_entries)
    resolved_page_size = max(1, page_size)
    max_page = max(0, (total - 1) // resolved_page_size)
    resolved_page = max(0, min(page, max_page))
    start = resolved_page * resolved_page_size
    page_entries = resolved_entries[start : start + resolved_page_size]
    items: list[dict[str, Any]] = []
    for entry, status in page_entries:
        catalog_id = str(entry.get("catalog_id") or "")
        imported = status in {"available", "downloading", "imported"}
        retryable = status == "failed"
        capabilities = _join_values(list(entry.get("capabilities") or []))
        engines = _join_values(list(entry.get("source_engines") or [entry.get("source_engine")]))
        requirements = _requirements_text(
            module_sdk,
            dict(entry.get("requirements") or {}),
        )
        capabilities_label = module_sdk.i18n.t(
            "system.model.catalog.item.capabilities"
        )
        engines_label = module_sdk.i18n.t("system.model.catalog.item.engines")
        status_key = {
            "catalog_available": "system.model.catalog.status.available",
            "available": "system.model.catalog.status.imported",
            "imported": "system.model.catalog.status.imported",
            "downloading": "system.model.catalog.status.downloading",
            "failed": "system.model.catalog.status.failed",
        }.get(status, "system.model.catalog.status.available")
        status_icon = {
            "catalog_available": "ric.download-cloud-2-line",
            "available": "ric.checkbox-circle-line",
            "imported": "ric.checkbox-circle-line",
            "downloading": "ric.progress-3-line",
            "failed": "ric.error-warning-line",
        }.get(status, "ric.download-cloud-2-line")
        status_icon_color = {
            "catalog_available": "#94A3B8",
            "available": "#22C55E",
            "imported": "#22C55E",
            "downloading": "#3B82F6",
            "failed": "#EF4444",
        }.get(status, "#94A3B8")
        items.append(
            {
                "id": catalog_id,
                "icon": status_icon,
                "icon_color": status_icon_color,
                "title": str(entry.get("label") or ""),
                "detail_path": f"/system/model/catalog/{catalog_id}/view",
                "text": " | ".join(
                    value
                    for value in [
                        str(entry.get("summary") or ""),
                        requirements,
                        f"{capabilities_label}: {capabilities}",
                        f"{engines_label}: {engines}",
                        module_sdk.i18n.t(status_key),
                    ]
                    if value
                ),
                "imported": imported,
                "retryable": retryable,
                "status": status,
            }
        )
    return {
        "items": items,
        "total": total,
        "page": resolved_page,
        "page_size": resolved_page_size,
    }


def catalog_page_info(module_sdk, *, page: int, page_size: int, total: int) -> str:
    if total <= 0:
        return module_sdk.i18n.t("system.model.catalog.empty")
    start = page * page_size + 1
    end = min(total, start + page_size - 1)
    return module_sdk.i18n.t(
        "system.model.catalog.pagination.info",
        context={"start": start, "end": end, "total": total},
    )
