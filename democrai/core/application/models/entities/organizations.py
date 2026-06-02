from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import Organization


class OrganizationsCoreModel(BaseCoreModel):
    name = "organizations"
    sqlalchemy_model = Organization

    def serialize_row(self, item: Organization) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "description", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {
                "field": "name",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "description",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "created_at",
                "type": "str",
                "filterable": False,
                "transform": "date:%d/%m/%Y %H:%M",
            },
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        organization_id = filters.get("id")
        if organization_id is not None:
            try:
                query = query.filter(Organization.id == int(organization_id))
            except (TypeError, ValueError):
                pass

        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(Organization.name.ilike(f"%{name}%"))

        description = filters.get("description")
        if isinstance(description, str):
            query = query.filter(Organization.description.ilike(f"%{description}%"))

        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip() or None
        if not name:
            raise ValueError("name is required")

        with SessionLocal() as session:
            existing = session.query(Organization).filter(Organization.name == name).first()
            if existing is not None:
                raise ValueError("name already in use")

            organization = Organization(name=name, description=description)
            session.add(organization)
            session.commit()
            session.refresh(organization)
            return self.serialize_detail(organization)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            organization = query.filter(Organization.id == entity_id).first()
            if organization is None:
                return None

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("name is required")
                duplicate = (
                    session.query(Organization)
                    .filter(Organization.name == name, Organization.id != entity_id)
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("name already in use")
                organization.name = name

            if "description" in payload:
                description = str(payload.get("description") or "").strip()
                organization.description = description or None

            session.commit()
            session.refresh(organization)
            return self.serialize_detail(organization)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            organization = query.filter(Organization.id == entity_id).first()
            if organization is None:
                return False
            session.delete(organization)
            session.commit()
            return True
