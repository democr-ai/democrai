from __future__ import annotations

from typing import Any

from democrai.core.application.models.base import BaseCoreModel
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ModuleLock
from democrai.core.platform.utils.identity import to_optional_int


class ModuleLocksCoreModel(BaseCoreModel):
    name = "module_locks"
    sqlalchemy_model = ModuleLock

    def serialize_row(self, item: ModuleLock) -> dict[str, Any]:
        return {
            "id": item.id,
            "module_name": item.module_name,
            "user_id": item.user_id,
            "organization_id": item.organization_id,
            "role_id": item.role_id,
            "created_at": item.created_at.isoformat() if item.created_at else None,
            "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        }

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "module_name", "type": "text"},
            {"field": "user_id", "type": "int"},
            {"field": "organization_id", "type": "int"},
            {"field": "role_id", "type": "int"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {"field": "module_name", "type": "str", "filterable": True, "filter_type": "text"},
            {"field": "user_id", "type": "int", "filterable": True, "filter_type": "int"},
            {
                "field": "organization_id",
                "type": "int",
                "filterable": True,
                "filter_type": "int",
            },
            {"field": "role_id", "type": "int", "filterable": True, "filter_type": "int"},
            {"field": "created_at", "type": "str", "filterable": False},
            {"field": "updated_at", "type": "str", "filterable": False},
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        module_name = filters.get("module_name")
        if isinstance(module_name, str):
            query = query.filter(ModuleLock.module_name.ilike(f"%{module_name}%"))

        for field_name in ("id", "user_id", "organization_id", "role_id"):
            parsed = to_optional_int(filters.get(field_name))
            if parsed is None:
                continue
            query = query.filter(getattr(ModuleLock, field_name) == parsed)
        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        module_name = str(payload.get("module_name") or "").strip()
        if not module_name:
            raise ValueError("module_name is required")

        user_id = to_optional_int(payload.get("user_id"))
        organization_id = to_optional_int(payload.get("organization_id"))
        role_id = to_optional_int(payload.get("role_id"))
        if user_id is None and organization_id is None and role_id is None:
            raise ValueError("at least one scope id is required")

        with SessionLocal() as session:
            row = ModuleLock(
                module_name=module_name,
                user_id=user_id,
                organization_id=organization_id,
                role_id=role_id,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            row = query.filter(ModuleLock.id == entity_id).first()
            if row is None:
                return None

            if "module_name" in payload:
                module_name = str(payload.get("module_name") or "").strip()
                if not module_name:
                    raise ValueError("module_name is required")
                row.module_name = module_name
            if "user_id" in payload:
                row.user_id = to_optional_int(payload.get("user_id"))
            if "organization_id" in payload:
                row.organization_id = to_optional_int(payload.get("organization_id"))
            if "role_id" in payload:
                row.role_id = to_optional_int(payload.get("role_id"))

            session.commit()
            session.refresh(row)
            return self.serialize_detail(row)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            row = query.filter(ModuleLock.id == entity_id).first()
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
