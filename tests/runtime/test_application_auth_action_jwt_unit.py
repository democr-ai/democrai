from __future__ import annotations

import asyncio
import datetime
from types import SimpleNamespace

import jwt as pyjwt
import pytest


def test_auth_action_decorator_permissions_and_access():
    mod = __import__("democrai.core.application.auth.action", fromlist=["dummy"])

    @mod.permission_required(["a.read"])
    async def _handler():
        return "ok"

    assert asyncio.run(_handler()) == "ok"
    assert mod.get_required_permissions(_handler) == ["a.read"]
    assert mod.check_access([], []) is True
    assert mod.check_access(["x"], ["x", "y"]) is True
    assert mod.check_access(["x"], ["y"]) is False


def test_auth_jwt_config_and_cookie_helpers(monkeypatch):
    mod = __import__("democrai.core.application.auth.jwt", fromlist=["dummy"])

    class _Cfg:
        def __init__(self, values):
            self.values = values

        def get(self, key, default=None):
            return self.values.get(key, default)

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(config=_Cfg({}), logger=SimpleNamespace(warning=lambda *_a, **_k: None, error=lambda *_a, **_k: None)),
    )
    monkeypatch.setattr(mod.os, "environ", {"AUTH_SECRET_KEY": "env-secret-key-for-tests-32-bytes"})

    assert mod._get_secret_key() == "env-secret-key-for-tests-32-bytes"
    assert mod.auth_cookie_name() == "session"
    assert mod.auth_cookie_secure() is False
    assert mod.auth_cookie_http_only() is True
    assert mod.auth_cookie_samesite() == "lax"
    assert mod.auth_cookie_domain() is None
    assert mod.session_cookie_name() == "democrai_sid"
    assert mod.jwt_issuer()
    assert mod.jwt_audience() is None
    assert mod.jwt_tid() is None
    assert mod.jwt_access_ttl_seconds() == mod.DEFAULT_ACCESS_TTL_SECONDS

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=_Cfg(
                {
                    "auth.cookie_name": "sid",
                    "auth.cookie_secure": "true",
                    "auth.cookie_http_only": 0,
                    "auth.cookie_samesite": "strict",
                    "auth.cookie_domain": "example.org",
                    "session.cookie_name": "s2",
                    "auth.jwt_issuer": "issuer-x",
                    "auth.jwt_audience": "aud-x",
                    "auth.jwt_tid": "tenant-x",
                    "auth.jwt_access_ttl_seconds": "120",
                }
            ),
            logger=SimpleNamespace(warning=lambda *_a, **_k: None, error=lambda *_a, **_k: None),
        ),
    )
    assert mod.auth_cookie_name() == "sid"
    assert mod.auth_cookie_secure() is True
    assert mod.auth_cookie_http_only() is False
    assert mod.auth_cookie_samesite() == "strict"
    assert mod.auth_cookie_domain() == "example.org"
    assert mod.session_cookie_name() == "s2"
    assert mod.jwt_issuer() == "issuer-x"
    assert mod.jwt_audience() == "aud-x"
    assert mod.jwt_tid() == "tenant-x"
    assert mod.jwt_access_ttl_seconds() == 120


def test_auth_jwt_config_bool_samesite_and_ttl_fallbacks(monkeypatch):
    mod = __import__("democrai.core.application.auth.jwt", fromlist=["dummy"])

    class _Cfg:
        def __init__(self, values):
            self.values = values

        def get(self, key, default=None):
            return self.values.get(key, default)

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=_Cfg(
                {
                    "auth.cookie_secure": "maybe",
                    "auth.cookie_http_only": " ",
                    "auth.cookie_samesite": "invalid",
                    "auth.jwt_access_ttl_seconds": "oops",
                }
            ),
            logger=SimpleNamespace(warning=lambda *_a, **_k: None, error=lambda *_a, **_k: None),
        ),
    )
    assert mod.auth_cookie_secure() is False
    assert mod.auth_cookie_http_only() is False
    assert mod.auth_cookie_samesite() == "lax"
    assert mod.jwt_access_ttl_seconds() == mod.DEFAULT_ACCESS_TTL_SECONDS


