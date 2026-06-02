from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.modules.commands as commands_mod


class _Logger:
    def __init__(self):
        self.debugs = []
        self.warnings = []
        self.errors = []

    def debug(self, msg, *args, **kwargs):
        self.debugs.append(str(msg))

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(str(msg))

    def error(self, msg, *args, **kwargs):
        self.errors.append(str(msg))


def _mk_module(name: str = "m"):
    return SimpleNamespace(
        name=name,
        is_active=True,
        type="python",
        owner_id="owner",
        _background_tasks=[],
        _stop_events={},
        _command_states={},
    )


def _patch_commands_deps(
    monkeypatch,
    *,
    logger: _Logger | None = None,
    registry=None,
    store=None,
    now=None,
    lease_ttl: float = 3.0,
    poll: float = 0.0,
) -> _Logger:
    resolved_logger = logger or _Logger()
    monkeypatch.setattr(
        commands_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=resolved_logger),
    )
    if registry is not None:
        monkeypatch.setattr(commands_mod, "module_command_registry", registry)
    if store is not None:
        monkeypatch.setattr(commands_mod, "module_command_state_store", store)
    if now is not None:
        monkeypatch.setattr(commands_mod, "utc_now_naive", lambda: now)
    monkeypatch.setattr(commands_mod, "DEFAULT_LEASE_TTL_SECONDS", lease_ttl)
    monkeypatch.setattr(commands_mod, "SCHEDULE_POLL_SECONDS", poll)
    return resolved_logger


def test_start_background_commands_and_refresh_state_branches(monkeypatch):
    logger = _Logger()
    module = _mk_module()
    module._start_scheduled_command = lambda _d: None
    module._start_managed_command = lambda *_a, **_k: None
    module.is_active = False

    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        registry=SimpleNamespace(get_all=lambda module_name=None: []),
        store=SimpleNamespace(ensure_registered=lambda _d: None, get=lambda _name: None),
    )
    commands_mod.start_background_commands(module)

    module2 = _mk_module()
    module2._background_tasks = [object()]
    module2._start_scheduled_command = lambda _d: None
    module2._start_managed_command = lambda *_a, **_k: None
    commands_mod.start_background_commands(module2)

    calls = []
    module3 = _mk_module("m3")
    module3._start_scheduled_command = lambda d: calls.append(("schedule", d.name))
    module3._start_managed_command = lambda d, restart_on_exit, run_once_after_completion: calls.append(
        ("managed", d.name, restart_on_exit, run_once_after_completion)
    )
    defs = [
        SimpleNamespace(name="a", lifecycle="schedule"),
        SimpleNamespace(name="b", lifecycle="long_run", restart_on_exit=True),
        SimpleNamespace(name="c", lifecycle="single_run"),
        SimpleNamespace(name="d", lifecycle="unknown"),
    ]
    reg = []
    store = SimpleNamespace(
            ensure_registered=lambda d: reg.append(d.name),
            get=lambda _name: None,
    )
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        registry=SimpleNamespace(get_all=lambda module_name=None: defs),
        store=store,
    )
    commands_mod.start_background_commands(module3)
    assert ("schedule", "a") in calls
    assert ("managed", "b", True, False) in calls
    assert ("managed", "c", False, True) in calls
    assert reg == ["a", "b", "c", "d"]

    definition = SimpleNamespace(name="x", lifecycle="schedule")
    module3._state_for = lambda d: commands_mod.state_for(module3, d)
    state = commands_mod.state_for(module3, definition)
    snap = SimpleNamespace(
        run_count=7,
        last_started_at=datetime(2026, 1, 1, 10, 0, 0),
        last_finished_at=datetime(2026, 1, 1, 10, 1, 0),
        status="failed",
        last_error="boom",
        next_run_at=datetime(2026, 1, 1, 11, 0, 0),
    )
    monkeypatch.setattr(commands_mod, "module_command_state_store", SimpleNamespace(get=lambda _name: snap))
    out = commands_mod.refresh_state(module3, definition)
    assert out is state
    assert state.runs == 7
    assert state.last_status == "failed"
    assert state.last_error == "boom"


