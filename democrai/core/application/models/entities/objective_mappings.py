from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ModelRegistry, ObjectiveMapping
from democrai.core.platform.utils.identity import to_optional_int


class ObjectiveMappingsCoreModel(BaseCoreModel):
    name = "objective_mappings"
    sqlalchemy_model = ObjectiveMapping

    def serialize_row(self, item: ObjectiveMapping) -> dict[str, Any]:
        return {
            "id": item.id,
            "objective": item.objective,
            "model_id": item.model_id,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "objective", "type": "text"},
            {"field": "model_id", "type": "int"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "objective", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "model_id", "type": "int", "filterable": True, "filter_type": "int"},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        objective = filters.get("objective")
        if isinstance(objective, str):
            query = query.filter(ObjectiveMapping.objective.ilike(f"%{objective}%"))

        for field_name in ("id", "model_id"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is None:
                continue
            query = query.filter(getattr(ObjectiveMapping, field_name) == parsed)

        return query

    def _ensure_model_exists(self, session, model_id: int) -> None:
        exists = session.query(ModelRegistry.id).filter(ModelRegistry.id == model_id).first()
        if exists is None:
            raise ValueError("model_id does not exist")

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        objective = str(payload.get("objective") or "").strip()
        model_id = to_optional_int(payload.get("model_id"))
        if not objective or model_id is None:
            raise ValueError("objective and model_id are required")

        with SessionLocal() as session:
            duplicate = (
                session.query(ObjectiveMapping)
                .filter(ObjectiveMapping.objective == objective)
                .first()
            )
            if duplicate is not None:
                raise ValueError("objective already mapped")
            self._ensure_model_exists(session, model_id)

            row = ObjectiveMapping(objective=objective, model_id=model_id)
            session.add(row)
            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        return result

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ObjectiveMapping.id == entity_id
            ).first()
            if row is None:
                return None

            if "objective" in payload:
                objective = str(payload.get("objective") or "").strip()
                if not objective:
                    raise ValueError("objective is required")
                duplicate = (
                    session.query(ObjectiveMapping)
                    .filter(
                        ObjectiveMapping.objective == objective,
                        ObjectiveMapping.id != entity_id,
                    )
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("objective already mapped")
                row.objective = objective

            if "model_id" in payload:
                model_id = to_optional_int(payload.get("model_id"))
                if model_id is None:
                    raise ValueError("model_id is required")
                self._ensure_model_exists(session, model_id)
                row.model_id = model_id

            session.commit()
            session.refresh(row)
            result = self.serialize_detail(row)
        return result

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                ObjectiveMapping.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
        return True
