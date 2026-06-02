from __future__ import annotations

from datetime import UTC
from datetime import datetime
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from democrai.core.runtime.foundation.app import app_ctx

SYSTEM_TIMEZONE_SENTINEL = "system"


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    return utc_now().replace(tzinfo=None)


def get_system_timezone_name() -> str:
    local_tz = datetime.now().astimezone().tzinfo
    tz_key = getattr(local_tz, "key", None)
    if tz_key:
        return tz_key

    tz_name = local_tz.tzname(None) if local_tz is not None else None
    return tz_name or "UTC"


def resolve_timezone_name(value: str | None) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized or normalized.lower() == SYSTEM_TIMEZONE_SENTINEL:
        return get_system_timezone_name()
    return normalized


def get_app_timezone_name() -> str:
    ctx = app_ctx()
    configured = None
    if ctx and ctx.config:
        configured = ctx.config.get("app.timezone")
    return resolve_timezone_name(configured)


def get_app_timezone() -> ZoneInfo:
    tz_name = get_app_timezone_name()
    try:
        return ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def validate_timezone_name(value: str | None) -> bool:
    normalized = resolve_timezone_name(value)
    try:
        ZoneInfo(normalized)
        return True
    except ZoneInfoNotFoundError:
        return False


def to_app_timezone(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(get_app_timezone())


def format_app_datetime(value: datetime, *, include_seconds: bool = True) -> str:
    localized = to_app_timezone(value)
    pattern = "%Y-%m-%d %H:%M:%S %Z" if include_seconds else "%Y-%m-%d %H:%M %Z"
    return localized.strftime(pattern)


def serialize_app_datetime(value: datetime) -> str:
    return to_app_timezone(value).isoformat()
