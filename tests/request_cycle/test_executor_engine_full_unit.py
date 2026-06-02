from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from democrai.core.application.request_cycle.effects import (
    ConfirmEffect,
    NavigateEffect,
    NotifyEffect,
    RefreshModulesEffect,
    RenderEffect,
    ScrollEffect,
    SetJwtEffect,
    StartPipelineEffect,
    UiMessagesEffect,
)
from democrai.core.runtime.foundation.app import RequestContext


class _Logger:
    def __init__(self):
        self.debugs = []
        self.infos = []
        self.warns = []
        self.errors = []

    def debug(self, msg, *_a, **_k):
        self.debugs.append(msg)

    def info(self, msg, *_a, **_k):
        self.infos.append(msg)

    def warning(self, msg, *_a, **_k):
        self.warns.append(msg)

    def error(self, msg, *_a, **_k):
        self.errors.append(msg)


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Profiler:
    def span(self, _name):
        return _Span()

    def finish(self):
        return None


class _SessionService:
    def __init__(self):
        self.persisted = []
        self.identity_calls = []

    def persist_identity_change(self, session, user, session_key):
        self.identity_calls.append((session, user, session_key))
        return "ukey"

    def persist(self, key):
        self.persisted.append(key)


@pytest.mark.asyncio
async def test_executor_execute_effect_matrix_and_jwt_injection(monkeypatch):
    mod = __import__("democrai.core.application.request_cycle.executor", fromlist=["dummy"])
    logger = _Logger()

    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_debug_auth_flow", lambda *_a, **_k: None)
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            container=SimpleNamespace(get=lambda _k: None),
            connection_registry=None,
            redis_task_bridge=None,
        ),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.handler.actions.base_handlers",
        SimpleNamespace(_get_modules_list=lambda _s: {"modules": ["a"]}),
    )

    executor = mod.EffectExecutor()
    notify_calls = []
    monkeypatch.setattr(executor, "_handle_notify", lambda effect, session, context: notify_calls.append(effect.channel))
    async def _start_pipeline_stub(effect, session, context, action_name):
        return {"pipeline": {"taskId": "t1"}}

    async def _handle_confirmation_stub(*_a, **_k):
        return [{"confirm": True}]

    monkeypatch.setattr(executor, "_start_pipeline", _start_pipeline_stub)
    monkeypatch.setattr(executor, "_handle_confirmation", _handle_confirmation_stub)

    async def _render(_session):
        return [{"surfaceUpdate": {"surfaceId": "main"}}]

    effects = [
        NavigateEffect("/x", render=False),
        RenderEffect(path="/y"),
        UiMessagesEffect([{"m": 1}]),
        StartPipelineEffect(task="task", label="L"),
        ConfirmEffect(via="dialog"),
        NotifyEffect(channel="toast", payload={"text": "x"}),
        RefreshModulesEffect(),
        ScrollEffect(component_id="list"),
        SetJwtEffect(token="jwt"),
    ]
    session = {"user": {"id": 1}}
    ctx = RequestContext(
        request_id="r1",
        user=1,
        role="user",
        organization_id=None,
        access_level=3,
        channel="ipc",
        session_key="s1",
    )
    service = _SessionService()

    out = await executor.execute(
        effects=effects,
        session=session,
        context=ctx,
        action_name="demo.action",
        action_context={},
        render=_render,
        session_service=service,
    )
    assert out
    assert out[0]["jwt"] == "jwt"
    assert "current_path" in out[0]
    assert notify_calls == ["toast"]
    assert service.persisted == ["ukey"]


@pytest.mark.asyncio
async def test_executor_execute_jwt_appended_without_mutations(monkeypatch):
    mod = __import__("democrai.core.application.request_cycle.executor", fromlist=["dummy"])
    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_debug_auth_flow", lambda *_a, **_k: None)
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=_Logger(),
            container=SimpleNamespace(get=lambda _k: None),
            connection_registry=None,
            redis_task_bridge=None,
        ),
    )

    executor = mod.EffectExecutor()
    service = _SessionService()
    ctx = RequestContext(
        request_id="r2",
        user=1,
        role="user",
        organization_id=None,
        access_level=3,
        channel="ipc",
        session_key="s2",
    )
    out = await executor.execute(
        effects=[SetJwtEffect(token="jwt2")],
        session={"user": {"id": 1}},
        context=ctx,
        action_name="a",
        action_context={},
        render=lambda _s: [],
        session_service=service,
    )
    assert out == [{"jwt": "jwt2"}]
    assert service.persisted == []


