from __future__ import annotations

from typing import Any

from sqlalchemy.orm import joinedload

from democrai.core.application.auth.service import get_hashed_password
from democrai.core.application.auth.service import (
    get_user_access_profile,
    get_user_access_profile_by_username,
    verify_user as core_verify_user,
)
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.auth.roles import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_USER,
)
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import Organization, Role, User
from democrai.core.platform.utils.identity import to_optional_int


class UsersCoreModel(BaseCoreModel):
    name = "users"
    sqlalchemy_model = User

    def base_query(self, session):
        return session.query(User).options(
            joinedload(User.roles),
            joinedload(User.organization),
        )

    def serialize_row(self, item: User) -> dict[str, Any]:
        role_name = item.roles[0].name if item.roles else None
        return {
            "id": item.id,
            "username": item.username,
            "email": item.email,
            "language": item.language,
            "role": role_name,
            "access_level": item.access_level,
            "organization_id": item.organization_id,
            "organization_name": item.organization.name if item.organization is not None else None,
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }

    def serialize_detail(self, item: User) -> dict[str, Any]:
        row = self.serialize_row(item)
        row["roles"] = [role.name for role in item.roles]
        return row

    def verify(self, username: str, password: str) -> bool:
        success, _ = core_verify_user(username, password)
        return success

    def get_info(self, username: str) -> dict[str, Any] | None:
        return get_user_access_profile_by_username(username)

    def get_info_by_id(self, user_id: int) -> dict[str, Any] | None:
        return get_user_access_profile(user_id)

    def filters_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int"},
            {"field": "username", "type": "text"},
            {"field": "email", "type": "text"},
            {"field": "language", "type": "text"},
            {"field": "role", "type": "text"},
            {"field": "access_level", "type": "int"},
            {"field": "organization_id", "type": "int"},
            {"field": "organization_name", "type": "text"},
        ]

    def table_model(self) -> list[dict[str, Any]]:
        return [
            {"field": "id", "type": "int", "filterable": False},
            {
                "field": "username",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "email",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {
                "field": "language",
                "type": "str",
                "filterable": True,
                "filter_type": "text",
            },
            {"field": "role", "type": "str", "filterable": True, "filter_type": "text"},
            {
                "field": "access_level",
                "type": "int",
                "filterable": True,
                "filter_type": "select",
                "options": [ROLE_LEVEL_SUPER, ROLE_LEVEL_ORGANIZATION, ROLE_LEVEL_USER],
                "transform": "get_stub:access_levels",
            },
            {
                "field": "organization_name",
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

    def form_model_create(self) -> list[dict[str, Any]]:
        return [
            {"field": "username", "type": "text", "required": True},
            {"field": "email", "type": "text", "required": False},
            {"field": "language", "type": "text", "required": False},
            {"field": "role", "type": "select", "required": False},
            {
                "field": "access_level",
                "type": "select",
                "required": True,
                "options": [ROLE_LEVEL_SUPER, ROLE_LEVEL_ORGANIZATION, ROLE_LEVEL_USER],
            },
            {"field": "password", "type": "password", "required": True},
            {"field": "confirm_password", "type": "password", "required": True},
        ]

    def form_model_update(self, entity_id: int) -> list[dict[str, Any]]:
        return [
            {"field": "username", "type": "text", "required": True},
            {"field": "email", "type": "text", "required": False},
            {"field": "language", "type": "text", "required": False},
            {"field": "role", "type": "select", "required": False},
            {
                "field": "access_level",
                "type": "select",
                "required": True,
                "options": [ROLE_LEVEL_SUPER, ROLE_LEVEL_ORGANIZATION, ROLE_LEVEL_USER],
            },
        ]

    def _apply_filters(self, query, filters: dict[str, Any]):
        username = filters.get("username")
        if isinstance(username, str):
            query = query.filter(User.username.ilike(f"%{username}%"))

        email = filters.get("email")
        if isinstance(email, str):
            query = query.filter(User.email.ilike(f"%{email}%"))

        language = filters.get("language")
        if isinstance(language, str):
            query = query.filter(User.language.ilike(f"%{language}%"))

        role = filters.get("role")
        if isinstance(role, str):
            query = query.filter(User.roles.any(Role.name.ilike(f"%{role}%")))

        organization_name = filters.get("organization_name")
        if isinstance(organization_name, str):
            query = query.join(User.organization).filter(
                Organization.name.ilike(f"%{organization_name}%")
            )

        for field_name in ("id", "access_level", "organization_id"):
            value = filters.get(field_name)
            if value is None:
                continue
            parsed = to_optional_int(value)
            if parsed is None:
                continue
            query = query.filter(getattr(User, field_name) == parsed)
        return query

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        username = str(payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        email = str(payload.get("email") or "").strip() or None
        role_name = str(payload.get("role") or "").strip()
        access_level = to_optional_int(payload.get("access_level")) or 3
        organization_id = to_optional_int(payload.get("organization_id"))

        if not username or not password:
            raise ValueError("username and password are required")

        with SessionLocal() as session:
            existing = session.query(User).filter(User.username == username).first()
            if existing is not None:
                raise ValueError("username already in use")

            role = None
            if role_name:
                role = session.query(Role).filter(Role.name == role_name).first()

            user = User(
                username=username,
                email=email,
                password_hash=get_hashed_password(password),
                access_level=access_level,
                organization_id=organization_id,
            )
            if role is not None:
                user.roles = [role]

            session.add(user)
            session.commit()
            session.refresh(user)
            return self.serialize_detail(user)

    def update(self, entity_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            user = query.filter(User.id == entity_id).first()
            if user is None:
                return None

            username = payload.get("username")
            if username is not None:
                username = str(username).strip()
                if not username:
                    raise ValueError("username is required")
                duplicate = (
                    session.query(User)
                    .filter(User.username == username, User.id != entity_id)
                    .first()
                )
                if duplicate is not None:
                    raise ValueError("username already in use")
                user.username = username

            if "email" in payload:
                email = str(payload.get("email") or "").strip()
                user.email = email or None

            if "language" in payload:
                language = str(payload.get("language") or "").strip().lower()
                user.language = language or None

            if "access_level" in payload:
                parsed_access_level = to_optional_int(payload.get("access_level"))
                if parsed_access_level is not None:
                    user.access_level = parsed_access_level

            if "organization_id" in payload:
                user.organization_id = to_optional_int(payload.get("organization_id"))

            role_name = str(payload.get("role") or "").strip()
            if role_name:
                role = session.query(Role).filter(Role.name == role_name).first()
                if role is not None:
                    user.roles = [role]

            password = str(payload.get("password") or "")
            if password:
                user.password_hash = get_hashed_password(password)

            session.commit()
            session.refresh(user)
            return self.serialize_detail(user)

    def delete(self, entity_id: int) -> bool:
        with SessionLocal() as session:
            query = self._apply_access_scope(self.base_query(session))
            user = query.filter(User.id == entity_id).first()
            if user is None:
                return False
            session.delete(user)
            session.commit()
            return True
