from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database.models import EngineNodeInstallRegistry


class EngineNodeInstallRegistryCoreModel(BaseCoreModel):
    name = "engine_node_install_registry"
    sqlalchemy_model = EngineNodeInstallRegistry

    def _default_sort(self) -> tuple[str, str]:
        return ("updated_at", "desc")

    def serialize_row(self, item: EngineNodeInstallRegistry) -> dict[str, Any]:
        return {
            "id": item.id,
            "engine_id": item.engine_id,
            "node_id": item.node_id,
            "status": item.status,
            "last_event_id": item.last_event_id,
            "last_error": item.last_error,
            "manifest_version": item.manifest_version,
            "install_started_at": (
                item.install_started_at.isoformat() if item.install_started_at else None
            ),
            "install_completed_at": (
                item.install_completed_at.isoformat()
                if item.install_completed_at
                else None
            ),
            "last_heartbeat_at": (
                item.last_heartbeat_at.isoformat() if item.last_heartbeat_at else None
            ),
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "engine_id", "type": "text"},
            {"field": "node_id", "type": "text"},
            {"field": "status", "type": "text"},
            {"field": "last_event_id", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": True, "filter_type": "text"},
            {
                "field": "engine_id",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "node_id",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "status",
                "type": "str",
                "filterable": True,
                "filter_type": "select",
                "options": ["pending", "installing", "installed", "error"],
            },
            {"field": "updated_at", "type": "str", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in ("engine_id", "node_id", "status", "last_event_id"):
            value = filters.get(field_name)
            if isinstance(value, str) and value.strip():
                query = query.filter(
                    getattr(EngineNodeInstallRegistry, field_name).ilike(
                        f"%{value.strip()}%"
                    )
                )

        raw_id = filters.get("id")
        if raw_id is not None:
            try:
                parsed_id = int(raw_id)
            except (TypeError, ValueError):
                parsed_id = None
            if parsed_id is not None:
                query = query.filter(EngineNodeInstallRegistry.id == parsed_id)

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("engine_node_install_registry is read-only")

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("engine_node_install_registry is read-only")

    def delete(self, entity_id: int) -> bool:
        raise NotImplementedError("engine_node_install_registry is read-only")