@pytest.mark.asyncio
async def test_executor_start_pipeline_and_build_coroutine_variants(monkeypatch):
    mod = __import__("democrai.core.application.request_cycle.executor", fromlist=["dummy"])
    logger = _Logger()
    ctx = RequestContext(
        request_id="reqp",
        user=7,
        role="admin",
        organization_id=2,
        access_level=1,
        channel="ipc",
        session_key="ss",
        stream_id="st",
    )
    executor = mod.EffectExecutor()

    class _TM:
        async def submit(self, **kwargs):
            return "task-1"

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(task_manager=_TM(), logger=logger))
    monkeypatch.setattr(executor, "_build_pipeline_coroutine", lambda *a, **k: object())
    msg = await executor._start_pipeline(
        StartPipelineEffect(task="x", label="L"), {"user": {"id": "7"}}, ctx, "demo.action"
    )
    assert msg["pipeline"]["taskId"] == "task-1"

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(task_manager=None, logger=logger))
    with pytest.raises(RuntimeError):
        await executor._start_pipeline(StartPipelineEffect(task="x", label="L"), {"user": {"id": "7"}}, ctx, "a")

    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(task_manager=_TM(), logger=logger))
    with pytest.raises(ValueError):
        await executor._start_pipeline(StartPipelineEffect(task="x", label="L"), {"user": {}}, ctx, "a")

    # _build_pipeline_coroutine paths
    executor2 = mod.EffectExecutor()
    set_calls = []
    monkeypatch.setattr(mod, "set_req_ctx", lambda _c: set_calls.append("set") or "tok")
    monkeypatch.setattr(mod, "reset_req_ctx", lambda _t: set_calls.append("reset"))

    async def _async_task(**kwargs):
        return {"ok": kwargs["v"]}

    def _sync_task(**kwargs):
        return kwargs["v"] + 1

    monkeypatch.setattr(mod.task_registry, "get", lambda name: _async_task if name == "async.name" else _sync_task if name == "sync.name" else None)
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    r1 = await executor2._build_pipeline_coroutine(StartPipelineEffect(task="async.name", label="L", args={"v": 3}), ctx, "a")
    r2 = await executor2._build_pipeline_coroutine(StartPipelineEffect(task="sync.name", label="L", args={"v": 3}), ctx, "a")
    assert r1 == {"ok": 3}
    assert r2 == 4

    async def _direct():
        return 9

    assert await executor2._build_pipeline_coroutine(StartPipelineEffect(task=_direct(), label="L"), ctx, "a") == 9
    assert await executor2._build_pipeline_coroutine(StartPipelineEffect(task=lambda **_k: 5, label="L"), ctx, "a") == 5

    async def _callable_async(**_k):
        return 6

    assert await executor2._build_pipeline_coroutine(StartPipelineEffect(task=_callable_async, label="L"), ctx, "a") == 6

    with pytest.raises(ValueError):
        await executor2._build_pipeline_coroutine(StartPipelineEffect(task="missing", label="L"), ctx, "a")
    with pytest.raises(ValueError):
        await executor2._build_pipeline_coroutine(StartPipelineEffect(task=123, label="L"), ctx, "a")

    assert set_calls


