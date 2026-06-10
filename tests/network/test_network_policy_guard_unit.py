from __future__ import annotations

import asyncio
import builtins
import http.client as http_client
import sys
from types import SimpleNamespace

import pytest

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.network import policy_guard as mod


@pytest.fixture(autouse=True)
def _reset_policy_state():
    mod._ORIGINALS.clear()
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    mod._STATE.set(None)
    yield
    mod._ORIGINALS.clear()
    mod._ACTIVE = False
    mod._ACTIVE_COUNT = 0
    mod._STATE.set(None)


def test_policy_guard_state_checks_and_wrappers(monkeypatch):
    token = mod._STATE.set(
        {
            "subject_type": "module",
            "subject_name": "demo",
            "user_id": 7,
            "organization_id": 2,
            "session_key": "sess",
        }
    )
    assert mod._subject_type() == "module"
    assert mod._subject_name() == "demo"
    assert mod._request_context() == (7, 2, "sess")

    calls = []

    def _check_external_access(**kwargs):
        calls.append(kwargs)
        target = kwargs["target"]
        if "deny" in target:
            return SimpleNamespace(allowed=False, message="denied")
        return SimpleNamespace(allowed=True, message="ok")

    monkeypatch.setattr(mod, "check_external_access", _check_external_access)

    mod._check_url("https://ok.local/a")
    assert calls[-1]["operation"] == "receive"
    with pytest.raises(PermissionError):
        mod._check_url("https://deny.local/a")
    with pytest.raises(PermissionError):
        mod._check_url(" ")
    mod._check_target("ok.local", 443)
    assert calls[-1]["operation"] == "connect"
    with pytest.raises(PermissionError):
        mod._check_target("deny.local", 80)
    assert calls

    called = []
    monkeypatch.setattr(mod, "_check_url", lambda url, **kw: called.append(("url", url, kw)))
    monkeypatch.setattr(mod, "_check_target", lambda host, port=None, **kw: called.append(("target", host, port, kw)))

    def _orig(*args, **kwargs):
        return ("ok", args, kwargs)

    assert mod._wrap_urlopen(_orig)("https://x") == ("ok", ("https://x",), {})
    assert mod._wrap_http_request(_orig)("self", "GET", "https://x") == ("ok", ("self", "GET", "https://x"), {})

    async def _aorig(*args, **kwargs):
        return ("aok", args, kwargs)

    out = asyncio.run(mod._wrap_aiohttp_request(_aorig)("self", "GET", "https://x"))
    assert out[0] == "aok"
    assert mod._wrap_socket_connect(_orig)("sock", ("host", 1)) == ("ok", ("sock", ("host", 1)), {})
    assert mod._wrap_socket_connect(_orig)("sock", "host:1") == ("ok", ("sock", "host:1"), {})
    assert mod._wrap_socket_connect_ex(_orig)("sock", ("host", 2)) == ("ok", ("sock", ("host", 2)), {})
    assert mod._wrap_socket_connect_ex(_orig)("sock", "host:2") == ("ok", ("sock", "host:2"), {})
    assert mod._wrap_socket_sendto(_orig)("sock", b"d", ("host", 3)) == ("ok", ("sock", b"d", ("host", 3)), {})
    assert mod._wrap_socket_sendto(_orig)("sock", b"d", 0, ("host", 4)) == ("ok", ("sock", b"d", 0, ("host", 4)), {})
    assert mod._wrap_socket_sendto(_orig)("sock", b"d", 0) == ("ok", ("sock", b"d", 0), {})
    assert mod._wrap_create_connection(_orig)(("host", 5)) == ("ok", (("host", 5),), {})
    assert mod._wrap_create_connection(_orig)("host:6") == ("ok", ("host:6",), {})
    out2 = asyncio.run(mod._wrap_asyncio_open_connection(_aorig)("host", 6))
    assert out2[0] == "aok"
    out3 = asyncio.run(mod._wrap_asyncio_open_connection(_aorig)(None, None))
    assert out3[0] == "aok"
    assert called
    mod._STATE.reset(token)


def test_policy_guard_context_access_allows_receive_and_connect(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mod,
        "check_external_access",
        lambda **kwargs: calls.append(kwargs)
        or SimpleNamespace(allowed=False, message="blocked"),
    )

    rule_receive = AccessManifestRule(
        subject=AccessSubject.create("module", "demo"),
        resource=AccessResource.create(
            resource_type="network",
            operation="receive",
            target="https://assets.example.test/image.png",
        ),
    )
    rule_connect = AccessManifestRule(
        subject=AccessSubject.create("module", "demo"),
        resource=AccessResource.create(
            resource_type="network",
            operation="connect",
            target="https://assets.example.test/image.png",
        ),
    )
    monkeypatch.setattr(
        mod,
        "is_network_target_allowed",
        lambda target, patterns: target in {"https://assets.example.test/image.png", "10.0.0.2:443"}
        and bool(patterns),
    )

    with mod.network_policy_context(
        subject_name="demo",
        access=(rule_receive, rule_connect),
    ):
        mod._check_url("https://assets.example.test/image.png", operation="receive")
        mod._check_target("10.0.0.2", 443, operation="connect")

    assert calls == []


