from __future__ import annotations

from dataclasses import dataclass


PERIOD_MINUTE = "minute"
PERIOD_HOUR = "hour"
PERIOD_DAY = "day"
PERIOD_WEEK = "week"
PERIOD_MONTH = "month"
PERIOD_UNITS = {
    PERIOD_MINUTE,
    PERIOD_HOUR,
    PERIOD_DAY,
    PERIOD_WEEK,
    PERIOD_MONTH,
}

METRIC_TOTAL_TOKENS = "total_tokens"
METRIC_REQUESTS = "requests"
METRIC_TYPES = {
    METRIC_TOTAL_TOKENS,
    METRIC_REQUESTS,
}

SCOPE_ALL = "all"
SCOPE_ORGANIZATION = "organization"
SCOPE_ROLE = "role"
SCOPE_USER = "user"
SCOPE_GUEST = "guest"
SCOPE_TYPES = {
    SCOPE_ALL,
    SCOPE_ORGANIZATION,
    SCOPE_ROLE,
    SCOPE_USER,
    SCOPE_GUEST,
}


@dataclass(frozen=True)
class EngineQuotaDecision:
    allowed: bool
    reason: str = ""
    counter_id: int | None = None
    limit_id: int | None = None
    scope_type: str | None = None
    scope_id: int | None = None
    metric_type: str | None = None
    used_value: int = 0
    limit_value: int | None = None
    remaining_value: int | None = None
    used_total_tokens: int = 0
    limit_total_tokens: int | None = None
    remaining_total_tokens: int | None = None