@pytest.mark.asyncio
async def test_executor_confirmation_modal_notify_and_send_to_user(monkeypatch):
    mod = __import__("democrai.core.application.request_cycle.executor", fromlist=["dummy"])
    logger = _Logger()
    enqueue_calls = []
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            container=SimpleNamespace(get=lambda _k: None),
            connection_registry=None,
            redis_task_bridge=None,
        ),
    )
    executor = mod.EffectExecutor()
    monkeypatch.setattr(executor, "_notification_queue", SimpleNamespace(enqueue=lambda **kw: enqueue_calls.append(kw)))

    session = {"user": {"id": 7}}
    ctx = RequestContext(
        request_id="r3",
        user=7,
        role="user",
        organization_id=3,
        access_level=2,
        channel="ipc",
    )
    render_calls = []
    async def _render_confirmation(**kwargs):
        render_calls.append(dict(kwargs))
        return [{"rendered": True}]
    monkeypatch.setattr(executor, "_build_confirmation_modal_messages", _render_confirmation)

    response = await executor._handle_confirmation(
        ConfirmEffect(via="both", path="/m", params={"a": 1}, render=True),
        session=session,
        context=ctx,
        action_name="act",
    )
    assert response == [{"rendered": True}]
    assert render_calls[0]["path"] == "/m"
    assert render_calls

    # _build_confirmation_modal_messages
    _comp = SimpleNamespace(to_dict=lambda: {"id": "c1"})
    fake_builder = SimpleNamespace(
        get_roots=lambda: [SimpleNamespace(id="root1")],
        _components=[_comp],
    )
    async def _resolve_builder(*_a, **_k):
        return fake_builder

    monkeypatch.setattr(mod.Router, "resolve", _resolve_builder)
    monkeypatch.setattr(
        mod,
        "sdk",
        SimpleNamespace(
            ui=SimpleNamespace(
                Dialog=lambda *a, **k: SimpleNamespace(id="dlg", to_dict=lambda: {"id": "dlg"})
            )
        ),
    )
    modal_msgs = await executor._build_confirmation_modal_messages(path="/x", params={}, session={})
    assert isinstance(modal_msgs, list)

    fake_builder_empty = SimpleNamespace(get_roots=lambda: [SimpleNamespace(id="")], _components=[])

    async def _resolve_builder_empty(*_a, **_k):
        return fake_builder_empty

    monkeypatch.setattr(mod.Router, "resolve", _resolve_builder_empty)
    assert await executor._build_confirmation_modal_messages(path="/x", params={}, session={}) == [{"rendered": True}]

    # _handle_notify
    class _Notifier:
        def __init__(self, mode="ok"):
            self.mode = mode
            self.calls = []

        def notify(self, **kwargs):
            self.calls.append(kwargs)
            if self.mode == "typeerror":
                raise TypeError("sig")
            if self.mode == "error":
                raise RuntimeError("boom")

    notifier = _Notifier()
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            container=SimpleNamespace(get=lambda _k: notifier),
            connection_registry=None,
            redis_task_bridge=None,
        ),
    )
    executor._handle_notify(NotifyEffect(channel="inapp", payload={"k": 1}, user_id=7), session, ctx)
    assert notifier.calls

    notifier2 = _Notifier(mode="typeerror")
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            container=SimpleNamespace(get=lambda _k: notifier2),
            connection_registry=None,
            redis_task_bridge=None,
        ),
    )
    executor._handle_notify(NotifyEffect(channel="inapp", payload={"k": 1}, user_id=7), session, ctx)

    # notifier fails -> builtin branch with queue fallback
    notifier3 = _Notifier(mode="error")
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=logger,
            container=SimpleNamespace(get=lambda _k: notifier3),
            connection_registry=None,
            redis_task_bridge=None,
        ),
    )
    original_send_to_user = executor._send_to_user
    monkeypatch.setattr(executor, "_send_to_user", lambda *_a, **_k: False)
    executor._handle_notify(NotifyEffect(channel="toast", payload={"text": "x"}, user_id=7), session, ctx)
    assert enqueue_calls
    monkeypatch.setattr(executor, "_send_to_user", original_send_to_user)
    executor._handle_notify(NotifyEffect(channel="email", payload={"x": 1}, user_id=7), session, ctx)
    executor._handle_notify(NotifyEffect(channel="unknown", payload={"x": 1}, user_id=7), session, ctx)

    # no user -> warning/skip
    executor._handle_notify(NotifyEffect(channel="inapp", payload={"x": 1}, user_id=None), {"user": {}}, ctx)
    assert logger.warns

    # _send_to_user branches
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(connection_registry=None, redis_task_bridge=None, logger=logger))
    assert executor._send_to_user(1, None, {"m": 1}) is False

    class _Registry:
        def __init__(self, conns):
            self.conns = conns

        def get_connections(self, *_a, **_k):
            return self.conns

    bridge_calls = []
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(connection_registry=_Registry([]), redis_task_bridge=SimpleNamespace(publish=lambda *a: bridge_calls.append(a)), logger=logger),
    )
    assert executor._send_to_user(1, None, {"m": 1}) is True
    assert bridge_calls

    class _Bus:
        def __init__(self, fail=False):
            self.fail = fail
            self.sent = []

        def send(self, client_id, message):
            if self.fail:
                raise RuntimeError("x")
            self.sent.append((client_id, message))

    b1 = _Bus()
    b2 = _Bus(fail=True)
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(connection_registry=_Registry([(b1, "c1"), (b2, "c2")]), redis_task_bridge=None, logger=logger),
    )
    assert executor._send_to_user(1, None, {"m": 2}) is True
    assert b1.sent and logger.errors