def test_policy_guard_allows_only_configured_loopback_proxy_connect(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "http://token:x@127.0.0.1:4123")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    assert mod._network_access_allowed("127.0.0.1:4123", operation="connect")
    assert mod._network_access_allowed("https://127.0.0.1:4123", operation="connect")
    assert mod._network_access_allowed("https://localhost:4123", operation="connect")

    assert not mod._network_access_allowed("127.0.0.1:4124", operation="connect")
    assert not mod._network_access_allowed("https://127.0.0.1:4123", operation="receive")


def test_policy_guard_ignores_non_loopback_proxy_env(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "http://proxy.example.com:8080")
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("HTTP_PROXY", raising=False)

    assert not mod._network_access_allowed("proxy.example.com:8080", operation="connect")


def test_policy_guard_enable_disable_and_context(monkeypatch):
    # fake optional libs imported inside enable/disable
    fake_requests_sessions = SimpleNamespace(Session=SimpleNamespace(request=lambda *a, **k: None))
    fake_requests = SimpleNamespace(sessions=fake_requests_sessions)
    fake_httpx = SimpleNamespace(
        Client=SimpleNamespace(request=lambda *a, **k: None),
        AsyncClient=SimpleNamespace(request=lambda *a, **k: None),
    )
    fake_aiohttp = SimpleNamespace(ClientSession=SimpleNamespace(_request=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "requests.sessions", fake_requests_sessions)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)
    monkeypatch.setattr(mod, "_check_url", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_check_target", lambda *_a, **_k: None)

    token1 = mod.enable_network_policy(
        subject_name="demo",
        user_id=1,
        organization_id=2,
        session_key="k",
    )
    assert mod._ACTIVE is True and mod._ACTIVE_COUNT == 1
    assert "urllib.request.urlopen" in mod._ORIGINALS

    token2 = mod.enable_network_policy(subject_name="demo2")
    assert mod._ACTIVE_COUNT == 2

    # Exercise wrapped HTTPConnection/HTTPSConnection __init__.
    _ = http_client.HTTPConnection("example.com")
    _ = http_client.HTTPSConnection("example.com")

    mod.disable_network_policy(token2)
    assert mod._ACTIVE is True and mod._ACTIVE_COUNT == 1

    mod.disable_network_policy(token1)
    assert mod._ACTIVE is False and mod._ACTIVE_COUNT == 0 and mod._ORIGINALS == {}

    # token reset exception path
    class _BadToken:
        pass

    bad_token = _BadToken()
    mod.disable_network_policy(bad_token)  # does not raise

    entered = []
    exited = []
    monkeypatch.setattr(mod, "enable_network_policy", lambda **kwargs: entered.append(kwargs) or "tok")
    monkeypatch.setattr(mod, "disable_network_policy", lambda token=None: exited.append(token))
    with mod.network_policy_context(subject_name="s", user_id=1, organization_id=2, session_key="k"):
        pass
    assert entered and exited == ["tok"]


def test_policy_guard_enable_disable_import_failure_paths(monkeypatch):
    # Force optional imports in enable/disable to fail and cover except branches.
    monkeypatch.setattr(mod, "_check_url", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_check_target", lambda *_a, **_k: None)

    real_import = builtins.__import__

    def _fake_import(name, *args, **kwargs):
        if name in {"requests.sessions", "httpx", "aiohttp"}:
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _fake_import)
    token = mod.enable_network_policy(subject_name="demo")
    assert mod._ACTIVE is True
    mod.disable_network_policy(token)
    # token None path + not active early return
    mod.disable_network_policy(None)


def test_policy_guard_enable_fails_if_present_library_patch_fails(monkeypatch):
    fake_requests_sessions = SimpleNamespace(Session=SimpleNamespace(request=lambda *a, **k: None))
    fake_requests = SimpleNamespace(sessions=fake_requests_sessions)
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "requests.sessions", fake_requests_sessions)
    monkeypatch.setattr(mod, "_check_url", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_check_target", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_wrap_http_request", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError, match="requests\\.sessions\\.Session\\.request"):
        mod.enable_network_policy(subject_name="demo")

    assert mod._ACTIVE is False
    assert mod._ACTIVE_COUNT == 0
    assert mod._ORIGINALS == {}


def test_policy_guard_disable_with_empty_originals(monkeypatch):
    # Cover disable branches where imports succeed but originals are absent.
    fake_requests_sessions = SimpleNamespace(Session=SimpleNamespace(request=lambda *a, **k: None))
    fake_requests = SimpleNamespace(sessions=fake_requests_sessions)
    fake_httpx = SimpleNamespace(
        Client=SimpleNamespace(request=lambda *a, **k: None),
        AsyncClient=SimpleNamespace(request=lambda *a, **k: None),
    )
    fake_aiohttp = SimpleNamespace(ClientSession=SimpleNamespace(_request=lambda *a, **k: None))
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "requests.sessions", fake_requests_sessions)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)
    mod._ORIGINALS.clear()
    mod._ACTIVE = True
    mod._ACTIVE_COUNT = 0
    mod.disable_network_policy(None)
    assert mod._ACTIVE is False and mod._ORIGINALS == {}


