from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.orm import Query
from sqlalchemy import desc

from democrai.core.application.models.context import CoreModelContext
from democrai.core.application.auth.roles import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
)
from democrai.core.infrastructure.database import SessionLocal


class BaseCoreModel(ABC):
    """
    Contract for core DB-backed models exposed to SDK.
    """

    name: str = ""
    sqlalchemy_model = None

    def __init__(self, ctx: CoreModelContext):
        self.ctx = ctx

    # ---- Query and serialization hooks ----
    def _session_factory(self):
        return SessionLocal

    def base_query(self, session) -> Query:
        return session.query(self.sqlalchemy_model)

    @abstractmethod
    def serialize_row(self, item: Any) -> dict[str, Any]:
        raise NotImplementedError

    def serialize_detail(self, item: Any) -> dict[str, Any]:
        return self.serialize_row(item)

    # ---- UI schema hooks ----
    def form_model_create(self) -> list[dict[str, Any]]:
        return []

    def form_model_update(self, entity_id: int) -> list[dict[str, Any]]:
        return self.form_model_create()

    def form_model_extra(self, name: str) -> list[dict[str, Any]]:
        return []

    def filters_model(self) -> list[dict[str, Any]]:
        return []

    def table_model(self) -> list[dict[str, Any]]:
        return []

    def _default_sort(self) -> tuple[str, str]:
        return ("id", "asc")

    # ---- Access / filters ----
    def _apply_access_scope(self, query: Query) -> Query:
        if self.ctx.bypass:
            return query

        model = self.sqlalchemy_model
        level = self.ctx.access_level
        if level == ROLE_LEVEL_SUPER:
            return query

        if (
            level == ROLE_LEVEL_ORGANIZATION
            and self.ctx.organization_id is not None
            and hasattr(model, "organization_id")
        ):
            return query.filter(model.organization_id == self.ctx.organization_id)

        if hasattr(model, "user_id"):
            return query.filter(model.user_id == self.ctx.user_id)

        return query

    def _allowed_filter_fields(self) -> set[str]:
        allowed: set[str] = set()
        for item in self.filters_model() or []:
            if isinstance(item, dict):
                field_name = str(item.get("field") or "").strip()
                if field_name:
                    allowed.add(field_name)
        return allowed

    def _normalize_filters(self, filters: dict[str, Any] | None) -> dict[str, Any]:
        raw = {} if filters is None else filters
        if not isinstance(raw, dict):
            return {}
        allowed = self._allowed_filter_fields()
        normalized: dict[str, Any] = {}
        for key, value in raw.items():
            field_name = str(key or "").strip()
            if not field_name or field_name not in allowed:
                continue
            if value is None:
                continue
            if isinstance(value, dict):
                value = value.get("value", value.get("q"))
            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    continue
            normalized[field_name] = value
        return normalized

    def _apply_filters(self, query: Query, filters: dict[str, Any]) -> Query:
        model = self.sqlalchemy_model
        for field_name, value in filters.items():
            if not hasattr(model, field_name):
                continue
            column = getattr(model, field_name)
            if isinstance(value, str):
                query = query.filter(column.ilike(f"%{value}%"))
            else:
                query = query.filter(column == value)
        return query

    def _normalize_sort(self, sort: dict[str, Any] | None) -> dict[str, str]:
        raw = {} if sort is None else sort
        if not isinstance(raw, dict):
            raw = {}
        field = str(raw.get("field") or raw.get("sortField") or "").strip()
        direction = (
            str(raw.get("direction") or raw.get("sortDirection") or "").strip().lower()
        )
        if not field:
            default_field, default_direction = self._default_sort()
            return {"field": default_field, "direction": default_direction}
        if direction not in {"asc", "desc"}:
            direction = "asc"
        sortable_fields = {
            str(item.get("field") or "").strip()
            for item in (self.table_model() or [])
            if isinstance(item, dict) and str(item.get("field") or "").strip()
        }
        if field not in sortable_fields or not hasattr(self.sqlalchemy_model, field):
            default_field, default_direction = self._default_sort()
            return {"field": default_field, "direction": default_direction}
        return {"field": field, "direction": direction}

    def _apply_sort(self, query: Query, sort: dict[str, str]) -> Query:
        field = str(sort.get("field") or "").strip()
        if not field or not hasattr(self.sqlalchemy_model, field):
            default_field, default_direction = self._default_sort()
            field = default_field
            sort = {"field": field, "direction": default_direction}
        column = getattr(self.sqlalchemy_model, field)
        direction = str(sort.get("direction") or "asc").strip().lower()
        if direction == "desc":
            return query.order_by(desc(column))
        return query.order_by(column.asc())

    # ---- Standard methods ----
    def view(self, entity_id: int) -> dict[str, Any] | None:
        with self._session_factory()() as session:
            query = self._apply_access_scope(self.base_query(session))
            item = query.filter(self.sqlalchemy_model.id == entity_id).first()
            if item is None:
                return None
            return self.serialize_detail(item)

    def count(
        self,
        *,
        filters: dict[str, Any] | None = None,
    ) -> int:
        normalized_filters = self._normalize_filters(filters)

        with self._session_factory()() as session:
            query = self.base_query(session)
            query = self._apply_filters(query, normalized_filters)
            query = self._apply_access_scope(query)
            return query.count()

    def list(
        self,
        *,
        page: int = 0,
        page_size: int = 25,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_page = max(0, int(page))
        resolved_page_size = max(1, min(int(page_size), 200))
        normalized_filters = self._normalize_filters(filters)
        normalized_sort = self._normalize_sort(sort)

        with self._session_factory()() as session:
            query = self.base_query(session)
            query = self._apply_filters(query, normalized_filters)
            query = self._apply_access_scope(query)
            total_rows = query.count()
            rows = (
                self._apply_sort(query, normalized_sort)
                .offset(resolved_page * resolved_page_size)
                .limit(resolved_page_size)
                .all()
            )

        return {
            "rows": [self.serialize_row(item) for item in rows],
            "total_rows": total_rows,
            "page": resolved_page,
            "page_size": resolved_page_size,
            "filters": normalized_filters,
            "sort": normalized_sort,
        }

    def all(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_filters = self._normalize_filters(filters)
        normalized_sort = self._normalize_sort(sort)

        with self._session_factory()() as session:
            query = self.base_query(session)
            query = self._apply_filters(query, normalized_filters)
            query = self._apply_access_scope(query)
            rows = self._apply_sort(query, normalized_sort).all()

        return {
            "rows": [self.serialize_row(item) for item in rows],
            "filters": normalized_filters,
            "sort": normalized_sort,
        }

    @abstractmethod
    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: int) -> bool:
        raise NotImplementedError
