from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.auth.roles import is_super_role
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import Permission, Role


class RolesCoreModel(BaseCoreModel):
    name = "roles"
    sqlalchemy_model = Role

    def base_query(self, session):
        return session.query(Role).options(joinedload(Role.permissions))

    def serialize_row(self, item: Role) -> dict[str, Any]:
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "permissions_count": len(item.permissions),
        }

    def serialize_detail(self, item: Role) -> dict[str, Any]:
        row = self.serialize_row(item)
        row["permissions"] = [perm.name for perm in item.permissions]
        return row

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "name", "type": "text"},
            {"field": "description", "type": "text"},
            {"field": "permission", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "name", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "description",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {"field": "permissions_count", "type": "int", "filterable": False},
        ]

    def form_model_create(self) -> list[dict[str, Any]]:
        return [
            {"field": "name", "type": "text", "required": True},
            {"field": "description", "type": "text", "required": False},
            {"field": "permissions", "type": "multiselect", "required": False},
        ]

    def form_model_update(self, entity_id: int) -> list[dict[str, Any]]:
        return self.form_model_create()

    def form_model_extra(self, name: str) -> list[dict[str, Any]]:
        normalized_name = name.strip().lower() if isinstance(name, str) else ""
        if normalized_name != "permissions_options":
            return []

        with SessionLocal() as session:
            permissions = (
                session.query(Permission).order_by(Permission.name.asc()).all()
            )

        return [
            {
                "label": permission.name,
                "value": permission.name,
            }
            for permission in permissions
            if permission.name
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        name = filters.get("name")
        if isinstance(name, str):
            query = query.filter(Role.name.ilike(f"%{name}%"))

        description = filters.get("description")
        if isinstance(description, str):
            query = query.filter(Role.description.ilike(f"%{description}%"))

        permission = filters.get("permission")
        if isinstance(permission, str):
            query = query.filter(
                Role.permissions.any(Permission.name.ilike(f"%{permission}%"))
            )

        role_id = filters.get("id")
        if role_id is not None:
            try:
                query = query.filter(Role.id == int(role_id))
            except (TypeError, ValueError):
                pass

        return query

    def _ensure_permissions(
        self, session, permission_names: list[str]
    ) -> list[Permission]:
        resolved: list[Permission] = []
        for raw_name in permission_names:
            name = str(raw_name or "").strip()
            if not name:
                continue
            permission = (
                session.query(Permission).filter(Permission.name == name).first()
            )
            if permission is None:
                permission = Permission(name=name)
                session.add(permission)
                session.flush()
            resolved.append(permission)
        return resolved

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        name = str(payload.get("name") or "").strip()
        description = str(payload.get("description") or "").strip() or None
        permission_names = payload.get("permissions") or []
        if not isinstance(permission_names, list):
            permission_names = []
        if not name:
            raise ValueError("role name is required")

        with SessionLocal() as session:
            existing = session.query(Role).filter(Role.name == name).first()
            if existing is not None:
                raise ValueError("role name already in use")

            role = Role(name=name, description=description)
            role.permissions = self._ensure_permissions(session, permission_names)
            session.add(role)
            session.commit()
            session.refresh(role)
            return self.serialize_detail(role)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            role = self.base_query(session).filter(Role.id == entity_id).first()
            if role is None:
                return None
            if is_super_role(role.name):
                raise ValueError("super role cannot be modified or deleted")

            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("role name is required")
                duplicate = (
                    session.query(Role)
                    .filter(Role.name == name, Role.id != entity_id)
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("role name already in use")
                role.name = name

            if "description" in payload:
                role.description = str(payload.get("description") or "").strip() or None

            if "permissions" in payload:
                permission_names = payload.get("permissions") or []
                if not isinstance(permission_names, list):
                    permission_names = []
                role.permissions = self._ensure_permissions(session, permission_names)

            session.commit()
            session.refresh(role)
            return self.serialize_detail(role)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            role = session.query(Role).filter(Role.id == entity_id).first()
            if role is None:
                return False
            if is_super_role(role.name):
                raise ValueError("super role cannot be modified or deleted")
            session.delete(role)
            session.commit()
            return True
