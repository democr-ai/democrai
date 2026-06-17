from __future__ import annotations

from typing import Any

from sqlalchemy import and_

from democrai.core.application.ai.engine.quotas.types import METRIC_TYPES
from democrai.core.application.ai.engine.quotas.types import SCOPE_ALL
from democrai.core.application.ai.engine.quotas.types import SCOPE_GUEST
from democrai.core.application.ai.engine.quotas.types import SCOPE_TYPES
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaCounter
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaLimit
from democrai.core.platform.utils.identity import to_optional_int


class EngineQuotaLimitsCoreModel(BaseCoreModel):
    name = "engine_quota_limits"
    sqlalchemy_model = EngineQuotaLimit

    def serialize_row(self, item: EngineQuotaLimit) -> dict[str, Any]:
        return {
            "id": item.id,
            "counter_id": item.counter_id,
            "engine_row_id": item.engine_row_id,
            "scope_type": item.scope_type,
            "scope_id": item.scope_id,
            "metric_type": item.metric_type,
            "limit_value": item.limit_value,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "counter_id", "type": "int"},
            {"field": "engine_row_id", "type": "int"},
            {"field": "scope_type", "type": "text"},
            {"field": "scope_id", "type": "int"},
            {"field": "metric_type", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "counter_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "engine_row_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "scope_type", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "scope_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "metric_type", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "limit_value", "type": "int", "filterable": False},
        ]

    def form_model_create(self) -> list[dict[str, Any]]:
        return [
            {"field": "counter_id", "type": "number", "required": True},
            {"field": "engine_row_id", "type": "number", "required": True},
            {
                "field": "scope_type",
                "type": "select",
                "required": True,
                "options": sorted(SCOPE_TYPES),
            },
            {"field": "scope_id", "type": "number", "required": False},
            {
                "field": "metric_type",
                "type": "select",
                "required": True,
                "options": sorted(METRIC_TYPES),
            },
            {"field": "limit_value", "type": "number", "required": True},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        scope_type = filters.get("scope_type")
        if isinstance(scope_type, str):
            query = query.filter(EngineQuotaLimit.scope_type == scope_type)
        metric_type = filters.get("metric_type")
        if isinstance(metric_type, str):
            query = query.filter(EngineQuotaLimit.metric_type == metric_type)
        for field_name in ("id", "counter_id", "engine_row_id", "scope_id"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is not None:
                query = query.filter(getattr(EngineQuotaLimit, field_name) == parsed)
        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        values = self._validated_values(payload)
        with SessionLocal() as session:
            self._ensure_references(session, values)
            self._ensure_unique_scope(session, values)
            row = EngineQuotaLimit(**values)
            session.add(row)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                EngineQuotaLimit.id == entity_id
            ).first()
            if row is None:
                return None
            values = self.serialize_row(row)
            values.update(payload)
            values = self._validated_values(values)
            self._ensure_references(session, values)
            self._ensure_unique_scope(session, values, exclude_id=entity_id)
            for key, value in values.items():
                setattr(row, key, value)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            row = self._apply_access_scope(self.base_query(session)).filter(
                EngineQuotaLimit.id == entity_id
            ).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True

    @staticmethod
    def _validated_values(payload: dict[str, Any]) -> dict[str, Any]:
        counter_id = to_optional_int(payload.get("counter_id"))
        engine_row_id = to_optional_int(payload.get("engine_row_id"))
        scope_type = str(payload.get("scope_type") or "").strip()
        scope_id = to_optional_int(payload.get("scope_id"))
        metric_type = str(payload.get("metric_type") or "").strip()
        limit_value = to_optional_int(payload.get("limit_value"))
        if counter_id is None:
            raise ValueError("counter_id is required")
        if engine_row_id is None:
            raise ValueError("engine_row_id is required")
        if scope_type not in SCOPE_TYPES:
            raise ValueError(f"engine quota scope_type unsupported:{scope_type}")
        if metric_type not in METRIC_TYPES:
            raise ValueError(f"engine quota metric_type unsupported:{metric_type}")
        if scope_type in {SCOPE_ALL, SCOPE_GUEST}:
            scope_id = None
        elif scope_id is None:
            raise ValueError("scope_id is required for this scope_type")
        if limit_value is None or limit_value < 0:
            raise ValueError("limit_value must be >= 0")
        return {
            "counter_id": counter_id,
            "engine_row_id": engine_row_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "metric_type": metric_type,
            "limit_value": limit_value,
        }

    @staticmethod
    def _ensure_references(session, values: dict[str, Any]) -> None:
        counter = (
            session.query(EngineQuotaCounter.id)
            .filter(EngineQuotaCounter.id == values["counter_id"])
            .first()
        )
        if counter is None:
            raise ValueError("counter_id does not exist")
        engine = (
            session.query(EngineRegistry.id)
            .filter(EngineRegistry.id == values["engine_row_id"])
            .first()
        )
        if engine is None:
            raise ValueError("engine_row_id does not exist")

    @staticmethod
    def _ensure_unique_scope(
        session,
        values: dict[str, Any],
        *,
        exclude_id: int | None = None,
    ) -> None:
        filters = [
            EngineQuotaLimit.counter_id == values["counter_id"],
            EngineQuotaLimit.engine_row_id == values["engine_row_id"],
            EngineQuotaLimit.scope_type == values["scope_type"],
            EngineQuotaLimit.metric_type == values["metric_type"],
        ]
        if values["scope_id"] is None:
            filters.append(EngineQuotaLimit.scope_id.is_(None))
        else:
            filters.append(EngineQuotaLimit.scope_id == values["scope_id"])
        if exclude_id is not None:
            filters.append(EngineQuotaLimit.id != exclude_id)
        duplicate = session.query(EngineQuotaLimit.id).filter(and_(*filters)).first()
        if duplicate is not None:
            raise ValueError("engine quota limit already exists for this scope")
