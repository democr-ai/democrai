from __future__ import annotations

from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import joinedload

from democrai.core.application.auth.roles import is_super_role, normalize_role
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import ModuleLock, User
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx


def _session_user(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {}
    user = session.get("user")
    return user if isinstance(user, dict) else {}


def module_access_identity(
    session: dict[str, Any] | None,
    *,
    user_id: int | None = None,
) -> dict[str, Any]:
    user = _session_user(session)
    resolved_user_id = to_optional_int(user_id)
    if resolved_user_id is None:
        resolved_user_id = to_optional_int(user.get("id"))

    return {
        "user_id": resolved_user_id,
        "organization_id": to_optional_int(user.get("organization_id")),
        "role": normalize_role(user.get("role")),
    }


def is_module_locked_for_user(
    module_name: str,
    *,
    user_id: int | None,
    organization_id: int | None,
    role: str | None = None,
) -> bool:
    target_module = module_name.strip() if isinstance(module_name, str) else ""
    if not target_module:
        return False
    if bool(getattr(app_ctx(), "setup_mode", False)):
        return False
    if is_super_role(role):
        return False

    resolved_user_id = user_id
    resolved_organization_id = organization_id
    if resolved_user_id is None and resolved_organization_id is None:
        return False

    with SessionLocal() as session:
        role_ids: list[int] = []
        user = None
        if resolved_user_id is not None:
            user = (
                session.query(User)
                .options(joinedload(User.roles))
                .filter(User.id == resolved_user_id)
                .first()
            )
            if user is not None:
                for user_role in user.roles or []:
                    if is_super_role(user_role.name):
                        return False
                    if user_role.id is not None:
                        role_ids.append(user_role.id)
                if resolved_organization_id is None:
                    resolved_organization_id = user.organization_id

        predicates = []
        if resolved_user_id is not None:
            predicates.append(ModuleLock.user_id == resolved_user_id)
        if resolved_organization_id is not None:
            predicates.append(ModuleLock.organization_id == resolved_organization_id)
        if role_ids:
            predicates.append(ModuleLock.role_id.in_(role_ids))
        if not predicates:
            return False

        return (
            session.query(ModuleLock.id)
            .filter(ModuleLock.module_name == target_module)
            .filter(or_(*predicates))
            .first()
            is not None
        )


def is_module_locked_for_session(
    module_name: str,
    session: dict[str, Any] | None,
    *,
    user_id: int | None = None,
) -> bool:
    identity = module_access_identity(session, user_id=user_id)
    return is_module_locked_for_user(
        module_name,
        user_id=identity["user_id"],
        organization_id=identity["organization_id"],
        role=identity["role"],
    )


__all__ = [
    "is_module_locked_for_session",
    "is_module_locked_for_user",
    "module_access_identity",
]
