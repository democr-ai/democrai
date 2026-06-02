from __future__ import annotations

from typing import Any

from democrai.core.application.ai.constants import normalize_capability
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ModelCapabilityPriority, ModelRegistry
from democrai.core.platform.utils.identity import to_optional_int


class ModelCapabilityPriorityCoreModel(BaseCoreModel):
    name = "model_capability_priority"
    sqlalchemy_model = ModelCapabilityPriority

    def serialize_row(self, item: ModelCapabilityPriority) -> dict[str, Any]:
        return {
            "id": item.id,
            "capability": item.capability,
            "model_id": item.model_id,
            "priority": item.priority,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "capability", "type": "text"},
            {"field": "model_id", "type": "int"},
            {"field": "priority", "type": "int"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "capability", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "model_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "priority", "type": "int", "filterable": True, "filter_type": "int"},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        capability = normalize_capability(filters.get("capability"))
        if capability:
            query = query.filter(ModelCapabilityPriority.capability == capability)

        for field_name in ("id", "model_id", "priority"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is None:
                continue
            query = query.filter(getattr(ModelCapabilityPriority, field_name) == parsed)

        return query

    def _ensure_model_exists(self, session, model_id: int) -> None:
        exists = session.query(ModelRegistry.id).filter(ModelRegistry.id == model_id).first()
        if exists is None:
            raise ValueError("model_id does not exist")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        capability = normalize_capability(payload.get("capability"))
        model_id = to_optional_int(payload.get("model_id"))
        priority = to_optional_int(payload.get("priority"))
        if not capability or model_id is None or priority is None:
            raise ValueError("capability, model_id and priority are required")
        if priority <= 0:
            raise ValueError("priority must be >= 1")

        with SessionLocal() as session:
            self._ensure_model_exists(session, model_id)
            duplicate_model = (
                session.query(ModelCapabilityPriority)
                .filter(
                    ModelCapabilityPriority.capability == capability,
                    ModelCapabilityPriority.model_id == model_id,
                )
                .first()
            )
            if duplicate_model is not None:
                raise ValueError("capability/model pair already exists")

            duplicate_priority = (
                session.query(ModelCapabilityPriority)
                .filter(
                    ModelCapabilityPriority.capability == capability,
                    ModelCapabilityPriority.priority == priority,
                )
                .first()
            )
            if duplicate_priority is not None:
                raise ValueError("priority already assigned for capability")

            row = ModelCapabilityPriority(
                capability=capability,
                model_id=model_id,
                priority=priority,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        return result

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ModelCapabilityPriority.id == entity_id
            ).first()
            if row is None:
                return None

            capability = row.capability
            model_id = row.model_id
            priority = row.priority

            if "capability" in payload:
                capability = normalize_capability(payload.get("capability"))
                if not capability:
                    raise ValueError("capability is required")
            if "model_id" in payload:
                parsed_model_id = to_optional_int(payload.get("model_id"))
                if parsed_model_id is None:
                    raise ValueError("model_id is required")
                self._ensure_model_exists(session, parsed_model_id)
                model_id = parsed_model_id
            if "priority" in payload:
                parsed_priority = to_optional_int(payload.get("priority"))
                if parsed_priority is None:
                    raise ValueError("priority is required")
                if parsed_priority <= 0:
                    raise ValueError("priority must be >= 1")
                priority = parsed_priority

            duplicate_model = (
                session.query(ModelCapabilityPriority)
                .filter(
                    ModelCapabilityPriority.capability == capability,
                    ModelCapabilityPriority.model_id == model_id,
                    ModelCapabilityPriority.id != entity_id,
                )
                .first()
            )
            if duplicate_model is not None:
                raise ValueError("capability/model pair already exists")

            duplicate_priority = (
                session.query(ModelCapabilityPriority)
                .filter(
                    ModelCapabilityPriority.capability == capability,
                    ModelCapabilityPriority.priority == priority,
                    ModelCapabilityPriority.id != entity_id,
                )
                .first()
            )
            if duplicate_priority is not None:
                raise ValueError("priority already assigned for capability")

            row.capability = capability
            row.model_id = model_id
            row.priority = priority

            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        return result

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ModelCapabilityPriority.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
        return True
