from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import OrganizationTool
from democrai.core.platform.utils.identity import to_optional_int


class OrganizationToolsCoreModel(BaseCoreModel):
    name = "organization_tool"
    sqlalchemy_model = OrganizationTool

    def serialize_row(self, item: OrganizationTool) -> dict[str, Any]:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "tool_name": item.tool_name,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "organization_id", "type": "int"},
            {"field": "tool_name", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "organization_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "tool_name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "created_at", "type": "str", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in ("id", "organization_id"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is not None:
                query = query.filter(getattr(OrganizationTool, field_name) == parsed)

        tool_name = filters.get("tool_name")
        if isinstance(tool_name, str):
            query = query.filter(OrganizationTool.tool_name.ilike(f"%{tool_name}%"))
        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        organization_id = to_optional_int(payload.get("organization_id"))
        tool_name = str(payload.get("tool_name") or "").strip()
        if organization_id is None:
            raise ValueError("organization_id is required")
        if not tool_name:
            raise ValueError("tool_name is required")

        with SessionLocal() as session:
            row = (
                session.query(OrganizationTool)
                .filter(
                    OrganizationTool.organization_id == organization_id,
                    OrganizationTool.tool_name == tool_name,
                )
                .first()
            )
            if row is None:
                row = OrganizationTool(
                    organization_id=organization_id,
                    tool_name=tool_name,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            row = query.filter(OrganizationTool.id == entity_id).first()
            if row is None:
                return None
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            row = query.filter(OrganizationTool.id == entity_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