@pytest.mark.asyncio
async def test_invoke_command_payload_and_kwargs(monkeypatch):
    logger = _Logger()
    captured = {}

    async def _invoke(**kwargs):
        captured.update(kwargs)
        return {"ok": True}

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(invoke=_invoke)),
    )

    module = _mk_module("demo")
    state = SimpleNamespace(last_status="idle", last_error="x")
    module._refresh_state = lambda _d: state

    def _fn(stop_event=None, command_name=None, module_name=None, ignored=None):
        return None

    definition = SimpleNamespace(
        name="cmd.run",
        lifecycle="single_run",
        func=_fn,
        handler_module="handlers.mod",
        handler_name="run",
    )
    _patch_commands_deps(monkeypatch, logger=logger)
    await commands_mod.invoke_command(module, definition, stop_event=asyncio.Event())
    assert captured["operation"] == "command"
    assert captured["payload"]["include_stop_event"] is True
    assert captured["payload"]["call_kwargs"] == {
        "command_name": "cmd.run",
        "module_name": "demo",
    }
    assert state.last_status == "running"
    assert state.last_error is None


@pytest.mark.asyncio
async def test_start_managed_command_paths(monkeypatch):
    logger = _Logger()
    original_sleep = commands_mod.asyncio.sleep

    async def _fast_sleep(_delay):
        await original_sleep(0)

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _fast_sleep)

    module = _mk_module("managed")
    tasks = []
    module._track_task = lambda t: tasks.append(t)
    module._lease_heartbeat = lambda _name: original_sleep(3600)
    module._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    module._invoke_command = lambda _d, stop_event=None: original_sleep(0)

    class _Store:
        def __init__(self):
            self.seq = [False, True]
            self.finished = []

        def try_acquire_lease(self, *_a, **_k):
            return self.seq.pop(0)

        def get(self, _name):
            return SimpleNamespace(run_count=0, status="running")

        def finish_run(self, name, **kwargs):
            self.finished.append((name, kwargs))

    store = _Store()
    _patch_commands_deps(monkeypatch, logger=logger, store=store)
    definition = SimpleNamespace(name="job", lifecycle="long_run")
    commands_mod.start_managed_command(
        module,
        definition,
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    await tasks[0]
    assert store.finished and store.finished[0][1]["status"] == "completed"

    module2 = _mk_module("managed2")
    tasks2 = []
    module2._track_task = lambda t: tasks2.append(t)
    module2._lease_heartbeat = lambda _name: original_sleep(3600)
    module2._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    module2._invoke_command = lambda _d, stop_event=None: (_ for _ in ()).throw(asyncio.CancelledError())
    store2 = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: True,
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda name, **kwargs: logger.warning(f"{name}:{kwargs.get('status')}"),
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store2)
    commands_mod.start_managed_command(
        module2,
        SimpleNamespace(name="job.cancel", lifecycle="long_run"),
        restart_on_exit=True,
        run_once_after_completion=False,
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks2[0]

    module3 = _mk_module("managed3")
    tasks3 = []
    module3._track_task = lambda t: tasks3.append(t)
    module3._lease_heartbeat = lambda _name: original_sleep(3600)
    module3._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    async def _raise(_d, stop_event=None):
        raise RuntimeError("invoke boom")

    module3._invoke_command = _raise
    store3 = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: True,
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store3)
    commands_mod.start_managed_command(
        module3,
        SimpleNamespace(name="job.error", lifecycle="long_run"),
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    await tasks3[0]
    assert logger.errors

    module4 = _mk_module("managed4")
    tasks4 = []
    module4._track_task = lambda t: tasks4.append(t)
    module4._lease_heartbeat = lambda _name: original_sleep(3600)
    module4._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    module4._invoke_command = lambda _d, stop_event=None: original_sleep(0)
    store4 = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: False,
        get=lambda _name: SimpleNamespace(run_count=1, status="completed"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store4)
    commands_mod.start_managed_command(
        module4,
        SimpleNamespace(name="job.done", lifecycle="single_run"),
        restart_on_exit=False,
        run_once_after_completion=True,
    )
    await tasks4[0]


@pytest.mark.asyncio
async def test_start_scheduled_command_success_and_failure(monkeypatch):
    logger = _Logger()
    original_sleep = commands_mod.asyncio.sleep
    module = _mk_module("sched")
    tasks = []
    module._track_task = lambda t: tasks.append(t)
    module._lease_heartbeat = lambda _name: original_sleep(3600)
    now = datetime(2026, 1, 1, 12, 0, 0)
    state = SimpleNamespace(next_run_at=None)
    module._refresh_state = lambda _d: state
    compute_calls = {"n": 0}

    def _compute(_d, _now):
        compute_calls["n"] += 1
        if compute_calls["n"] == 1:
            return now
        return now + timedelta(seconds=5)

    module._compute_next_run = _compute
    module._invoke_command = lambda _d: original_sleep(0)

    finished = asyncio.Event()
    finished_rows = []

    def _finish(name, **kwargs):
        finished_rows.append((name, kwargs))
        if kwargs.get("status") == "completed":
            finished.set()

    store = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: True,
        set_next_run=lambda *_a, **_k: None,
        finish_run=_finish,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store, now=now)

    commands_mod.start_scheduled_command(
        module, SimpleNamespace(name="sched.ok", lifecycle="schedule")
    )
    await asyncio.wait_for(finished.wait(), timeout=1.0)
    tasks[0].cancel()
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
    assert any(row[1].get("status") == "completed" for row in finished_rows)

    call_count = {"n": 0}

    async def _sleep_for_failure(delay):
        call_count["n"] += 1
        if delay >= 1:
            raise asyncio.CancelledError()
        await original_sleep(0)

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _sleep_for_failure)

    module2 = _mk_module("sched2")
    tasks2 = []
    module2._track_task = lambda t: tasks2.append(t)
    module2._lease_heartbeat = lambda _name: original_sleep(3600)
    module2._refresh_state = lambda _d: SimpleNamespace(next_run_at=None)
    module2._compute_next_run = lambda _d, _now: now

    async def _boom(_d):
        raise RuntimeError("cmd failure")

    module2._invoke_command = _boom
    failed_rows = []
    store2 = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: True,
        set_next_run=lambda *_a, **_k: None,
        finish_run=lambda name, **kwargs: failed_rows.append((name, kwargs)),
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store2, now=now)
    commands_mod.start_scheduled_command(
        module2, SimpleNamespace(name="sched.fail", lifecycle="schedule")
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks2[0]
    assert any(row[1].get("status") == "failed" for row in failed_rows)
    assert logger.errors


@pytest.mark.asyncio
async def test_lease_heartbeat_retries_then_stops(monkeypatch):
    logger = _Logger()
    original_sleep = commands_mod.asyncio.sleep

    async def _fast_sleep(_delay):
        await original_sleep(0)

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _fast_sleep)

    beats = {"n": 0}

    def _heartbeat(_command_name, owner, lease_ttl_seconds):
        beats["n"] += 1
        return beats["n"] < 2

    module = _mk_module("hb")
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(heartbeat=_heartbeat),
    )
    await commands_mod.lease_heartbeat(module, "cmd.hb")
    assert beats["n"] == 2
    assert logger.warnings


