from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from democrai.core.application.ai.engine.quotas.types import PERIOD_DAY
from democrai.core.application.ai.engine.quotas.types import PERIOD_HOUR
from democrai.core.application.ai.engine.quotas.types import PERIOD_MINUTE
from democrai.core.application.ai.engine.quotas.types import PERIOD_MONTH
from democrai.core.application.ai.engine.quotas.types import PERIOD_WEEK


def rolling_window(period_unit: str, *, now: datetime) -> tuple[datetime, datetime]:
    if period_unit == PERIOD_MINUTE:
        return now - timedelta(minutes=1), now
    if period_unit == PERIOD_HOUR:
        return now - timedelta(hours=1), now
    if period_unit == PERIOD_DAY:
        return now - timedelta(days=1), now
    if period_unit == PERIOD_WEEK:
        return now - timedelta(weeks=1), now
    if period_unit == PERIOD_MONTH:
        return _subtract_one_month(now), now
    raise ValueError(f"engine_quota_period_unit_unknown:{period_unit}")


def _subtract_one_month(value: datetime) -> datetime:
    month = value.month - 1
    year = value.year
    if month < 1:
        month = 12
        year -= 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
