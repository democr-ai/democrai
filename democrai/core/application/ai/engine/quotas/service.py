from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.quotas.subjects import EngineQuotaSubject
from democrai.core.application.ai.engine.quotas.subjects import resolve_quota_subject
from democrai.core.application.ai.engine.quotas.types import EngineQuotaDecision
from democrai.core.application.ai.engine.quotas.types import SCOPE_ALL
from democrai.core.application.ai.engine.quotas.types import SCOPE_GUEST
from democrai.core.application.ai.engine.quotas.types import SCOPE_ORGANIZATION
from democrai.core.application.ai.engine.quotas.types import SCOPE_ROLE
from democrai.core.application.ai.engine.quotas.types import SCOPE_USER
from democrai.core.application.ai.engine.quotas.windows import rolling_window
from democrai.core.infrastructure.ai.engine.quotas.repository import (
    EngineQuotaRepository,
)
from democrai.core.platform.utils.identity import to_int_or_zero
from democrai.core.platform.utils.timezone import utc_now_naive


def check_engine_quota(
    *,
    engine_registry_id: int,
    user_id: int | None,
    request_context: dict[str, Any] | None = None,
) -> EngineQuotaDecision:
    engine_row_id = to_int_or_zero(engine_registry_id)
    if engine_row_id <= 0:
        return EngineQuotaDecision(
            allowed=False,
            reason="engine_quota_engine_registry_id_required",
        )

    subject = resolve_quota_subject(user_id=user_id, request_context=request_context)
    repository = EngineQuotaRepository()
    limits = repository.limits_for_engine(engine_row_id=engine_row_id)
    if not limits:
        return EngineQuotaDecision(allowed=True, reason="engine_quota_unlimited")

    now = utc_now_naive()
    applicable = [
        item for item in limits if _limit_applies(item, subject)
    ]
    if not applicable:
        return EngineQuotaDecision(allowed=True, reason="engine_quota_unlimited")

    for item in applicable:
        started_at, ended_at = rolling_window(item.period_unit, now=now)
        usage_filter = _usage_filter(item.scope_type, subject)
        used = repository.sum_usage_total_tokens(
            engine_row_id=engine_row_id,
            started_at=started_at,
            ended_at=ended_at,
            **usage_filter,
        )
        limit_total = int(item.limit_total_tokens)
        remaining = limit_total - used
        if used >= limit_total:
            return EngineQuotaDecision(
                allowed=False,
                reason="engine_quota_exceeded",
                counter_id=item.counter_id,
                limit_id=item.limit_id,
                scope_type=item.scope_type,
                scope_id=item.scope_id,
                used_total_tokens=used,
                limit_total_tokens=limit_total,
                remaining_total_tokens=max(0, remaining),
            )

    return EngineQuotaDecision(allowed=True, reason="engine_quota_available")


def require_engine_quota(
    *,
    engine_registry_id: int,
    user_id: int | None,
    request_context: dict[str, Any] | None = None,
) -> None:
    decision = check_engine_quota(
        engine_registry_id=engine_registry_id,
        user_id=user_id,
        request_context=request_context,
    )
    if decision.allowed:
        return
    raise RuntimeError(
        "engine_quota_exceeded:"
        f"engine_registry_id={engine_registry_id}:"
        f"scope={decision.scope_type}:{decision.scope_id}:"
        f"used={decision.used_total_tokens}:"
        f"limit={decision.limit_total_tokens}"
    )


def _limit_applies(item: Any, subject: EngineQuotaSubject) -> bool:
    if item.scope_type == SCOPE_ALL:
        return True
    if item.scope_type == SCOPE_GUEST:
        return subject.is_guest
    if subject.is_guest:
        return False
    if item.scope_type == SCOPE_ORGANIZATION:
        return item.scope_id == subject.organization_id
    if item.scope_type == SCOPE_ROLE:
        return item.scope_id in subject.role_ids
    if item.scope_type == SCOPE_USER:
        return item.scope_id == subject.user_id
    return False


def _usage_filter(scope_type: str, subject: EngineQuotaSubject) -> dict[str, Any]:
    if scope_type == SCOPE_ORGANIZATION:
        return {"organization_id": subject.organization_id}
    if scope_type in {SCOPE_ROLE, SCOPE_USER}:
        return {"user_id": subject.user_id}
    if scope_type == SCOPE_GUEST:
        return {"session_id": subject.session_id or ""}
    return {}
