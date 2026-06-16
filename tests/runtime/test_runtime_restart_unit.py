from __future__ import annotations

from types import SimpleNamespace

import pytest


class _ImmediateThread:
    def __init__(self, *, target, name=None, daemon=None):
        self._target = target
        self.name = name
        self.daemon = daemon

    def start(self):
        self._target()


def test_request_application_restart_core_child_stops_orchestrator(monkeypatch):
    from democrai.core.runtime.lifecycle import restart

    stopped = []
    terminated = []
    socket_cleanups = []
    exits = []
    process = object()
    ctx = SimpleNamespace(
        network=SimpleNamespace(stop=lambda: stopped.append("network")),
        engine_orchestrator_process=process,
        config=object(),
    )

    monkeypatch.setattr(restart.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(restart.threading, "Thread", _ImmediateThread)
    monkeypatch.setenv("DEMOCRAI_CORE_PROCESS", "1")
    monkeypatch.setattr(
        "democrai.core.runtime.lifecycle.process_supervisor.process_supervisor",
        SimpleNamespace(
            terminate=lambda handle, timeout_ms=0: terminated.append(
                (handle, timeout_ms)
            )
        ),
    )
    from democrai.core.application.ai.engine.orchestrator.config import (
        EngineOrchestratorConfig,
    )

    class _EngineOrchestratorConfig:
        def cleanup_socket(self):
            socket_cleanups.append(ctx.config)

    monkeypatch.setattr(
        EngineOrchestratorConfig,
        "load",
        lambda _config: _EngineOrchestratorConfig(),
    )

    def _exit(code):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(restart.os, "_exit", _exit)

    with pytest.raises(SystemExit):
        restart.request_application_restart(ctx, delay_seconds=0)

    assert stopped == ["network"]
    assert terminated == [(process, 5000)]
    assert ctx.engine_orchestrator_process is None
    assert socket_cleanups == [ctx.config]
    assert exits == [restart.APPLICATION_RESTART_EXIT_CODE]


def test_request_application_restart_core_child_without_orchestrator_keeps_exit_code(
    monkeypatch,
):
    from democrai.core.runtime.lifecycle import restart

    exits = []
    ctx = SimpleNamespace(
        network=SimpleNamespace(stop=lambda: None),
        engine_orchestrator_process=None,
        config=object(),
    )

    monkeypatch.setattr(restart.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(restart.threading, "Thread", _ImmediateThread)
    monkeypatch.setenv("DEMOCRAI_CORE_PROCESS", "1")

    def _exit(code):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(restart.os, "_exit", _exit)

    with pytest.raises(SystemExit):
        restart.request_application_restart(ctx, delay_seconds=0)

    assert exits == [restart.APPLICATION_RESTART_EXIT_CODE]


def test_request_application_restart_core_child_exits_when_orchestrator_cleanup_fails(
    monkeypatch,
):
    from democrai.core.runtime.lifecycle import restart

    errors = []
    exits = []
    process = object()
    ctx = SimpleNamespace(
        network=SimpleNamespace(stop=lambda: None),
        engine_orchestrator_process=process,
        config=object(),
        logger=SimpleNamespace(error=lambda message: errors.append(message)),
    )

    monkeypatch.setattr(restart.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(restart.threading, "Thread", _ImmediateThread)
    monkeypatch.setenv("DEMOCRAI_CORE_PROCESS", "1")

    def _terminate(_handle, timeout_ms=0):
        raise RuntimeError("terminate_failed")

    monkeypatch.setattr(
        "democrai.core.runtime.lifecycle.process_supervisor.process_supervisor",
        SimpleNamespace(terminate=_terminate),
    )
    from democrai.core.application.ai.engine.orchestrator.config import (
        EngineOrchestratorConfig,
    )

    class _EngineOrchestratorConfig:
        def cleanup_socket(self):
            return None

    monkeypatch.setattr(
        EngineOrchestratorConfig,
        "load",
        lambda _config: _EngineOrchestratorConfig(),
    )

    def _exit(code):
        exits.append(code)
        raise SystemExit(code)

    monkeypatch.setattr(restart.os, "_exit", _exit)

    with pytest.raises(SystemExit):
        restart.request_application_restart(ctx, delay_seconds=0)

    assert ctx.engine_orchestrator_process is None
    assert exits == [restart.APPLICATION_RESTART_EXIT_CODE]
    assert any("terminate_failed" in message for message in errors)


def test_request_application_restart_non_core_child_execs_current_command(monkeypatch):
    from democrai.core.runtime.lifecycle import restart

    execs = []
    ctx = SimpleNamespace(network=SimpleNamespace(stop=lambda: None))

    monkeypatch.setattr(restart.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(restart.threading, "Thread", _ImmediateThread)
    monkeypatch.delenv("DEMOCRAI_CORE_PROCESS", raising=False)

    def _execv(executable, argv):
        execs.append((executable, argv))
        raise SystemExit(0)

    monkeypatch.setattr(restart.os, "execv", _execv)

    with pytest.raises(SystemExit):
        restart.request_application_restart(ctx, delay_seconds=0)

    assert execs == [(restart.sys.executable, [restart.sys.executable] + restart.sys.argv)]
