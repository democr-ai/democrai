from __future__ import annotations


TABLE_HEADER_KEYS = {
    "actor_user_id": "monitor.table.actor",
    "duration_ms": "monitor.table.duration_ms",
    "entity_id": "monitor.table.entity_id",
    "entity_type": "monitor.table.entity",
    "event_type": "monitor.table.event",
    "id": "monitor.table.id",
    "label": "monitor.table.label",
    "model_name": "monitor.table.model",
    "module": "monitor.table.module",
    "name": "monitor.table.step",
    "objective": "monitor.table.objective",
    "operation": "monitor.table.operation",
    "pipeline_id": "monitor.table.pipeline",
    "progress": "monitor.table.progress",
    "provider": "monitor.table.provider",
    "request_id": "monitor.table.request",
    "request_kind": "monitor.table.request_kind",
    "status": "monitor.table.status",
    "success": "monitor.table.success",
    "timestamp": "monitor.table.when",
    "total_tokens": "monitor.table.tokens",
    "type": "monitor.table.type",
    "updated_at": "monitor.table.updated",
}


def translated_table_model(module_sdk, model: list[dict]) -> list[dict]:
    translated: list[dict] = []
    for column in model:
        item = dict(column)
        key = TABLE_HEADER_KEYS.get(str(item.get("field") or ""))
        if key:
            item["header"] = module_sdk.i18n.t(key)
        translated.append(item)
    return translated


def table_state_from_params(
    params: dict,
    table_id: str,
    *,
    default_page_size: int = 40,
    default_sort_field: str = "updated_at",
) -> tuple[int, int, dict[str, str], dict[str, str]]:
    prefix = f"{table_id}["

    def _get(name: str, default: str = "") -> str:
        return str(params.get(f"{table_id}[{name}]", default) or default)

    try:
        page = max(0, int(_get("page", "0") or 0))
    except (TypeError, ValueError):
        page = 0
    try:
        page_size = max(1, min(int(_get("page_size", str(default_page_size)) or default_page_size), 200))
    except (TypeError, ValueError):
        page_size = default_page_size

    filters: dict[str, str] = {}
    for key, value in params.items():
        field = str(key or "")
        if not field.startswith(prefix) or field in {
            f"{table_id}[page]",
            f"{table_id}[page_size]",
            f"{table_id}[sort_field]",
            f"{table_id}[sort_direction]",
        }:
            continue
        if not field.endswith("]"):
            continue
        inner_field = field[len(prefix) : -1].strip()
        normalized_value = str(value or "").strip()
        if inner_field and normalized_value:
            filters[inner_field] = normalized_value

    sort_field = _get("sort_field", default_sort_field).strip() or default_sort_field
    sort_direction = _get("sort_direction", "desc").strip().lower()
    if sort_direction not in {"asc", "desc"}:
        sort_direction = "desc"
    sort = {"field": sort_field, "direction": sort_direction}
    return page, page_size, filters, sort
