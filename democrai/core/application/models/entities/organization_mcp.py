from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import OrganizationMcp
from democrai.core.platform.utils.identity import to_optional_int


class OrganizationMcpCoreModel(BaseCoreModel):
    name = "organization_mcp"
    sqlalchemy_model = OrganizationMcp

    def serialize_row(self, item: OrganizationMcp) -> dict[str, Any]:
        return {
            "id": item.id,
            "organization_id": item.organization_id,
            "mcp_server_id": item.mcp_server_id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "organization_id", "type": "int"},
            {"field": "mcp_server_id", "type": "int"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "organization_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "mcp_server_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "created_at", "type": "str", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        for field_name in ("id", "organization_id", "mcp_server_id"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is not None:
                query = query.filter(getattr(OrganizationMcp, field_name) == parsed)
        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        organization_id = to_optional_int(payload.get("organization_id"))
        mcp_server_id = to_optional_int(payload.get("mcp_server_id"))
        if organization_id is None:
            raise ValueError("organization_id is required")
        if mcp_server_id is None:
            raise ValueError("mcp_server_id is required")

        with SessionLocal() as session:
            row = (
                session.query(OrganizationMcp)
                .filter(
                    OrganizationMcp.organization_id == organization_id,
                    OrganizationMcp.mcp_server_id == mcp_server_id,
                )
                .first()
            )
            if row is None:
                row = OrganizationMcp(
                    organization_id=organization_id,
                    mcp_server_id=mcp_server_id,
                )
                session.add(row)
                session.commit()
                session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            row = query.filter(OrganizationMcp.id == entity_id).first()
            if row is None:
                return None
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            row = query.filter(OrganizationMcp.id == entity_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