@pytest.mark.asyncio
async def test_start_managed_command_remaining_branches(monkeypatch):
    logger = _Logger()
    original_sleep = commands_mod.asyncio.sleep
    class _FlipBool:
        def __init__(self):
            self.calls = 0

        def __bool__(self):
            self.calls += 1
            return self.calls == 1

    module_a = _mk_module("managed.a")
    tasks_a = []
    module_a._track_task = lambda t: tasks_a.append(t)
    module_a._lease_heartbeat = lambda _name: original_sleep(3600)
    module_a._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    module_a._invoke_command = lambda _d, stop_event=None: original_sleep(0)

    async def _cancel_sleep(_delay):
        raise asyncio.CancelledError()

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _cancel_sleep)
    store_a = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: False,
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store_a)
    commands_mod.start_managed_command(
        module_a,
        SimpleNamespace(name="job.cancel.false", lifecycle="long_run"),
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks_a[0]

    module_b = _mk_module("managed.b")
    tasks_b = []
    module_b._track_task = lambda t: tasks_b.append(t)
    module_b._lease_heartbeat = lambda _name: original_sleep(3600)
    module_b._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    module_b._invoke_command = lambda _d, stop_event=None: original_sleep(0)

    async def _runtime_sleep(_delay):
        raise RuntimeError("sleep boom")

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _runtime_sleep)
    store_b = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: False,
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store_b)
    commands_mod.start_managed_command(
        module_b,
        SimpleNamespace(name="job.error.false", lifecycle="long_run"),
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    with pytest.raises(RuntimeError):
        await tasks_b[0]

    module_c = _mk_module("managed.c")
    tasks_c = []
    module_c._track_task = lambda t: tasks_c.append(t)
    module_c._lease_heartbeat = lambda _name: original_sleep(3600)
    module_c._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)

    async def _invoke_boom(_d, stop_event=None):
        raise RuntimeError("invoke boom restart")

    module_c._invoke_command = _invoke_boom

    async def _stop_after_restart(delay):
        if delay == 1:
            raise asyncio.CancelledError()
        await original_sleep(0)

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _stop_after_restart)
    store_c = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: True,
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store_c)
    commands_mod.start_managed_command(
        module_c,
        SimpleNamespace(name="job.restart.error", lifecycle="long_run"),
        restart_on_exit=True,
        run_once_after_completion=False,
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks_c[0]

    module_d = _mk_module("managed.d")
    tasks_d = []
    module_d._track_task = lambda t: tasks_d.append(t)
    module_d._lease_heartbeat = lambda _name: original_sleep(3600)
    module_d._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)

    async def _raise_cancel(_d, stop_event=None):
        raise asyncio.CancelledError()

    module_d._invoke_command = _raise_cancel
    monkeypatch.setattr(commands_mod.asyncio, "sleep", lambda delay: original_sleep(0))
    store_d = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: _FlipBool(),
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store_d)
    commands_mod.start_managed_command(
        module_d,
        SimpleNamespace(name="job.flip.cancel", lifecycle="long_run"),
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks_d[0]

    module_e = _mk_module("managed.e")
    tasks_e = []
    module_e._track_task = lambda t: tasks_e.append(t)
    module_e._lease_heartbeat = lambda _name: original_sleep(3600)
    module_e._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)

    async def _raise_exc(_d, stop_event=None):
        raise RuntimeError("flip exception")

    module_e._invoke_command = _raise_exc
    store_e = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: _FlipBool(),
        get=lambda _name: SimpleNamespace(run_count=0, status="running"),
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store_e)
    commands_mod.start_managed_command(
        module_e,
        SimpleNamespace(name="job.flip.error", lifecycle="long_run"),
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    await tasks_e[0]


@pytest.mark.asyncio
async def test_start_scheduled_command_remaining_branches(monkeypatch):
    logger = _Logger()
    original_sleep = commands_mod.asyncio.sleep
    now = datetime(2026, 1, 1, 13, 0, 0)

    module = _mk_module("sched.remaining")
    tasks = []
    module._track_task = lambda t: tasks.append(t)
    module._lease_heartbeat = lambda _name: original_sleep(3600)
    state = SimpleNamespace(next_run_at=now)
    module._refresh_state = lambda _d: state
    module._compute_next_run = lambda _d, _now: now + timedelta(seconds=10)
    module._invoke_command = lambda _d: original_sleep(0)

    sleep_calls = {"n": 0}

    async def _sleep_driver(delay):
        sleep_calls["n"] += 1
        if delay == 0.0 and sleep_calls["n"] == 1:
            await original_sleep(0)
            return
        if delay == 0.0:
            raise asyncio.CancelledError()
        await original_sleep(0)

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _sleep_driver)
    store = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: False,
        set_next_run=lambda *_a, **_k: None,
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=logger, store=store, now=now)

    commands_mod.start_scheduled_command(
        module, SimpleNamespace(name="sched.remaining", lifecycle="schedule")
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]


