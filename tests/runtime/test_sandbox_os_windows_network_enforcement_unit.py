from __future__ import annotations

import socket
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.sandbox.os.windows import helper as helper_mod
from democrai.core.infrastructure.sandbox.os.windows import winfwp


class _FakeEngine:
    def __init__(self) -> None:
        self.opened = False
        self.applied: list[tuple[str, tuple, bool]] = []
        self.cleared: list[str] = []

    def open(self) -> None:
        self.opened = True

    def apply_block_except(self, identity, *, allowed=None, loopback=True) -> None:
        self.applied.append((identity.value, tuple(allowed or ()), loopback))

    def clear_identity(self, identity) -> None:
        self.cleared.append(identity.value)


@pytest.fixture
def patched(monkeypatch):
    engine = _FakeEngine()
    monkeypatch.setattr(winfwp, "is_process_elevated", lambda: True)
    monkeypatch.setattr(winfwp, "WfpEngine", lambda: engine)
    monkeypatch.setattr(winfwp, "is_descendant_pid", lambda pid, ancestor, **k: True)
    # Default: every pid maps to the same sandbox-host image (shared identity).
    monkeypatch.setattr(winfwp, "process_image_path", lambda pid: r"C:\democrai\sandbox-host.exe")
    return engine


def test_ensure_ready_fails_closed_without_elevation(monkeypatch):
    monkeypatch.setattr(winfwp, "is_process_elevated", lambda: False)
    backend = helper_mod.WindowsHelperBackend()
    with pytest.raises(RuntimeError, match="requires_elevation"):
        backend.ensure_ready()


def test_supports_pid_enforcement_true():
    assert helper_mod.WindowsHelperBackend.supports_pid_enforcement is True


def test_apply_installs_block_except_loopback(patched):
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=1000)
    assert patched.opened is True
    assert len(patched.applied) == 1
    image, allowed, loopback = patched.applied[0]
    assert image.endswith("sandbox-host.exe")
    assert allowed == ()
    assert loopback is True


def test_shared_identity_is_installed_once_and_refcounted(patched):
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=1000)
    backend.apply([], pid=1001)  # same image -> shares the one filter set
    assert len(patched.applied) == 1
    # First child teardown must NOT clear while the second still shares it.
    backend.clear(pid=1000)
    assert patched.cleared == []
    backend.clear(pid=1001)
    assert len(patched.cleared) == 1


def test_distinct_identities_each_get_filters(patched, monkeypatch):
    monkeypatch.setattr(winfwp, "process_image_path", lambda pid: rf"C:\host-{pid}.exe")
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=1000)
    backend.apply([], pid=2000)
    assert len(patched.applied) == 2
    backend.clear(pid=1000)
    assert len(patched.cleared) == 1


def test_resolve_v4_allowed_drops_loopback_and_resolves(monkeypatch):
    def fake_getaddrinfo(host, port, *a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.5", port))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    allowed = helper_mod._resolve_v4_allowed(
        [
            {"host": "127.0.0.1", "port": 8080, "protocol": "tcp"},  # dropped
            {"host": "api.example", "port": 443, "protocol": "tcp"},  # resolved
        ]
    )
    assert len(allowed) == 1
    assert allowed[0].host_ip == "203.0.113.5"
    assert allowed[0].port == 443


def test_clear_unknown_pid_is_noop(patched):
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=1000)
    backend.clear(pid=9999)  # never applied
    assert patched.cleared == []


def test_validate_target_pid_rejects_non_descendant(patched, monkeypatch):
    monkeypatch.setattr(winfwp, "is_descendant_pid", lambda pid, ancestor, **k: False)
    backend = helper_mod.WindowsHelperBackend()
    with pytest.raises(RuntimeError, match="not_descendant"):
        backend.validate_client_and_target_pid(
            writer=SimpleNamespace(), requested_pid=1234, parent_pid=1
        )
