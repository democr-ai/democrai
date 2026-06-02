from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AICapability


_CAPABILITY_ORDER = [
    AICapability.CHAT,
    AICapability.TOOL_CALLING,
    AICapability.REASONING,
    AICapability.DETECTION,
    AICapability.IMAGE_TO_TEXT,
    AICapability.EMBEDDING,
    AICapability.AUDIO,
    AICapability.TTS,
    AICapability.STT,
]

_ALLOWED_CAPABILITIES = set(_CAPABILITY_ORDER)
_MAX_PRIORITY = 3


def _normalize_capability(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalize_capability_list(raw: Any) -> list[str]:
    values: list[str] = []
    if isinstance(raw, list):
        values = [str(item or "") for item in raw]
    elif isinstance(raw, str):
        values = [part for part in raw.split(",")]

    normalized: list[str] = []
    seen: set[str] = set()
    for item in values:
        capability = _normalize_capability(item)
        if not capability or capability in seen:
            continue
        seen.add(capability)
        normalized.append(capability)
    return normalized


def _ordered_capabilities(items: set[str]) -> list[str]:
    explicit = [cap for cap in _CAPABILITY_ORDER if cap in items]
    extras = sorted(cap for cap in items if cap not in _ALLOWED_CAPABILITIES)
    return [*explicit, *extras]


def _paginate_model_list(
    module_sdk, model_name: str, filters: dict[str, Any]
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 0
    page_size = 200
    model = getattr(module_sdk.models, model_name)
    while True:
        listing = model.list(page=page, page_size=page_size, filters=filters)
        rows = listing.get("rows") or []
        for row in rows:
            if isinstance(row, dict):
                items.append(row)
        total_rows = int(listing.get("total_rows") or 0)
        if len(items) >= total_rows or not rows:
            break
        page += 1
    return items


def list_capabilities(module_sdk) -> list[str]:
    active_models = _paginate_model_list(
        module_sdk,
        "model_registry",
        {"status": "active"},
    )
    capabilities: set[str] = set()
    for row in active_models:
        for cap in _normalize_capability_list(row.get("capabilities")):
            capabilities.add(cap)
    return _ordered_capabilities(capabilities)


def _active_models_by_id(module_sdk, capability: str) -> dict[int, dict[str, Any]]:
    active_models = _paginate_model_list(
        module_sdk,
        "model_registry",
        {"status": "active"},
    )
    matched: dict[int, dict[str, Any]] = {}
    for row in active_models:
        model_id = int(row["id"])
        caps = _normalize_capability_list(row.get("capabilities"))
        if capability in caps:
            matched[model_id] = row
    return matched


def _priority_rows_for_capability(module_sdk, capability: str) -> list[dict[str, Any]]:
    rows = _paginate_model_list(
        module_sdk,
        "model_capability_priority",
        {"capability": capability},
    )
    rows.sort(
        key=lambda row: (
            int(row["priority"]),
            int(row["model_id"]),
            int(row["id"]),
        )
    )
    return rows


def _engine_map(module_sdk) -> dict[int, dict[str, Any]]:
    rows = _paginate_model_list(module_sdk, "engine_registry", {})
    by_id: dict[int, dict[str, Any]] = {}
    for row in rows:
        engine_id = int(row["id"])
        by_id[engine_id] = row
    return by_id


def _engine_display_name(row: dict[str, Any], engine_id: int) -> str:
    return (
        str(
            row.get("name")
            or row.get("label")
            or row.get("provider_name")
            or row.get("provider")
            or ""
        ).strip()
        or f"engine_{engine_id}"
    )


def _model_display_name(row: dict[str, Any], model_id: int) -> str:
    available_model = (
        row.get("available_model")
        if isinstance(row.get("available_model"), dict)
        else {}
    )
    extra_config = (
        row.get("extra_config") if isinstance(row.get("extra_config"), dict) else {}
    )
    embedded_available = (
        extra_config.get("available_model")
        if isinstance(extra_config.get("available_model"), dict)
        else {}
    )
    for source in (available_model, embedded_available, row):
        value = str(source.get("label") or source.get("name") or "").strip()
        if value:
            return value
    return f"model_{model_id}"


def _model_option_label(
    model_row: dict[str, Any],
    *,
    engine_by_id: dict[int, dict[str, Any]],
) -> str:
    model_id = int(model_row["id"])
    engine_id = int(model_row["engine_id"])
    model_name = _model_display_name(model_row, model_id)
    engine_name = _engine_display_name(engine_by_id.get(engine_id, {}), engine_id)
    if engine_name:
        return f"{model_name} ({engine_name})"
    return model_name


def _selected_priority_values(
    priority_rows: list[dict[str, Any]],
    active_models: dict[int, dict[str, Any]],
) -> dict[str, str]:
    values = {f"priority_{index}": "" for index in range(1, _MAX_PRIORITY + 1)}
    for row in priority_rows:
        priority = int(row["priority"])
        if priority < 1 or priority > _MAX_PRIORITY:
            continue
        model_id = int(row["model_id"])
        if model_id in active_models:
            values[f"priority_{priority}"] = str(model_id)
    return values


def _empty_option(module_sdk) -> dict[str, str]:
    return {
        "label": module_sdk.i18n.t("system.capabilities.priority.option.none"),
        "value": "",
    }


def capability_priority_form_data(module_sdk, capability: str) -> dict[str, Any]:
    normalized = _normalize_capability(capability)
    if not normalized:
        return {
            "capability": "",
            "options": [],
            "values": {},
            "has_models": False,
        }

    active_models = _active_models_by_id(module_sdk, normalized)
    priority_rows = _priority_rows_for_capability(module_sdk, normalized)
    engine_by_id = _engine_map(module_sdk)

    options = [_empty_option(module_sdk)]
    for model_id in sorted(active_models):
        model_row = active_models[model_id]
        options.append(
            {
                "label": _model_option_label(model_row, engine_by_id=engine_by_id),
                "value": str(model_id),
            }
        )

    values = _selected_priority_values(priority_rows, active_models)
    return {
        "capability": normalized,
        "options": options,
        "values": values,
        "has_models": bool(active_models),
    }


def _optional_model_id(value: Any) -> int | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    return int(raw)


def save_capability_priorities(
    module_sdk,
    capability: str,
    *,
    priority_1: Any = None,
    priority_2: Any = None,
    priority_3: Any = None,
) -> None:
    normalized = _normalize_capability(capability)
    if not normalized:
        raise ValueError("capability_required")

    active_models = _active_models_by_id(module_sdk, normalized)
    selected = [
        _optional_model_id(priority_1),
        _optional_model_id(priority_2),
        _optional_model_id(priority_3),
    ]
    selected_ids = [model_id for model_id in selected if model_id is not None]
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("duplicate_model")
    if any(model_id not in active_models for model_id in selected_ids):
        raise ValueError("invalid_model")

    for row in _priority_rows_for_capability(module_sdk, normalized):
        module_sdk.models.model_capability_priority.delete(int(row["id"]))

    for priority, model_id in enumerate(selected, start=1):
        if model_id is None:
            continue
        module_sdk.models.model_capability_priority.create(
            {
                "capability": normalized,
                "model_id": model_id,
                "priority": priority,
            }
        )
