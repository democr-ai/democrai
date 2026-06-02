from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

import democrai.sdk.i18n as i18n_mod
import democrai.core.platform.utils.identity as identity_mod
import democrai.core.platform.utils.timezone as timezone_mod


def test_i18n_additional_branches(monkeypatch, tmp_path):
    calls = {"load": [], "user_lang": [], "t": []}

    class _Tx:
        def load_module_locales(self, module, path):
            calls["load"].append((module, path))

        def get_user_language(self, user_id):
            calls["user_lang"].append(user_id)
            return "IT" if user_id == 10 else "en"

        def t(self, key, lang=None, context=None, module=None):
            calls["t"].append((key, lang, context, module))
            return f"{module}:{key}:{lang}"

    monkeypatch.setattr(i18n_mod, "get_translation_service", lambda: _Tx())

    sdk = SimpleNamespace(
        module_name="mod",
        module_path=str(tmp_path),
        session={"user": {"id": "10"}},
    )
    (tmp_path / "locales").mkdir(parents=True)

    i18n = i18n_mod.I18n(sdk)
    assert i18n.get_user_language() == "IT"
    assert calls["user_lang"][-1] == 10

    # user fallback branch where user id is anonymous and no explicit lang/session lang
    sdk.session = {"user": {"id": "anonymous"}}
    out = i18n.t("k", context={"x": 1})
    assert out == "None:k:None"

    # explicit lang bypasses session/user lookup
    out2 = i18n.t("k2", lang="FR")
    assert out2 == "None:k2:FR"
    assert calls["load"] == []

    # session/user lookup branch -> translation service get_user_language
    sdk.session = {"user": {"id": 12}}
    out3 = i18n.t("k3")
    assert out3 == "None:k3:en"

    assert i18n.get_user_language(user_id=99) == "en"

    # skip module locale loading branch
    sdk.module_name = ""
    sdk.module_path = str(tmp_path / "missing-locales")
    out4 = i18n.t("k4")
    assert out4 == "None:k4:en"

    sdk.module_name = "mod"
    sdk.session = {"user_language": " IT "}
    out5 = i18n.t("k5")
    assert out5 == "None:k5:it"


def test_identity_helpers_branches():
    assert identity_mod.to_optional_int(True) is None
    assert identity_mod.to_optional_int(False) is None
    assert identity_mod.to_optional_int("  ") is None
    assert identity_mod.to_optional_int("12") == 12
    assert identity_mod.to_optional_int("abc") is None
    assert identity_mod.to_required_int("7", "field") == 7
    assert identity_mod.to_int_or_zero(None) == 0
    assert identity_mod.to_int_or_zero("9") == 9
    with pytest.raises(ValueError):
        identity_mod.to_required_int("x", "field")


def test_timezone_key_and_validate_true(monkeypatch):
    real_datetime = timezone_mod.datetime

    class _Tz:
        key = "Europe/Rome"

    class _Now:
        def astimezone(self):
            return SimpleNamespace(tzinfo=_Tz())

    class _DateTimeProxy:
        @staticmethod
        def now(tz=None):
            return _Now()

    monkeypatch.setattr(timezone_mod, "datetime", _DateTimeProxy)
    assert timezone_mod.get_system_timezone_name() == "Europe/Rome"

    assert timezone_mod.validate_timezone_name("UTC") is True

    # utc helper smoke checks
    monkeypatch.setattr(timezone_mod, "datetime", real_datetime)
    now = timezone_mod.utc_now()
    naive = timezone_mod.utc_now_naive()
    assert now.tzinfo is not None
    assert naive.tzinfo is None

    # format without seconds branch
    dt = datetime(2026, 1, 1, 12, 30, 0)
    monkeypatch.setattr(timezone_mod, "app_ctx", lambda: SimpleNamespace(config=SimpleNamespace(get=lambda *_a, **_k: "UTC")))
    out = timezone_mod.format_app_datetime(dt, include_seconds=False)
    assert out.startswith("2026-01-01 12:30")
