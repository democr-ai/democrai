from __future__ import annotations

from typing import Any

from democrai.core.application.models.entities._observability import ObservabilityCoreModel
from democrai.core.infrastructure.storage.observability.models import AIModelPipelineStep


class AIModelPipelineStepsCoreModel(ObservabilityCoreModel):
    name = "ai_model_pipeline_steps"
    sqlalchemy_model = AIModelPipelineStep

    def _default_sort(self) -> tuple[str, str]:
        return ("timestamp", "asc")

    def serialize_row(self, item: AIModelPipelineStep) -> dict[str, Any]:
        return {
            "id": item.id,
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            "pipeline_id": item.pipeline_id,
            "request_id": item.request_id,
            "step_id": item.step_id,
            "parent_step_id": item.parent_step_id,
            "root_method": item.root_method,
            "type": item.type,
            "name": item.name,
            "status": item.status,
            "duration_ms": item.duration_ms,
            "provider": item.provider,
            "engine": item.engine,
            "model_registry_id": item.model_registry_id,
            "model_name": item.model_name,
            "error": item.error,
            "input_hash": item.input_hash,
            "output_hash": item.output_hash,
            "input_size_bytes": item.input_size_bytes,
            "output_size_bytes": item.output_size_bytes,
            "archive_status": item.archive_status,
            "archive_media_path": item.archive_media_path,
            "archive_error": item.archive_error,
        }

    def serialize_detail(self, item: AIModelPipelineStep) -> dict[str, Any]:
        row = self.serialize_row(item)
        row["input_json"] = item.input_json
        row["output_json"] = item.output_json
        row["stats_json"] = item.stats_json
        row["metadata_json"] = item.metadata_json
        return row

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "pipeline_id", "type": "text"},
            {"field": "request_id", "type": "text"},
            {"field": "type", "type": "text"},
            {"field": "name", "type": "text"},
            {"field": "status", "type": "text"},
            {"field": "provider", "type": "text"},
            {"field": "model_name", "type": "text"},
            {"field": "model_registry_id", "type": "int"},
            {"field": "archive_status", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {
                "field": "timestamp",
                "type": "str",
                "filterable": False,
                "transform": "date:%H:%M:%S",
            },
            {"field": "type", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "status", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "duration_ms", "type": "float", "filterable": False},
            {"field": "provider", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "model_name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "archive_status", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "error", "type": "str", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in (
            "pipeline_id",
            "request_id",
            "type",
            "name",
            "status",
            "provider",
            "model_name",
            "archive_status",
        ):
            value = filters.get(field_name)
            if isinstance(value, str):
                query = query.filter(getattr(AIModelPipelineStep, field_name) == value)

        model_registry_id = filters.get("model_registry_id")
        if model_registry_id is not None:
            query = query.filter(
                AIModelPipelineStep.model_registry_id == int(model_registry_id)
            )

        return query