@pytest.mark.asyncio
async def test_engine_handle_and_internal_paths(monkeypatch):
    mod = __import__("democrai.core.application.request_cycle.engine", fromlist=["dummy"])
    logger = _Logger()
    lock_calls = []

    class _Locks:
        def __init__(self, acquire_result=True):
            self.acquire_result = acquire_result

        async def acquire(self, key, rid):
            lock_calls.append(("acquire", key, rid))
            return self.acquire_result

        async def release(self, key, rid):
            lock_calls.append(("release", key, rid))
            return True

    modules_runtime = SimpleNamespace(ensure_started=lambda: asyncio.sleep(0))
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(action_lock_manager=_Locks(), modules=modules_runtime, logger=logger),
    )
    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "ensure_request_profile", lambda *_a, **_k: (_Profiler(), "tok", True))
    monkeypatch.setattr(mod, "stop_request_profile", lambda _tok: None)
    monkeypatch.setattr(mod, "current_request_profiler", lambda: _Profiler())
    auth_service_mod = __import__(
        "democrai.core.application.auth.service",
        fromlist=["get_user_permissions"],
    )
    monkeypatch.setattr(auth_service_mod, "get_user_permissions", lambda _u: ["p1"])

    engine = mod.RequestCycleEngine()

    req = RequestContext(
        request_id="rq1",
        user=7,
        role="user",
        organization_id=1,
        access_level=2,
        channel="ipc",
        session_key="s1",
    )
    monkeypatch.setattr(mod, "req_ctx", lambda: req)

    async def _render(session, **kwargs):
        return [{"render": kwargs.get("force_shell", False)}]

    # ping
    out_ping = await engine.handle(
        {"type": "ping"},
        get_session=lambda u, r: {},
        render=_render,
        dispatcher=SimpleNamespace(dispatch=lambda *_a, **_k: asyncio.sleep(0)),
        session_service=SimpleNamespace(),
    )
    assert out_ping[0]["type"] == "pong"

    # init
    sess_init = {"active_main_template": "x", "_active_main_template": "y"}
    out_init = await engine.handle(
        {"type": "init"},
        get_session=lambda u, r: sess_init,
        render=_render,
        dispatcher=SimpleNamespace(dispatch=lambda *_a, **_k: asyncio.sleep(0)),
        session_service=SimpleNamespace(),
    )
    assert out_init == [{"render": True}]
    assert "active_main_template" not in sess_init and "_active_main_template" not in sess_init

    # no action
    out_empty = await engine.handle(
        {"type": "noop"},
        get_session=lambda u, r: {},
        render=_render,
        dispatcher=SimpleNamespace(dispatch=lambda *_a, **_k: asyncio.sleep(0)),
        session_service=SimpleNamespace(),
    )
    assert out_empty == []

    # permissions cache branches
    monkeypatch.setattr(mod.time, "monotonic", lambda: 100.0)
    s = {
        "_perm_cache_user": 7,
        "_perm_cache_ts": 90.0,
        "_perm_cache_values": ["a", 2],
    }
    assert engine._get_permissions(7, s) == ["a", "2"]
    monkeypatch.setattr(auth_service_mod, "get_user_permissions", lambda _u: ["p1"])
    monkeypatch.setattr(mod.time, "monotonic", lambda: 1000.0)
    assert engine._get_permissions(7, s) == ["p1"]
    assert engine._get_permissions(None, s) == []
    with monkeypatch.context() as setup_context:
        permission_calls = []
        setup_context.setattr(
            mod,
            "app_ctx",
            lambda: SimpleNamespace(setup_mode=True),
        )
        setup_context.setattr(
            auth_service_mod,
            "get_user_permissions",
            lambda _u: permission_calls.append(_u),
        )
        assert engine._get_permissions(7, {}) == []
        assert permission_calls == []

    # _action_lock_key
    assert engine._action_lock_key(action_name="a", user=1, session_key=None).startswith("user:1:action:")
    assert engine._action_lock_key(action_name="", user=1, session_key=None) == ""

    # binding action result for non-dict
    class _Disp1:
        async def dispatch(self, *_a, **_k):
            return 9

    out_bind = await engine.handle(
        {"request_id": "rb", "bindingAction": {"bindingId": "b1", "name": "n", "context": {}}},
        get_session=lambda u, r: {"_perm_cache_user": 7, "_perm_cache_ts": 1000.0, "_perm_cache_values": []},
        render=_render,
        dispatcher=_Disp1(),
        session_service=SimpleNamespace(),
    )
    assert out_bind[0]["bindingActionResult"]["ok"] is True

    # user action: busy lock
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(action_lock_manager=_Locks(acquire_result=False), modules=modules_runtime, logger=logger),
    )
    engine_busy = mod.RequestCycleEngine()
    out_busy = await engine_busy.handle(
        {"request_id": "ru1", "userAction": {"name": "demo.act", "context": {}}},
        get_session=lambda u, r: {"_perm_cache_user": 7, "_perm_cache_ts": 1000.0, "_perm_cache_values": []},
        render=_render,
        dispatcher=_Disp1(),
        session_service=SimpleNamespace(),
    )
    assert out_busy[0]["type"] == "action_busy"

    # user action: invalid + error + success execute path
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(action_lock_manager=_Locks(acquire_result=True), modules=modules_runtime, logger=logger),
    )
    engine_ok = mod.RequestCycleEngine()

    class _DispInvalid:
        async def dispatch(self, *_a, **_k):
            return "bad"

    out_invalid = await engine_ok.handle(
        {"request_id": "ru2", "userAction": {"name": "demo.act", "context": {}}},
        get_session=lambda u, r: {"_perm_cache_user": 7, "_perm_cache_ts": 1000.0, "_perm_cache_values": []},
        render=_render,
        dispatcher=_DispInvalid(),
        session_service=SimpleNamespace(),
    )
    assert out_invalid[0]["error"] == "invalid_action_response"

    class _DispErr:
        async def dispatch(self, *_a, **_k):
            return {"type": "error", "error": "boom"}

    out_err = await engine_ok.handle(
        {"request_id": "ru3", "userAction": {"name": "demo.act", "context": {}}},
        get_session=lambda u, r: {"_perm_cache_user": 7, "_perm_cache_ts": 1000.0, "_perm_cache_values": []},
        render=_render,
        dispatcher=_DispErr(),
        session_service=SimpleNamespace(),
    )
    assert out_err[0]["error"] == "boom"

    dispatched_contexts = []

    class _DispOk:
        async def dispatch(self, _name, action_ctx, *_a, **_k):
            dispatched_contexts.append(action_ctx)
            return {"value": {"ok": True}}

    monkeypatch.setattr(mod, "effects_from_action_result", lambda result, **_k: [UiMessagesEffect([{"ok": 1}])] if "effects" not in result else [])
    async def _execute_stub(**_k):
        return [{"done": True}]

    monkeypatch.setattr(engine_ok.effect_executor, "execute", _execute_stub)
    req.stream_id = "st"
    out_ok = await engine_ok.handle(
        {
            "request_id": "ru4",
            "userAction": {
                "name": "demo.act",
                "context": {
                    "x": 1,
                    "stream_id": "context-stream",
                    "_stream_id": "context-raw-stream",
                    "session_key": "context-session",
                },
                "surfaceId": "main",
                "sourceComponentId": "cmp",
            },
            "stream_id": "ignored",
        },
        get_session=lambda u, r: {"_perm_cache_user": 7, "_perm_cache_ts": 1000.0, "_perm_cache_values": []},
        render=_render,
        dispatcher=_DispOk(),
        session_service=SimpleNamespace(),
    )
    assert out_ok == [{"done": True}]
    assert dispatched_contexts[-1]["stream_id"] == "st"
    assert dispatched_contexts[-1]["session_key"] == "s1"
    assert "_stream_id" not in dispatched_contexts[-1]
    req.stream_id = None


