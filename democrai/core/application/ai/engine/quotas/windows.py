from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from democrai.core.application.ai.engine.quotas.types import PERIOD_DAY
from democrai.core.application.ai.engine.quotas.types import PERIOD_HOUR
from democrai.core.application.ai.engine.quotas.types import PERIOD_MINUTE
from democrai.core.application.ai.engine.quotas.types import PERIOD_MONTH
from democrai.core.application.ai.engine.quotas.types import PERIOD_WEEK


def rolling_window(
    period_unit: str,
    *,
    period_count: int = 1,
    now: datetime,
) -> tuple[datetime, datetime]:
    count = int(period_count)
    if count < 1:
        raise ValueError(f"engine_quota_period_count_invalid:{period_count}")
    if period_unit == PERIOD_MINUTE:
        return now - timedelta(minutes=count), now
    if period_unit == PERIOD_HOUR:
        return now - timedelta(hours=count), now
    if period_unit == PERIOD_DAY:
        return now - timedelta(days=count), now
    if period_unit == PERIOD_WEEK:
        return now - timedelta(weeks=count), now
    if period_unit == PERIOD_MONTH:
        return _subtract_months(now, count), now
    raise ValueError(f"engine_quota_period_unit_unknown:{period_unit}")


def _subtract_months(value: datetime, count: int) -> datetime:
    month_index = (value.year * 12 + value.month - 1) - count
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)
