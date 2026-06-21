from __future__ import annotations

import os
from types import SimpleNamespace

from democrai.core.runtime.lifecycle import process_supervisor as supervisor_mod
from democrai.core.runtime.foundation.app import app_ctx
import pytest


class _LoggerCapture:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.warnings = []
        self.debugs = []

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)

    def warning(self, message, *args, **kwargs):
        self.warnings.append(message)

    def debug(self, message, *args, **kwargs):
        self.debugs.append(message)


class _Signal:
    def __init__(self):
        self.handlers = []

    def connect(self, handler):
        self.handlers.append(handler)

    def disconnect(self):
        self.handlers.clear()

    def emit(self, *args):
        for handler in list(self.handlers):
            handler(*args)


class _ChildProc:
    def __init__(self, name="child"):
        self.name = name
        self.finished = _Signal()
        self.errorOccurred = _Signal()
        self.deleted = False

    def deleteLater(self):
        self.deleted = True

    def waitForFinished(self, _timeout):
        return False


def test_process_supervisor_register_unregister_and_pid_helpers(monkeypatch):
    supervisor = supervisor_mod.ProcessSupervisor()
    handle = SimpleNamespace(processId=lambda: 42)
    pid_handle = SimpleNamespace(pid=43)

    supervisor.register(handle, name="gui")
    supervisor.register(pid_handle, name="worker")
    supervisor.register(SimpleNamespace(processId=lambda: 0), name="ignored")

    assert sorted(supervisor._processes.keys()) == [42, 43]
    assert supervisor._pid_from_handle(handle) == 42
    assert supervisor._pid_from_handle(pid_handle) == 43
    assert supervisor._pid_from_handle(None) is None
    assert supervisor._pid_from_handle(SimpleNamespace(processId=lambda: (_ for _ in ()).throw(RuntimeError("boom")), pid=None)) is None

    supervisor.unregister(handle)
    supervisor.unregister(SimpleNamespace())
    assert list(supervisor._processes.keys()) == [43]


def test_process_supervisor_terminate_and_terminate_all(monkeypatch):
    supervisor = supervisor_mod.ProcessSupervisor()
    events = []
    monkeypatch.setattr(supervisor, "_terminate_tree", lambda pid, handle, timeout: events.append((pid, handle, timeout)))

    h1 = SimpleNamespace(processId=lambda: 11)
    h2 = SimpleNamespace(pid=12)
    supervisor.register(h1, "one")
    supervisor.register(h2, "two")

    supervisor.terminate(SimpleNamespace(), timeout_ms=100)
    supervisor.terminate(h1, timeout_ms=2000)
    supervisor.terminate_all(timeout_ms=1000)

    assert events == [
        (11, h1, 2000),
        (12, h2, 1000),
    ]
    assert supervisor._processes == {}


@pytest.mark.posix_only
def test_process_supervisor_tree_and_wait_helpers(monkeypatch):
    supervisor = supervisor_mod.ProcessSupervisor()

    child_a = SimpleNamespace(
        parents=lambda: [1, 2],
        terminate=lambda: None,
        is_running=lambda: True,
        kill=lambda: None,
    )
    child_b = SimpleNamespace(
        parents=lambda: [1],
        terminate=lambda: None,
        is_running=lambda: False,
        kill=lambda: None,
    )
    psutil_stub = SimpleNamespace(
        Process=lambda pid: SimpleNamespace(children=lambda recursive=True: [child_b, child_a]),
        wait_procs=lambda procs, timeout=1.0: None,
        pid_exists=lambda pid: pid == 99,
    )
    monkeypatch.setattr(supervisor_mod, "psutil", psutil_stub)
    descendants = supervisor._descendants(99)
    assert descendants == [child_a, child_b]

    monkeypatch.setattr(psutil_stub, "Process", lambda pid: (_ for _ in ()).throw(RuntimeError("no proc")))
    assert supervisor._descendants(99) == []
    monkeypatch.setattr(supervisor_mod, "psutil", None)
    assert supervisor._descendants(99) == []
    monkeypatch.setattr(supervisor_mod, "psutil", psutil_stub)

    called = []
    supervisor._terminate_psutil([SimpleNamespace(terminate=lambda: called.append("terminate"))])
    supervisor._terminate_psutil([SimpleNamespace(terminate=lambda: (_ for _ in ()).throw(RuntimeError("boom")))])
    monkeypatch.setattr(psutil_stub, "wait_procs", lambda procs, timeout=1.0: (_ for _ in ()).throw(RuntimeError("wait boom")))
    supervisor._terminate_psutil([SimpleNamespace(terminate=lambda: called.append("terminate2"))])
    monkeypatch.setattr(psutil_stub, "wait_procs", lambda procs, timeout=1.0: None)

    supervisor._kill_psutil([SimpleNamespace(is_running=lambda: True, kill=lambda: called.append("kill"))])
    supervisor._kill_psutil([SimpleNamespace(is_running=lambda: (_ for _ in ()).throw(RuntimeError("boom")), kill=lambda: called.append("kill_never"))])
    monkeypatch.setattr(psutil_stub, "wait_procs", lambda procs, timeout=1.0: (_ for _ in ()).throw(RuntimeError("wait boom")))
    supervisor._kill_psutil([SimpleNamespace(is_running=lambda: True, kill=lambda: called.append("kill2"))])
    monkeypatch.setattr(psutil_stub, "wait_procs", lambda procs, timeout=1.0: None)
    assert called == ["terminate", "terminate2", "kill", "kill2"]

    monkeypatch.setattr(supervisor_mod.time, "time", lambda: 0.0)
    monkeypatch.setattr(supervisor_mod.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(supervisor, "_pid_exists", lambda pid: False)
    assert supervisor._wait_pid_exit(1, 0.1) is True

    exists = iter([True, True, False])
    times = iter([0.0, 0.02, 0.04, 0.06])
    monkeypatch.setattr(supervisor_mod.time, "time", lambda: next(times))
    monkeypatch.setattr(supervisor, "_pid_exists", lambda pid: next(exists))
    assert supervisor._wait_pid_exit(1, 0.05) is True

    monkeypatch.setattr(
        supervisor,
        "_pid_exists",
        supervisor_mod.ProcessSupervisor._pid_exists.__get__(
            supervisor, supervisor_mod.ProcessSupervisor
        ),
    )
    # Without psutil it falls back to the platform liveness probe (os.kill based).
    monkeypatch.setattr(supervisor_mod, "psutil", None)
    calls = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: calls.append((pid, sig)))
    assert supervisor._pid_exists(5) is True
    monkeypatch.setattr(os, "kill", lambda pid, sig: (_ for _ in ()).throw(OSError("gone")))
    assert supervisor._pid_exists(5) is False

    # With psutil a live (non-zombie) process is alive, a zombie is treated as gone.
    def _make_psutil(status):
        return SimpleNamespace(
            STATUS_ZOMBIE="zombie",
            Process=lambda pid: SimpleNamespace(status=lambda: status),
        )

    monkeypatch.setattr(supervisor_mod, "psutil", _make_psutil("running"))
    assert supervisor._pid_exists(6) is True
    monkeypatch.setattr(supervisor_mod, "psutil", _make_psutil("zombie"))
    assert supervisor._pid_exists(6) is False

    # A failing psutil probe reports the pid as gone (no os.kill fallback).
    broken_psutil = SimpleNamespace(
        STATUS_ZOMBIE="zombie",
        Process=lambda pid: (_ for _ in ()).throw(RuntimeError("pid boom")),
    )
    monkeypatch.setattr(supervisor_mod, "psutil", broken_psutil)
    assert supervisor._pid_exists(6) is False