def test_policy_guard_nested_context_extends_parent_scope(monkeypatch):
    fake_requests_sessions = SimpleNamespace(
        Session=SimpleNamespace(request=lambda *a, **k: None)
    )
    fake_requests = SimpleNamespace(sessions=fake_requests_sessions)
    fake_httpx = SimpleNamespace(
        Client=SimpleNamespace(request=lambda *a, **k: None),
        AsyncClient=SimpleNamespace(request=lambda *a, **k: None),
    )
    fake_aiohttp = SimpleNamespace(
        ClientSession=SimpleNamespace(_request=lambda *a, **k: None)
    )
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    monkeypatch.setitem(sys.modules, "requests.sessions", fake_requests_sessions)
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)
    monkeypatch.setattr(mod, "_check_url", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_check_target", lambda *_a, **_k: None)

    parent = mod.enable_network_policy(
        subject_name="module.demo",
        user_id=10,
        organization_id=20,
        session_key="parent-session",
    )
    assert mod._subject_name() == "module.demo"
    assert mod._request_context() == (10, 20, "parent-session")

    child = mod.enable_network_policy(
        subject_name="engine.demo",
    )
    assert mod._subject_name() == "engine.demo"
    assert mod._request_context() == (10, 20, "parent-session")

    mod.disable_network_policy(child)
    assert mod._subject_name() == "module.demo"
    assert mod._request_context() == (10, 20, "parent-session")

    mod.disable_network_policy(parent)


def test_resolved_ip_recheck_skipped_inside_approved_host_connect(monkeypatch):
    # Simulate the CDN case: hostnames pass, raw resolved IPs are denied
    # (because the rotated IP is not in the host's reverse-resolution set).
    def _check_target(host, port=None, **kw):
        if mod._is_ip_address(str(host)):
            raise PermissionError(f"ip denied: {host}")
        return None

    monkeypatch.setattr(mod, "_check_target", _check_target)

    connect_wrapper = mod._wrap_socket_connect(
        lambda self_conn, addr, *a, **k: ("connected", addr)
    )

    # Bare connect to a resolved IP (no enclosing approved host) → denied.
    with pytest.raises(PermissionError):
        connect_wrapper("sock", ("203.0.113.7", 443))

    # create_connection approves the hostname, then does the inner connect to a
    # rotated CDN IP; that IP re-check must be skipped inside the scope.
    def _create_connection_original(address, *a, **k):
        return connect_wrapper("sock", ("203.0.113.7", 443))

    cc_wrapper = mod._wrap_create_connection(_create_connection_original)
    assert cc_wrapper(("cdn.rotating.test", 443)) == ("connected", ("203.0.113.7", 443))

    # Scope is cleaned up afterwards: the bare IP connect is denied again.
    assert mod._APPROVED_HOST_CONNECT_DEPTH.get() == 0
    with pytest.raises(PermissionError):
        connect_wrapper("sock", ("203.0.113.7", 443))


def test_create_connection_to_ip_literal_still_checks_inner_connect(monkeypatch):
    # When create_connection itself targets an IP, no host approval exists, so
    # the inner connect must still be checked (no scope opened).
    def _check_target(host, port=None, **kw):
        if mod._is_ip_address(str(host)):
            raise PermissionError(f"ip denied: {host}")
        return None

    monkeypatch.setattr(mod, "_check_target", _check_target)

    # _check_target raises on the IP at the create_connection level already.
    cc_wrapper = mod._wrap_create_connection(lambda address, *a, **k: ("connected", address))
    with pytest.raises(PermissionError):
        cc_wrapper(("203.0.113.7", 443))
    assert mod._APPROVED_HOST_CONNECT_DEPTH.get() == 0


def test_approved_host_scope_still_checks_inner_hostname_connect(monkeypatch):
    # Inside an approved-host scope, an inner connect to a *hostname* (not an IP)
    # is still validated — only resolved IPs are exempted.
    seen = []

    def _check_target(host, port=None, **kw):
        seen.append(str(host))
        if str(host) == "blocked.test":
            raise PermissionError("blocked host")
        return None

    monkeypatch.setattr(mod, "_check_target", _check_target)

    connect_wrapper = mod._wrap_socket_connect(
        lambda self_conn, addr, *a, **k: ("connected", addr)
    )

    def _create_connection_original(address, *a, **k):
        return connect_wrapper("sock", ("blocked.test", 443))

    cc_wrapper = mod._wrap_create_connection(_create_connection_original)
    with pytest.raises(PermissionError):
        cc_wrapper(("approved.test", 443))
    assert "blocked.test" in seen
