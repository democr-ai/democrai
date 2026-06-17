from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import User
from democrai.core.platform.utils.identity import to_optional_int


@dataclass(frozen=True)
class EngineQuotaSubject:
    user_id: int | None
    organization_id: int | None
    role_ids: tuple[int, ...]
    session_id: str | None

    @property
    def is_guest(self) -> bool:
        return self.user_id is None


def resolve_quota_subject(
    *,
    user_id: int | None,
    request_context: dict[str, Any] | None,
) -> EngineQuotaSubject:
    context = request_context if isinstance(request_context, dict) else {}
    resolved_user_id = to_optional_int(user_id)
    if resolved_user_id is None:
        resolved_user_id = to_optional_int(context.get("user"))
    organization_id = to_optional_int(context.get("organization_id"))
    session_id = str(context.get("session_key") or "").strip() or None

    if resolved_user_id is None:
        return EngineQuotaSubject(
            user_id=None,
            organization_id=None,
            role_ids=(),
            session_id=session_id,
        )

    with SessionLocal() as session:
        user = session.query(User).filter(User.id == resolved_user_id).first()
        if user is None:
            return EngineQuotaSubject(
                user_id=resolved_user_id,
                organization_id=organization_id,
                role_ids=(),
                session_id=session_id,
            )
        resolved_organization_id = to_optional_int(user.organization_id) or organization_id
        return EngineQuotaSubject(
            user_id=resolved_user_id,
            organization_id=resolved_organization_id,
            role_ids=tuple(int(role.id) for role in list(user.roles or []) if role.id),
            session_id=session_id,
        )
