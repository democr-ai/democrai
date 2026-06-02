from __future__ import annotations

from typing import Any

from modules.system.utils.actions.engine.models import parse_capabilities


def engine_name(engine_id: Any, engines_by_id: dict[int, dict[str, Any]]) -> str:
    try:
        engine = engines_by_id.get(int(engine_id))
    except (TypeError, ValueError):
        engine = None
    if not isinstance(engine, dict):
        return ""
    return str(
        engine.get("name")
        or engine.get("label")
        or engine.get("provider_name")
        or engine.get("provider")
        or ""
    ).strip()


def available_model_name(row: dict[str, Any]) -> str:
    available_model = (
        row.get("available_model") if isinstance(row.get("available_model"), dict) else {}
    )
    extra_config = row.get("extra_config") if isinstance(row.get("extra_config"), dict) else {}
    embedded_available = (
        extra_config.get("available_model")
        if isinstance(extra_config.get("available_model"), dict)
        else {}
    )
    for source in (available_model, embedded_available, row):
        value = str(source.get("label") or source.get("name") or "").strip()
        if value:
            return value
    return ""


def engine_rows_by_id(module_sdk) -> dict[int, dict[str, Any]]:
    rows = module_sdk.models.engine_registry.all(
        sort={"field": "name", "direction": "asc"},
    ).get("rows") or []
    result: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            result[int(row["id"])] = row
        except (KeyError, TypeError, ValueError):
            continue
    return result


def active_model_items(
    rows: list[dict[str, Any]],
    engines_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        resolved_engine_name = engine_name(row.get("engine_id"), engines_by_id)
        model_name = available_model_name(row)
        capabilities = parse_capabilities(row.get("capabilities"))
        meta = " | ".join(
            item
            for item in [
                f"Engine: {resolved_engine_name}" if resolved_engine_name else "",
                f"Capabilities: {', '.join(capabilities)}" if capabilities else "",
                str(row.get("status") or "").strip(),
            ]
            if item
        )
        items.append(
            {
                "id": int(row["id"]),
                "model_row_id": int(row["id"]),
                "title": model_name,
                "text": meta,
                "engine_name": resolved_engine_name,
                "model_name": model_name,
                "icon": "ric.checkbox-circle-line",
                "icon_color": "#22C55E",
            }
        )
    return items


def loaded_model_items(
    rows: list[dict[str, Any]],
    engines_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        engine_row_id = int(row.get("engine_row_id") or 0)
        if engine_row_id <= 0:
            continue
        model_registry_id = int(row.get("model_registry_id") or 0)
        if model_registry_id <= 0:
            continue
        resolved_engine_name = engine_name(engine_row_id, engines_by_id)
        config = row.get("config") if isinstance(row.get("config"), dict) else {}
        model_name = str(
            row.get("model_display_name")
            or row.get("model_registry_name")
            or config.get("model")
            or row.get("model")
            or row.get("model_path")
            or ""
        ).strip()
        meta = " | ".join(
            item
            for item in [
                f"Engine: {resolved_engine_name}" if resolved_engine_name else "",
                f"PID: {row.get('pid')}" if row.get("pid") else "",
                str(row.get("status") or "").strip(),
            ]
            if item
        )
        items.append(
            {
                "id": model_registry_id,
                "engine_row_id": engine_row_id,
                "model_registry_id": model_registry_id,
                "title": model_name or resolved_engine_name,
                "text": meta,
                "engine_name": resolved_engine_name,
                "model_name": model_name,
                "icon": "ric.cpu-line",
                "icon_color": "#3B82F6",
            }
        )
    return items


def active_job_items(
    rows: list[dict[str, Any]],
    engines_by_id: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        request_id = str(row.get("request_id") or "").strip()
        if not request_id:
            continue
        engine_row_id = row.get("engine_row_id")
        resolved_engine_name = (
            engine_name(engine_row_id, engines_by_id)
            if engine_row_id is not None
            else ""
        )
        status = str(row.get("status") or "").strip()
        method = str(row.get("method") or "").strip()
        selector = str(row.get("selector_type") or "").strip()
        model_registry_id = row.get("model_registry_id")
        meta = " | ".join(
            item
            for item in [
                f"Engine: {resolved_engine_name}" if resolved_engine_name else "",
                f"Model row: {model_registry_id}" if model_registry_id else "",
                f"Selector: {selector}" if selector else "",
                f"Mode: {row.get('response_mode')}" if row.get("response_mode") else "",
                status,
            ]
            if item
        )
        items.append(
            {
                "id": request_id,
                "request_id": request_id,
                "pipeline_id": row.get("pipeline_id"),
                "title": method or request_id,
                "text": meta,
                "engine_name": resolved_engine_name,
                "status": status,
                "icon": "ric.loader-4-line",
                "icon_color": "#F59E0B",
            }
        )
    return items
