import os

import pytest

import democrai.core.infrastructure.sandbox.os.core_relaunch as core_relaunch
from democrai.core.infrastructure.sandbox.os.core_relaunch import (
    CORE_OS_SANDBOX_PROXY_SESSION_ENV,
    ensure_in_process_core_proxy_session,
)
from democrai.core.infrastructure.sandbox.os.models import (
    ApplicationNetworkAllowlist,
)


_MANAGED_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "WS_PROXY",
    "WSS_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "ws_proxy",
    "wss_proxy",
    "no_proxy",
    CORE_OS_SANDBOX_PROXY_SESSION_ENV,
)


@pytest.fixture(autouse=True)
def _restore_proxy_env():
    # ensure_in_process_core_proxy_session mutates os.environ directly;
    # snapshot/restore so the session env never leaks into other tests.
    snapshot = {key: os.environ.get(key) for key in _MANAGED_ENV_KEYS}
    yield
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class _Config:
    def __init__(self, enabled: bool) -> None:
        self._enabled = enabled

    def get(self, key, default=None):
        if key == "sandbox.os.enabled":
            return self._enabled
        return default


def _wire_in_process(monkeypatch, *, session=None):
    monkeypatch.setattr(
        core_relaunch, "provider_supports_current_process_os_sandbox", lambda: True
    )
    monkeypatch.setattr(core_relaunch, "is_core_os_sandbox_relaunched", lambda: False)
    monkeypatch.setattr(
        core_relaunch, "_ensure_core_sandbox_helper_ready", lambda config: None
    )
    monkeypatch.setattr(
        core_relaunch,
        "build_framework_network_allowlist",
        lambda config=None: ApplicationNetworkAllowlist(endpoints=()),
    )
    started = session or {
        "session_id": "sess-123",
        "proxy_url": "http://tok:x@127.0.0.1:48211",
    }
    monkeypatch.setattr(
        core_relaunch, "_start_core_proxy_session", lambda allowlist, *, config=None: started
    )


def _clear_proxy_env(monkeypatch):
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        CORE_OS_SANDBOX_PROXY_SESSION_ENV,
    ):
        monkeypatch.delenv(key, raising=False)


def test_in_process_proxy_session_sets_env(monkeypatch):
    _clear_proxy_env(monkeypatch)
    _wire_in_process(monkeypatch)

    assert ensure_in_process_core_proxy_session(_Config(enabled=True)) is True
    assert os.environ["HTTPS_PROXY"] == "http://tok:x@127.0.0.1:48211"
    assert os.environ["HTTP_PROXY"] == "http://tok:x@127.0.0.1:48211"
    assert os.environ[CORE_OS_SANDBOX_PROXY_SESSION_ENV] == "sess-123"
    assert "127.0.0.1" in os.environ["NO_PROXY"]


def test_in_process_proxy_session_noop_when_sandbox_disabled(monkeypatch):
    _clear_proxy_env(monkeypatch)
    _wire_in_process(monkeypatch)

    assert ensure_in_process_core_proxy_session(_Config(enabled=False)) is False
    assert "HTTPS_PROXY" not in os.environ
    assert CORE_OS_SANDBOX_PROXY_SESSION_ENV not in os.environ


def test_in_process_proxy_session_noop_when_relaunched(monkeypatch):
    _clear_proxy_env(monkeypatch)
    _wire_in_process(monkeypatch)
    monkeypatch.setattr(core_relaunch, "is_core_os_sandbox_relaunched", lambda: True)

    assert ensure_in_process_core_proxy_session(_Config(enabled=True)) is False
    assert "HTTPS_PROXY" not in os.environ


def test_in_process_proxy_session_idempotent(monkeypatch):
    _clear_proxy_env(monkeypatch)
    _wire_in_process(monkeypatch)
    monkeypatch.setenv(CORE_OS_SANDBOX_PROXY_SESSION_ENV, "already")

    # A session is already wired; do not start a second one or overwrite env.
    def _fail(*_args, **_kwargs):
        raise AssertionError("should not start a second proxy session")

    monkeypatch.setattr(core_relaunch, "_start_core_proxy_session", _fail)
    assert ensure_in_process_core_proxy_session(_Config(enabled=True)) is True
    assert "HTTPS_PROXY" not in os.environ


def test_in_process_proxy_session_failure_is_a_hard_error(monkeypatch):
    _clear_proxy_env(monkeypatch)
    _wire_in_process(monkeypatch)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("helper unavailable")

    monkeypatch.setattr(core_relaunch, "_start_core_proxy_session", _boom)
    # The proxy is the primary enforcement mechanism: with the sandbox enabled
    # there is no silent fallback to IP-based allowlisting.
    with pytest.raises(RuntimeError, match="helper unavailable"):
        ensure_in_process_core_proxy_session(_Config(enabled=True))
    assert "HTTPS_PROXY" not in os.environ
    assert CORE_OS_SANDBOX_PROXY_SESSION_ENV not in os.environ
