from __future__ import annotations

from typing import Any

from democrai.core.application.environment.service import list_environment_variables
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database.models import EnvironmentVariableRegistry
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.normalize import normalize_bool


class EnvironmentVariableRegistryCoreModel(BaseCoreModel):
    name = "environment_variable_registry"
    sqlalchemy_model = EnvironmentVariableRegistry

    def _default_sort(self) -> tuple[str, str]:
        return ("subject_kind", "asc")

    def _normalize_sort(self, sort: dict[str, Any] | None) -> dict[str, str]:
        raw = {} if sort is None else sort
        if not isinstance(raw, dict):
            raw = {}
        field = str(raw.get("field") or raw.get("sortField") or "").strip()
        direction = (
            str(raw.get("direction") or raw.get("sortDirection") or "").strip().lower()
        )
        sortable = {
            str(item.get("field") or "").strip()
            for item in self.table_model()
            if str(item.get("field") or "").strip()
        }
        if field not in sortable:
            field, direction = self._default_sort()
        if direction not in {"asc", "desc"}:
            direction = "asc"
        return {"field": field, "direction": direction}

    def serialize_row(self, item: Any) -> dict[str, Any]:
        if isinstance(item, dict):
            return dict(item)
        return {}

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "subject_kind", "type": "text"},
            {"field": "subject", "type": "text"},
            {"field": "name", "type": "text"},
            {"field": "label", "type": "text"},
            {"field": "enabled", "type": "bool"},
            {"field": "configured", "type": "bool"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "subject_kind", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "subject", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "label", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "enabled",
                "type": "bool",
                "filterable": True,
                "filter_type": "select",
                "options": [True, False],
            },
            {
                "field": "configured",
                "type": "bool",
                "filterable": True,
                "filter_type": "select",
                "options": [True, False],
            },
            {"field": "masked_value", "type": "str", "filterable": False},
        ]

    def _rows(self) -> list[dict[str, Any]]:
        return list_environment_variables()

    def _matches(self, row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, value in filters.items():
            if value in (None, ""):
                continue
            field = str(key or "").strip()
            if field == "id":
                expected = to_optional_int(value)
                if expected is None or row.get("id") != expected:
                    return False
                continue
            raw = row.get(field)
            if isinstance(raw, bool):
                expected_bool = normalize_bool(value, default=False)
                if raw != expected_bool:
                    return False
                continue
            if str(value).strip().lower() not in str(raw or "").strip().lower():
                return False
        return True

    def _sort_rows(self, rows: list[dict[str, Any]], sort: dict[str, Any] | None) -> list[dict[str, Any]]:
        normalized = self._normalize_sort(sort)
        field = normalized.get("field") or "subject_kind"
        reverse = normalized.get("direction") == "desc"
        return sorted(rows, key=lambda row: str(row.get(field) or ""), reverse=reverse)

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
        rows = [row for row in self._rows() if self._matches(row, normalized_filters)]
        rows = self._sort_rows(rows, normalized_sort)
        start = resolved_page * resolved_page_size
        end = start + resolved_page_size
        return {
            "rows": rows[start:end],
            "total_rows": len(rows),
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
        rows = [row for row in self._rows() if self._matches(row, normalized_filters)]
        return {
            "rows": self._sort_rows(rows, normalized_sort),
            "filters": normalized_filters,
            "sort": normalized_sort,
        }

    def view(self, entity_id: int) -> dict[str, Any] | None:
        for row in self._rows():
            if row.get("id") == entity_id:
                return row
        return None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("environment_variable_registry is managed through sdk.environment")

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("environment_variable_registry is managed through sdk.environment")

    def delete(self, entity_id: int) -> bool:
        raise NotImplementedError("environment_variable_registry is managed through sdk.environment")
