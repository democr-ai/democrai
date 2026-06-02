from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.tasks.models import BackgroundTaskRecord


class BackgroundTasksCoreModel(BaseCoreModel):
    name = "background_tasks"
    sqlalchemy_model = BackgroundTaskRecord

    def _default_sort(self) -> tuple[str, str]:
        return ("updated_at", "desc")

    def serialize_row(self, item: BackgroundTaskRecord) -> dict[str, Any]:
        return {
            "id": item.id,
            "module": item.module,
            "label": item.label,
            "status": item.status,
            "progress": item.progress,
            "task_key": item.task_key,
            "user_id": item.user_id,
            "organization_id": item.organization_id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def serialize_detail(self, item: BackgroundTaskRecord) -> dict[str, Any]:
        row = self.serialize_row(item)
        row["checkpoint"] = item.checkpoint
        row["result"] = item.result
        row["error"] = item.error
        return row

    def view(self, entity_id: int | str) -> dict[str, Any] | None:
        task_id = str(entity_id or "").strip()
        if not task_id:
            return None
        with self._session_factory()() as session:
            query = self._apply_access_scope(self.base_query(session))
            item = query.filter(BackgroundTaskRecord.id == task_id).first()
            if item is None:
                return None
            return self.serialize_detail(item)

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "text"},
            {"field": "module", "type": "text"},
            {"field": "label", "type": "text"},
            {"field": "status", "type": "text"},
            {"field": "task_key", "type": "text"},
            {"field": "user_id", "type": "int"},
            {"field": "organization_id", "type": "int"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "module",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "label",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "status",
                "type": "str",
                "filterable": True,
                "filter_type": "select",
                "options": [
                    "pending",
                    "running",
                    "completed",
                    "failed",
                    "interrupted",
                    "waiting_confirmation",
                ],
            },
            {"field": "progress", "type": "float", "filterable": False},
            {
                "field": "updated_at",
                "type": "str",
                "filterable": False,
                "transform": "date:%d/%m/%Y %H:%M",
            },
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in ("id", "module", "label", "status", "task_key"):
            value = filters.get(field_name)
            if isinstance(value, str):
                query = query.filter(
                    getattr(BackgroundTaskRecord, field_name).ilike(f"%{value}%")
                )

        for field_name in ("user_id", "organization_id"):
            value = filters.get(field_name)
            if value is None:
                continue
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                continue
            query = query.filter(getattr(BackgroundTaskRecord, field_name) == parsed)

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("background_tasks is read-only")

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        raise NotImplementedError("background_tasks is read-only")

    def delete(self, entity_id: int) -> bool:
        raise NotImplementedError("background_tasks is read-only")
