from __future__ import annotations

from datetime import UTC
from datetime import datetime

from democrai.core.platform.utils import timezone as mod


class _Cfg:
    def __init__(self, timezone_value: str):
        self._timezone_value = timezone_value

    def get(self, key: str, default=None):
        if key == "app.timezone":
            return self._timezone_value
        return default


def test_serialize_and_format_datetime_use_app_timezone(monkeypatch):
    monkeypatch.setattr(mod, "app_ctx", lambda: type("_Ctx", (), {"config": _Cfg("Europe/Rome")})())

    value = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

    assert mod.serialize_app_datetime(value).startswith("2026-01-15T13:00:00+01:00")
    assert mod.format_app_datetime(value) == "2026-01-15 13:00:00 CET"


def test_timezone_helpers_cover_system_fallbacks_and_invalid_names(monkeypatch):
    class _LocalTz:
        key = None

        def tzname(self, value):
            return "LOCAL"

    class _Now:
        def astimezone(self):
            return type("_Aware", (), {"tzinfo": _LocalTz()})()

    class _DateTimeProxy:
        @staticmethod
        def now(tz=None):
            return _Now()

    monkeypatch.setattr(mod, "datetime", _DateTimeProxy)
    assert mod.get_system_timezone_name() == "LOCAL"

    monkeypatch.setattr(mod, "app_ctx", lambda: type("_Ctx", (), {"config": _Cfg("Invalid/Zone")})())
    assert mod.get_app_timezone().key == "UTC"
    assert mod.validate_timezone_name("Invalid/Zone") is False

    monkeypatch.setattr(mod, "app_ctx", lambda: type("_Ctx", (), {"config": _Cfg("UTC")})())
    assert mod.to_app_timezone(datetime(2026, 1, 15, 12, 0, 0)).tzinfo.key == "UTC"