@pytest.mark.asyncio
async def test_start_scheduled_command_wait_branch(monkeypatch):
    original_sleep = commands_mod.asyncio.sleep
    now = datetime(2026, 1, 1, 14, 0, 0)

    module = _mk_module("sched.wait")
    tasks = []
    module._track_task = lambda t: tasks.append(t)
    module._lease_heartbeat = lambda _name: original_sleep(3600)
    state = SimpleNamespace(next_run_at=now + timedelta(seconds=10))
    module._refresh_state = lambda _d: state
    module._compute_next_run = lambda _d, _now: now + timedelta(seconds=10)
    module._invoke_command = lambda _d: original_sleep(0)

    calls = {"n": 0}

    async def _sleep_wait(delay):
        calls["n"] += 1
        if delay == 5.0:
            state.next_run_at = now
            await original_sleep(0)
            return
        raise asyncio.CancelledError()

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _sleep_wait)
    store = SimpleNamespace(
        try_acquire_lease=lambda *_a, **_k: False,
        set_next_run=lambda *_a, **_k: None,
        finish_run=lambda *a, **k: None,
    )
    _patch_commands_deps(monkeypatch, logger=_Logger(), store=store, now=now)
    commands_mod.start_scheduled_command(
        module, SimpleNamespace(name="sched.wait", lifecycle="schedule")
    )
    with pytest.raises(asyncio.CancelledError):
        await tasks[0]