def test_process_supervisor_stop_and_wait_methods():
    graceful = []
    force = []
    waited = []
    supervisor = supervisor_mod.ProcessSupervisor()

    handle = SimpleNamespace(
        terminate=lambda: graceful.append("terminate"),
        kill=lambda: force.append("kill"),
        waitForFinished=lambda timeout: waited.append(("qt", timeout)),
    )
    supervisor._graceful_stop(handle)
    supervisor._force_stop(handle)
    supervisor._wait_handle(handle, 1500)

    # A Popen-like handle (wait only) receives the timeout in seconds, not ms.
    second = SimpleNamespace(wait=lambda timeout: waited.append(("wait_secs", timeout)))
    supervisor._wait_handle(second, 2000)

    class _SecondsWaiter:
        def wait(self, timeout):
            if not isinstance(timeout, float):
                raise TypeError("seconds")
            waited.append(("wait_seconds", timeout))

    third = _SecondsWaiter()
    supervisor._wait_handle(third, 2000)
    supervisor._graceful_stop(SimpleNamespace(terminate=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    supervisor._graceful_stop(SimpleNamespace())
    supervisor._force_stop(SimpleNamespace(kill=lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
    supervisor._force_stop(SimpleNamespace())
    supervisor._wait_handle(SimpleNamespace(), 1000)

    class _BrokenAttrs:
        def __getattr__(self, name):
            raise RuntimeError("attr boom")

    supervisor._wait_handle(_BrokenAttrs(), 1000)

    assert graceful == ["terminate"]
    assert force == ["kill"]
    assert waited == [("qt", 1500), ("wait_secs", 2.0), ("wait_seconds", 2.0)]


def test_process_supervisor_terminate_tree_force_path(monkeypatch):
    supervisor = supervisor_mod.ProcessSupervisor()
    events = []
    monkeypatch.setattr(supervisor, "_descendants", lambda pid: ["child"])
    monkeypatch.setattr(supervisor, "_graceful_stop", lambda handle: events.append("graceful"))
    monkeypatch.setattr(supervisor, "_wait_handle", lambda handle, timeout: events.append(("wait", timeout)))
    monkeypatch.setattr(supervisor, "_terminate_psutil", lambda procs: events.append(("terminate_psutil", procs)))
    monkeypatch.setattr(supervisor, "_wait_pid_exit", lambda pid, timeout: False)
    monkeypatch.setattr(supervisor, "_force_stop", lambda handle: events.append("force"))
    monkeypatch.setattr(supervisor, "_kill_psutil", lambda procs: events.append(("kill_psutil", procs)))

    supervisor._terminate_tree(99, "handle", 1500)

    assert events == [
        "graceful",
        ("wait", 1500),
        ("terminate_psutil", ["child"]),
        "force",
        ("kill_psutil", ["child"]),
        ("wait", 1500),
    ]


def test_process_supervisor_terminate_tree_returns_after_graceful_exit(monkeypatch):
    supervisor = supervisor_mod.ProcessSupervisor()
    events = []
    monkeypatch.setattr(supervisor, "_descendants", lambda pid: ["child"])
    monkeypatch.setattr(supervisor, "_graceful_stop", lambda handle: events.append("graceful"))
    monkeypatch.setattr(supervisor, "_wait_handle", lambda handle, timeout: events.append(("wait", timeout)))
    monkeypatch.setattr(supervisor, "_terminate_psutil", lambda procs: events.append(("terminate_psutil", procs)))
    monkeypatch.setattr(supervisor, "_wait_pid_exit", lambda pid, timeout: True)
    monkeypatch.setattr(supervisor, "_force_stop", lambda handle: events.append("force"))

    supervisor._terminate_tree(99, "handle", -1)

    assert events == [
        "graceful",
        ("wait", -1),
        ("terminate_psutil", ["child"]),
    ]