def test_auth_jwt_secret_from_env_without_ctx_and_ttl_zero(monkeypatch):
    mod = __import__("democrai.core.application.auth.jwt", fromlist=["dummy"])
    monkeypatch.setattr(mod, "app_ctx", lambda: None)
    monkeypatch.setattr(mod.os, "environ", {"AUTH_SECRET_KEY": "env-only-secret-key-for-tests-32b"})
    assert mod._get_secret_key() == "env-only-secret-key-for-tests-32b"

    class _Cfg:
        def get(self, key, default=None):
            if key == "auth.jwt_access_ttl_seconds":
                return 0
            return default

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(config=_Cfg(), logger=SimpleNamespace(warning=lambda *_a, **_k: None, error=lambda *_a, **_k: None)),
    )
    assert mod.jwt_access_ttl_seconds() == mod.DEFAULT_ACCESS_TTL_SECONDS


def test_auth_jwt_token_create_decode_and_error_paths(monkeypatch):
    mod = __import__("democrai.core.application.auth.jwt", fromlist=["dummy"])
    logs = {"warn": [], "err": []}

    class _Cfg:
        def __init__(self, values):
            self.values = values

        def get(self, key, default=None):
            return self.values.get(key, default)

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=_Cfg(
                {
                    "auth.jwt_secret": "test-secret-key-for-jwt-suite-32b",
                    "auth.jwt_algorithm": "HS256",
                    "auth.jwt_issuer": "issuer",
                    "auth.jwt_audience": "aud",
                    "auth.jwt_tid": "tid1",
                }
            ),
            logger=SimpleNamespace(
                warning=lambda m, *_a, **_k: logs["warn"].append(m),
                error=lambda m, *_a, **_k: logs["err"].append(m),
            ),
        ),
    )

    token = mod.create_access_token({"sub": "u1", "user_id": 1})
    decoded = mod.decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "u1"
    assert decoded["iss"] == "issuer"
    assert decoded["aud"] == "aud"
    assert decoded["tid"] == "tid1"

    # Mismatched tid -> PyJWTError path -> None
    bad_tid_token = pyjwt.encode(
        {
            "sub": "u1",
            "user_id": 1,
            "iss": "issuer",
            "aud": "aud",
            "tid": "bad",
            "exp": datetime.datetime.now(datetime.UTC) + datetime.timedelta(minutes=1),
            "iat": datetime.datetime.now(datetime.UTC),
        },
        "test-secret-key-for-jwt-suite-32b",
        algorithm="HS256",
    )
    assert mod.decode_access_token(bad_tid_token) is None
    assert logs["err"]

    # Expired token path with warning
    expired_token = pyjwt.encode(
        {
            "sub": "u1",
            "user_id": 1,
            "iss": "issuer",
            "aud": "aud",
            "tid": "tid1",
            "exp": datetime.datetime.now(datetime.UTC) - datetime.timedelta(seconds=1),
            "iat": datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=2),
        },
        "test-secret-key-for-jwt-suite-32b",
        algorithm="HS256",
    )
    assert mod.decode_access_token(expired_token, log_expired=True) is None
    assert logs["warn"]


def test_auth_jwt_expires_delta_and_expired_decode_fallback(monkeypatch):
    mod = __import__("democrai.core.application.auth.jwt", fromlist=["dummy"])
    logs = {"warn": [], "err": []}

    class _Cfg:
        def __init__(self, values):
            self.values = values

        def get(self, key, default=None):
            return self.values.get(key, default)

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=_Cfg(
                {
                    "auth.jwt_secret": "test-secret-key-for-jwt-suite-32b",
                    "auth.jwt_algorithm": "HS256",
                    "auth.jwt_issuer": "issuer",
                    "auth.jwt_audience": "",
                    "auth.jwt_tid": "",
                }
            ),
            logger=SimpleNamespace(
                warning=lambda m, *_a, **_k: logs["warn"].append(m),
                error=lambda m, *_a, **_k: logs["err"].append(m),
            ),
        ),
    )

    token = mod.create_access_token(
        {"sub": "u2", "user_id": 2},
        expires_delta=datetime.timedelta(seconds=30),
    )
    decoded = mod.decode_access_token(token)
    assert decoded is not None and decoded["sub"] == "u2"
    assert "aud" not in decoded and "tid" not in decoded

    class _ExpiredDecode:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise pyjwt.ExpiredSignatureError("expired")
            raise RuntimeError("decode boom")

    monkeypatch.setattr(mod.jwt, "decode", _ExpiredDecode())
    assert mod.decode_access_token("x.y.z", log_expired=False) is None
    assert logs["warn"] == []


def test_auth_jwt_secret_missing_raises(monkeypatch):
    mod = __import__("democrai.core.application.auth.jwt", fromlist=["dummy"])
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(config=SimpleNamespace(get=lambda *_a, **_k: None)),
    )
    monkeypatch.setattr(mod.os, "environ", {})
    with pytest.raises(RuntimeError):
        mod._get_secret_key()
