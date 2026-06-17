from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.quotas.types import PERIOD_UNITS
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaCounter


class EngineQuotaCountersCoreModel(BaseCoreModel):
    name = "engine_quota_counters"
    sqlalchemy_model = EngineQuotaCounter

    def serialize_row(self, item: EngineQuotaCounter) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "period_unit": item.period_unit,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "period_unit", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "period_unit",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {"field": "created_at", "type": "str", "filterable": False},
            {"field": "updated_at", "type": "str", "filterable": False},
        ]

    def form_model_create(self) -> list[dict[str, Any]]:
        return [
            {"field": "name", "type": "text", "required": True},
            {
                "field": "period_unit",
                "type": "select",
                "required": True,
                "options": sorted(PERIOD_UNITS),
            },
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(EngineQuotaCounter.name.ilike(f"%{name}%"))
        period_unit = filters.get("period_unit")
        if isinstance(period_unit, str):
            query = query.filter(EngineQuotaCounter.period_unit == period_unit)
        try:
            counter_id = int(filters.get("id")) if filters.get("id") is not None else None
        except (TypeError, ValueError):
            counter_id = None
        if counter_id is not None:
            query = query.filter(EngineQuotaCounter.id == counter_id)
        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        period_unit = str(payload.get("period_unit") or "").strip()
        self._validate_payload(name=name, period_unit=period_unit)
        with SessionLocal() as session:
            duplicate = (
                session.query(EngineQuotaCounter)
                .filter(EngineQuotaCounter.name == name)
                .first()
            )
            if duplicate is not None:
                raise ValueError("engine quota counter name already exists")
            row = EngineQuotaCounter(name=name, period_unit=period_unit)
            session.add(row)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                EngineQuotaCounter.id == entity_id
            ).first()
            if row is None:
                return None
            name = row.name
            period_unit = row.period_unit
            if "name" in payload:
                name = str(payload.get("name") or "").strip()
            if "period_unit" in payload:
                period_unit = str(payload.get("period_unit") or "").strip()
            self._validate_payload(name=name, period_unit=period_unit)
            duplicate = (
                session.query(EngineQuotaCounter)
                .filter(EngineQuotaCounter.name == name, EngineQuotaCounter.id != entity_id)
                .first()
            )
            if duplicate is not None:
                raise ValueError("engine quota counter name already exists")
            row.name = name
            row.period_unit = period_unit
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                EngineQuotaCounter.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    @staticmethod
    def _validate_payload(*, name: str, period_unit: str) -> None:
        if not name:
            raise ValueError("name is required")
        if period_unit not in PERIOD_UNITS:
            raise ValueError(f"engine quota period_unit unsupported:{period_unit}")
