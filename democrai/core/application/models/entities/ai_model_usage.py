from __future__ import annotations

from typing import Any

from democrai.core.application.models.entities._observability import ObservabilityCoreModel
from democrai.core.infrastructure.storage.observability.models import AIModelUsageEvent
from democrai.core.platform.utils.normalize import FALSE_STRINGS, TRUE_STRINGS, normalize_key


class AIModelUsageCoreModel(ObservabilityCoreModel):
    name = "ai_model_usage"
    sqlalchemy_model = AIModelUsageEvent

    def _default_sort(self) -> tuple[str, str]:
        return ("timestamp", "desc")

    def serialize_row(self, item: AIModelUsageEvent) -> dict[str, Any]:
        return {
            "id": item.id,
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            "provider": item.provider,
            "model_name": item.model_name,
            "objective": item.objective,
            "request_kind": item.request_kind,
            "user_id": item.user_id,
            "total_tokens": item.total_tokens,
            "duration_ms": item.duration_ms,
            "success": item.success,
        }

    def serialize_detail(self, item: AIModelUsageEvent) -> dict[str, Any]:
        row = self.serialize_row(item)
        row["session_id"] = item.session_id
        row["node_id"] = item.node_id
        row["request_id"] = item.request_id
        row["correlation_id"] = item.correlation_id
        row["engine"] = item.engine
        row["deployment_mode"] = item.deployment_mode
        row["agent_id"] = item.agent_id
        row["prompt_tokens"] = item.prompt_tokens
        row["completion_tokens"] = item.completion_tokens
        row["error"] = item.error
        row["channel"] = item.channel
        return row

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "provider", "type": "text"},
            {"field": "model_name", "type": "text"},
            {"field": "objective", "type": "text"},
            {"field": "request_kind", "type": "text"},
            {"field": "success", "type": "bool"},
            {"field": "user_id", "type": "int"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {
                "field": "timestamp",
                "type": "str",
                "filterable": False,
                "transform": "date:%d/%m/%Y %H:%M",
            },
            {"field": "provider", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "model_name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "objective", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "request_kind", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "total_tokens", "type": "int", "filterable": False},
            {"field": "duration_ms", "type": "float", "filterable": False},
            {
                "field": "success",
                "type": "bool",
                "filterable": True,
                "filter_type": "boolean",
            },
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in ("provider", "model_name", "objective", "request_kind"):
            value = filters.get(field_name)
            if isinstance(value, str):
                query = query.filter(
                    getattr(AIModelUsageEvent, field_name).ilike(f"%{value}%")
                )

        success = filters.get("success")
        if success is not None:
            if isinstance(success, str):
                normalized = normalize_key(success)
                if normalized in TRUE_STRINGS:
                    query = query.filter(AIModelUsageEvent.success == 1)
                elif normalized in FALSE_STRINGS:
                    query = query.filter(AIModelUsageEvent.success == 0)
            elif isinstance(success, bool):
                query = query.filter(AIModelUsageEvent.success == (1 if success else 0))

        user_id = filters.get("user_id")
        if user_id is not None:
            try:
                query = query.filter(AIModelUsageEvent.user_id == int(user_id))
            except (TypeError, ValueError):
                pass

        return query