@pytest.mark.asyncio
async def test_engine_remaining_branches_without_profiler(monkeypatch):
    mod = __import__("democrai.core.application.request_cycle.engine", fromlist=["dummy"])
    logger = _Logger()

    class _Locks:
        async def acquire(self, *_a, **_k):
            return True

        async def release(self, *_a, **_k):
            return True

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(action_lock_manager=_Locks(), modules=None, logger=logger),
    )
    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "current_request_profiler", lambda: None)
    monkeypatch.setattr(mod, "ensure_request_profile", lambda *_a, **_k: (_Profiler(), "tok", True))
    monkeypatch.setattr(mod, "stop_request_profile", lambda _tok: None)
    auth_service_mod = __import__(
        "democrai.core.application.auth.service",
        fromlist=["get_user_permissions"],
    )
    monkeypatch.setattr(auth_service_mod, "get_user_permissions", lambda _u: ["p"])

    req = RequestContext(
        request_id="rq-rem",
        user=7,
        role="user",
        organization_id=1,
        access_level=2,
        channel="ipc",
        session_key="s1",
    )
    monkeypatch.setattr(mod, "req_ctx", lambda: req)
    engine = mod.RequestCycleEngine()

    # _get_permissions session None branch
    assert engine._get_permissions(7, None) == ["p"]

    calls = []

    def _effects(result, **_kw):
        calls.append(result)
        return [UiMessagesEffect([{"ok": 1}])] if "message" in result else []

    monkeypatch.setattr(mod, "effects_from_action_result", _effects)
    monkeypatch.setattr(engine.effect_executor, "execute", lambda **_kw: asyncio.sleep(0, result=[{"ok": True}]))

    class _Disp:
        async def dispatch(self, *_a, **_k):
            return {"value": {"k": 1}}

    out = await engine._handle_user_action(
        msg={"request_id": "x", "userAction": {"name": "demo.act", "context": []}},
        session={},
        permissions=[],
        render=lambda _s, **_k: [],
        dispatcher=_Disp(),
        session_service=SimpleNamespace(),
        request_user=7,
        request_role="user",
        request_channel="ipc",
    )
    assert out == [{"ok": True}]
    assert calls and "message" in calls[-1]

    # _handle_binding_action branch with profiler None
    bind_out = await engine._handle_binding_action(
        msg={"request_id": "rb", "bindingAction": {"bindingId": "b1", "name": "n", "context": {}}},
        session={},
        permissions=[],
        dispatcher=_Disp(),
    )
    assert bind_out[0]["bindingActionResult"]["ok"] is True

    # fallback parse with span branch
    monkeypatch.setattr(mod, "current_request_profiler", lambda: _Profiler())
    await engine._handle_user_action(
        msg={"request_id": "x2", "userAction": {"name": "demo.act", "context": {}}},
        session={},
        permissions=[],
        render=lambda _s, **_k: [],
        dispatcher=_Disp(),
        session_service=SimpleNamespace(),
        request_user=7,
        request_role="user",
        request_channel="ipc",
    )
