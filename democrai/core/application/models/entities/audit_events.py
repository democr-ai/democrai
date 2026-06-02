from __future__ import annotations

from typing import Any

from democrai.core.application.auth.roles import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
)
from democrai.core.application.models.entities._observability import ObservabilityCoreModel
from democrai.core.infrastructure.storage.observability.models import AuditEvent


class AuditEventsCoreModel(ObservabilityCoreModel):
    name = "audit_events"
    sqlalchemy_model = AuditEvent

    def _default_sort(self) -> tuple[str, str]:
        return ("timestamp", "desc")

    def serialize_row(self, item: AuditEvent) -> dict[str, Any]:
        return {
            "id": item.id,
            "timestamp": item.timestamp.isoformat() if item.timestamp else None,
            "event_type": item.event_type,
            "actor_user_id": item.actor_user_id,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "operation": item.operation,
            "status": item.status,
        }

    def serialize_detail(self, item: AuditEvent) -> dict[str, Any]:
        row = self.serialize_row(item)
        row["actor_role"] = item.actor_role
        row["organization_id"] = item.organization_id
        row["session_id"] = item.session_id
        row["request_id"] = item.request_id
        row["correlation_id"] = item.correlation_id
        row["client_ip"] = item.client_ip
        row["channel"] = item.channel
        return row

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "event_type", "type": "text"},
            {"field": "actor_user_id", "type": "int"},
            {"field": "entity_type", "type": "text"},
            {"field": "entity_id", "type": "text"},
            {"field": "operation", "type": "text"},
            {"field": "status", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {
                "field": "timestamp",
                "type": "str",
                "filterable": False,
                "transform": "date:%d/%m/%Y %H:%M",
            },
            {"field": "event_type", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "actor_user_id", "type": "int", "filterable": True, "filter_type": "text"},
            {"field": "entity_type", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "entity_id", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "operation", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "status", "type": "str", "filterable": True, "filter_type": "text"},
        ]

    def _apply_access_scope(self, query):
        if self.ctx.bypass:
            return query

        level = int(self.ctx.access_level or 3)
        if level == ROLE_LEVEL_SUPER:
            return query

        if level == ROLE_LEVEL_ORGANIZATION:
            return query.filter(AuditEvent.organization_id == self.ctx.organization_id)

        return query.filter(AuditEvent.actor_user_id == self.ctx.user_id)

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in ("event_type", "entity_type", "entity_id", "operation", "status"):
            value = filters.get(field_name)
            if isinstance(value, str):
                query = query.filter(
                    getattr(AuditEvent, field_name).ilike(f"%{value}%")
                )

        actor_user_id = filters.get("actor_user_id")
        if actor_user_id is not None:
            try:
                query = query.filter(AuditEvent.actor_user_id == int(actor_user_id))
            except (TypeError, ValueError):
                pass

        return query
