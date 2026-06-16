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
    monkeypatch.setattr(
        winfwp,
        "process_image_path",
        lambda pid: r"C:\democrai\.venv\Scripts\python-democrai-sandbox.exe",
    )
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
    assert image.endswith("python-democrai-sandbox.exe")
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
    monkeypatch.setattr(
        winfwp, "process_image_path", lambda pid: rf"C:\v{pid}\python-democrai-sandbox.exe"
    )
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=1000)
    backend.apply([], pid=2000)
    assert len(patched.applied) == 2
    backend.clear(pid=1000)
    assert len(patched.cleared) == 1


def test_apply_block_except_covers_v4_and_v6(monkeypatch):
    # apply_block_except must install BLOCK + loopback PERMIT on BOTH ALE layers.
    monkeypatch.setattr(winfwp, "_fwpuclnt", lambda: SimpleNamespace())
    engine = winfwp.WfpEngine()
    calls: list[tuple] = []
    monkeypatch.setattr(engine, "_identity_condition", lambda identity, ka: object())
    monkeypatch.setattr(engine, "_remote_address_condition_v4", lambda a, m, ka: object())
    monkeypatch.setattr(engine, "_remote_address_condition_v6", lambda a, p, ka: object())
    monkeypatch.setattr(
        engine,
        "_add_filter",
        lambda key, *, layer_guid, action, weight, conditions, keepalive: calls.append(
            (layer_guid, action)
        ),
    )
    identity = winfwp.WfpIdentity(kind="app_id", value=r"C:\v\python-democrai-sandbox.exe")
    engine.apply_block_except(identity, allowed=[], loopback=True)

    v4, v6 = winfwp._FWPM_LAYER_ALE_AUTH_CONNECT_V4, winfwp._FWPM_LAYER_ALE_AUTH_CONNECT_V6
    assert (v4, winfwp.FWP_ACTION_BLOCK) in calls
    assert (v6, winfwp.FWP_ACTION_BLOCK) in calls  # v6 egress denied (bridge)
    assert (v4, winfwp.FWP_ACTION_PERMIT) in calls  # 127.0.0.0/8 loopback
    assert (v6, winfwp.FWP_ACTION_PERMIT) in calls  # ::1 loopback


def test_shared_identity_divergent_allowlist_warns(patched, monkeypatch):
    events: list[str] = []
    monkeypatch.setattr(
        helper_mod, "debug_os_sandbox_flow", lambda event, **k: events.append(event)
    )
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=1000)  # first child: deny (empty allowlist) -> installs
    assert len(patched.applied) == 1

    # second child, SAME sandbox-host identity, but a divergent (non-loopback) allowlist
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda h, p, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.9", p))],
    )
    backend.apply([{"host": "api.example", "port": 443, "protocol": "tcp"}], pid=1001)
    assert len(patched.applied) == 1  # shared: NOT reinstalled
    assert "windows.shared_identity_allowlist_divergence" in events


def test_apply_rolls_back_on_engine_failure(patched, monkeypatch):
    # A partial install (apply_block_except raises after adding some filters) must
    # not leave the pid registered with a half-applied set — a sibling sharing the
    # identity would otherwise find first_for_identity False and inherit it.
    backend = helper_mod.WindowsHelperBackend()
    real_apply = patched.apply_block_except
    calls = {"n": 0}

    def _maybe_boom(identity, *, allowed=None, loopback=True):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("FwpmFilterAdd0 failed")
        real_apply(identity, allowed=allowed, loopback=loopback)

    monkeypatch.setattr(patched, "apply_block_except", _maybe_boom)
    with pytest.raises(OSError):
        backend.apply([], pid=1000)
    assert patched.applied == []  # the failed install recorded nothing
    assert len(patched.cleared) == 1  # rollback dropped any partial filters
    # Fully rolled back: a retry is treated as the first child and installs fresh.
    backend.apply([], pid=1000)
    assert len(patched.applied) == 1


def test_apply_skips_non_host_interpreter_image(patched, monkeypatch):
    # A pid whose image is a plain shared interpreter (not a sandbox-host exe)
    # must NOT get a WFP block — that would confine the helper/desktop too.
    monkeypatch.setattr(
        winfwp, "process_image_path", lambda pid: r"C:\Users\fabio\Python312\python.exe"
    )
    backend = helper_mod.WindowsHelperBackend()
    backend.apply([], pid=4321)
    assert patched.applied == []  # no filters installed for a shared interpreter
    # And nothing tracked, so a later clear is a no-op.
    backend.clear(pid=4321)
    assert patched.cleared == []


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


def _capture_spawn(monkeypatch):
    from democrai.core.infrastructure.sandbox.os.windows import elevation

    captured: dict = {}

    def _fake(command, *, cwd=None):
        captured["command"] = list(command)
        captured["cwd"] = cwd
        return SimpleNamespace()

    monkeypatch.setattr(elevation, "spawn_elevated_process", _fake)
    return captured


def test_spawn_helper_process_dehosts_sandbox_host_interpreter(monkeypatch):
    # The elevated helper hosts the egress proxy; it must run from the real
    # interpreter, not the sandbox-host exe (whose app-id is WFP-blocked).
    captured = _capture_spawn(monkeypatch)
    backend = helper_mod.WindowsHelperBackend()
    host_exe = r"C:\v\python-democrai-sandbox.exe"
    backend.spawn_helper_process(
        [host_exe, "-m", "pkg", "--token", "x"], {"cwd": r"C:\app", "stdout": None}
    )
    assert "-democrai-sandbox" not in captured["command"][0]  # de-hosted
    assert captured["command"][0] == r"C:\v\python.exe"
    assert captured["command"][1:] == ["-m", "pkg", "--token", "x"]
    assert captured["cwd"] == r"C:\app"


def test_spawn_helper_process_keeps_normal_interpreter(monkeypatch):
    captured = _capture_spawn(monkeypatch)
    backend = helper_mod.WindowsHelperBackend()
    normal = r"C:\v\python.exe"
    backend.spawn_helper_process([normal, "-m", "pkg"], {"cwd": None, "stdout": None})
    assert captured["command"][0] == normal  # unchanged (no-op for a real interpreter)
