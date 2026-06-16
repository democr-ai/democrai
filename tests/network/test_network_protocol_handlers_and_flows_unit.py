from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from democrai.core.runtime.foundation.app import RequestContext, reset_req_ctx, set_req_ctx


class _Logger:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []
        self.debugs = []

    def error(self, msg, *args, **kwargs):
        self.errors.append(str(msg))

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(str(msg))

    def info(self, msg, *args, **kwargs):
        self.infos.append(str(msg))

    def debug(self, msg, *args, **kwargs):
        self.debugs.append(str(msg))


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Profiler:
    def span(self, _name):
        return _Span()


@contextmanager
def _request_context(*, user=1, organization_id=2, session_key="sess", request_id="r"):
    token = set_req_ctx(
        RequestContext(
            app=None,
            request_id=request_id,
            user=user,
            role="User" if user is not None else None,
            organization_id=organization_id,
            access_level=None,
            channel="bus",
            session_key=session_key,
        )
    )
    try:
        yield
    finally:
        reset_req_ctx(token)


@pytest.mark.asyncio
async def test_request_launch_paths(monkeypatch):
    from democrai.core.infrastructure.network.flows import request_launch as mod

    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(mod, "ensure_request_profile", lambda *_a, **_k: (_Profiler(), None, None))
    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "_debug_auth_flow", lambda *_a, **_k: None)

    sent = []

    class _Bus:
        def send(self, client_id, message):
            sent.append((client_id, message))

    cleaned = []

    async def _cleanup_client(bus, client_id):
        cleaned.append((bus, client_id))

    responses = [
        {
            "type": "ok",
            "jwt": "",
            "propertyUpdate": {
                "componentId": "image_demo_live",
                "propertyName": "src",
                "action": "set",
                "value": "x",
            },
        }
    ]
    async def _handle_ok(*_a, **_k):
        return responses

    network = SimpleNamespace(
        core=SimpleNamespace(handle=_handle_ok),
        _cleanup_client=_cleanup_client,
    )
    ctx = SimpleNamespace(
        request_id="r1",
        action_name="act",
        user=1,
        organization_id=2,
    )
    await mod.launch_request(network, _Bus(), "c1", {"type": "action"}, ctx)
    assert sent and sent[0][1]["request_id"] == "r1"
    assert cleaned

    sent.clear()
    async def _handle_empty(*_a, **_k):
        return []

    network.core = SimpleNamespace(handle=_handle_empty)
    await mod.launch_request(network, _Bus(), "c2", {"type": "action"}, ctx)
    assert sent[-1][1]["type"] == "request_ack"

    async def _boom(*_a, **_k):
        raise RuntimeError("boom")

    sent.clear()
    network.core = SimpleNamespace(handle=_boom)
    await mod.launch_request(network, _Bus(), "c3", {"type": "action"}, ctx)
    assert sent and sent[0][1]["type"] == "error" and logger.errors

    assert mod.response_clears_auth(None) is False
    assert mod.response_clears_auth([{"jwt": ""}]) is True
    assert mod.response_clears_auth([{"jwt": "x"}]) is False
    assert mod.response_clears_auth([1, "x"]) is False


@pytest.mark.asyncio
async def test_stream_flows_paths(monkeypatch):
    from democrai.core.infrastructure.network.flows import streams as mod

    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    q = asyncio.Queue()
    unsubscribed = []
    broadcasts = []

    class _StreamManager:
        def subscribe(self, stream_id):
            return q

        def unsubscribe(self, stream_id, queue):
            unsubscribed.append((stream_id, queue))

        async def broadcast(self, stream_id, payload):
            broadcasts.append((stream_id, payload))

    sent = []
    bus = SimpleNamespace(send=lambda cid, msg: sent.append((cid, msg)))
    network = SimpleNamespace(
        _active_subscriptions={},
        stream_manager=_StreamManager(),
        _media_stream_tasks={},
        _client_media_streams={},
        _stream_owners={},
    )

    mod.ensure_stream_piped(network, bus, "c1", "s1")
    # already subscribed branch
    mod.ensure_stream_piped(network, bus, "c1", "s1")
    await q.put({"type": "m1"})
    await asyncio.sleep(0)
    assert sent and sent[0][1]["type"] == "m1"
    # Explicit cancellation to exercise cleanup pop path in finally.
    t = network._active_subscriptions[(id(bus), "c1")]["s1"]
    t.cancel()
    await asyncio.sleep(0)

    mod.ensure_stream_piped(network, bus, "c1", "s1")
    assert len(network._active_subscriptions[(id(bus), "c1")]) == 1

    class _Upstream:
        def __init__(self, chunks, fail=False):
            self._chunks = chunks
            self._fail = fail

        async def aiter_bytes(self):
            if self._fail:
                raise RuntimeError("upstream-fail")
            for c in self._chunks:
                yield c

        async def aclose(self):
            return None

    class _Client:
        async def aclose(self):
            return None

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.handler.services.media",
        SimpleNamespace(encode_media_stream_chunk=lambda b: f"enc:{b.decode()}"),
    )
    network._media_stream_tasks["ms1"] = object()
    await mod.pipe_media_stream(network, "ms1", client=_Client(), upstream=_Upstream([b"a", b"", b"b"]))
    assert any(item[1]["type"] == "media_stream_end" for item in broadcasts)
    assert "ms1" not in network._media_stream_tasks

    broadcasts.clear()
    await mod.pipe_media_stream(network, "ms2", client=_Client(), upstream=_Upstream([], fail=True))
    assert any(item[1]["type"] == "media_stream_error" for item in broadcasts)

    class _CancelUpstream(_Upstream):
        async def aiter_bytes(self):
            raise asyncio.CancelledError()
            yield b""

    with pytest.raises(asyncio.CancelledError):
        await mod.pipe_media_stream(network, "ms3", client=_Client(), upstream=_CancelUpstream([]))

    async def _never():
        await asyncio.sleep(10)

    key = (id(bus), "c1")
    media_task = asyncio.create_task(_never())
    pipe_task = asyncio.create_task(_never())
    network._media_stream_tasks = {"stream-close": media_task}
    network._client_media_streams = {key: {"stream-close"}}
    network._active_subscriptions = {key: {"stream-close": pipe_task}}
    network._stream_owners = {"stream-close": key}
    await mod.close_media_stream(network, bus, "c1", "stream-close")
    assert "stream-close" not in network._stream_owners
    assert key not in network._active_subscriptions

    cleanup_calls = []

    async def _close_media_stream(bus_obj, cid, sid):
        cleanup_calls.append((bus_obj, cid, sid))

    live_task = asyncio.create_task(_never())
    network._active_subscriptions = {key: {"s2": live_task}}
    network._client_media_streams = {key: {"m2"}}
    network._stream_bindings = {}
    network._stream_binding_specs = {}
    network._close_media_stream = _close_media_stream
    network._session_scope_key = lambda _b, _c: "client:k1"
    network._session_external_approvals = {"client:k1": {"x"}, "user:1:2": {"y"}}
    network._client_session_keys = {key: "sess"}
    network._client_ips = {key: "203.0.113.10"}
    network._default_stream_id = lambda cid: f"stream_{cid}"
    network._stream_owners = {"stream_c1": key}
    network._authenticated_clients = {key: (1, "User", None, None)}
    await mod.cleanup_client(network, bus, "c1")
    assert cleanup_calls == [(bus, "c1", "m2")]
    assert key not in network._client_ips
    assert "client:k1" not in network._session_external_approvals
    assert "user:1:2" in network._session_external_approvals

    scheduled = []
    registry = SimpleNamespace(unregister=lambda *_a: 1)
    network.connection_registry = registry
    network._loop = SimpleNamespace(is_running=lambda: True)
    network._cleanup_client = lambda *_a: _close_media_stream(*_a, "x")
    monkeypatch.setattr(
        mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: (scheduled.append(True), coro.close()),
    )
    mod.on_bus_disconnect(network, bus, "c1")
    assert scheduled

    # Pipe error branch + key removed before finally pop.
    class _BadBus:
        def send(self, *_a, **_k):
            raise RuntimeError("send-boom")

    q2 = asyncio.Queue()
    network2 = SimpleNamespace(
        _active_subscriptions={},
        stream_manager=SimpleNamespace(
            subscribe=lambda _s: q2,
            unsubscribe=lambda _s, _q: network2._active_subscriptions.pop((id(bad_bus), "c9"), None),
        ),
    )
    bad_bus = _BadBus()
    mod.ensure_stream_piped(network2, bad_bus, "c9", "s9")
    await q2.put({"x": 1})
    await asyncio.sleep(0)
    assert logger.errors


@pytest.mark.asyncio
async def test_protocol_handlers_core_paths(monkeypatch):
    from democrai.core.infrastructure.network.protocol import handlers as mod

    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "generate_session_key", lambda: "sess-generated")

    sent = []
    bus = SimpleNamespace(send=lambda cid, payload: sent.append((cid, payload)))
    mod.send_auth_error(None, bus, "c1", {"request_id": "r"}, "x")
    mod.send_invalid_media_request(None, bus, "c1", {"request_id": "r2"})
    assert sent[0][1]["error"] == "x"
    assert sent[1][1]["error"] == "invalid_media_request"

    guest_ctx = SimpleNamespace(user=None)
    auth_ctx = SimpleNamespace(user=1)
    assert mod.is_action_allowed_for_context({}, guest_ctx) is False
    assert mod.is_action_allowed_for_context({"userAction": {}}, guest_ctx) is True
    assert mod.is_action_allowed_for_context({}, auth_ctx) is True

    network = SimpleNamespace(_GUEST_ALLOWED_MESSAGE_TYPES={"init", "ping"})
    assert mod.is_legacy_message_allowed_for_context(network, {"type": "init"}, guest_ctx) is True
    assert mod.is_legacy_message_allowed_for_context(network, {"type": "x"}, guest_ctx) is False
    assert mod.is_legacy_message_allowed_for_context(network, {}, guest_ctx) is False

    assert mod.default_stream_id("c1") == "stream_c1"

    network = SimpleNamespace(
        _stream_owners={},
        _authenticated_clients={},
        _client_session_keys={},
        connection_registry=SimpleNamespace(
            is_online=lambda *_a: False,
            register=lambda *_a, **_k: None,
        ),
        _notification_queue=SimpleNamespace(flush=lambda *_a, **_k: None),
    )
    mod.bind_stream_to_owner(network, "s1", bus=bus, client_id="c1")
    assert mod.stream_owner_matches(network, "s1", bus=bus, client_id="c1") is True
    mod.register_authenticated_client(network, bus, "c1", user=1, role="Admin", organization_id=2, access_level=1)
    mod.register_client_session_key(network, bus, "c1", "sk")

    pushed = []
    monkeypatch.setattr(
        mod,
        "_push_initial_notifications_to_super_users",
        lambda *_a, **_k: pushed.append(True),
    )
    network._extract_auth = lambda _msg: (1, "Super", 2, 1)
    network.register_authenticated_client = lambda *a, **k: mod.register_authenticated_client(network, *a, **k)
    mod.register_client_ip(network, bus, "c2", "203.0.113.10")
    ctx = mod.build_context(network, bus, "c2", {"request_id": "r1", "userAction": {"name": "a"}})
    assert ctx.user == 1 and ctx.client_ip == "203.0.113.10" and pushed

    # Cached connection auth must not authenticate a request without JWT.
    network._extract_auth = lambda _msg: (None, None, None, None)
    network._authenticated_clients[(id(bus), "c3")] = (7, "User", None, None)
    ctx2 = mod.build_context(network, bus, "c3", {"request_id": "r2"})
    assert ctx2.user is None and ctx2.session_key == "sess-generated"
    ctx3 = mod.build_context(network, bus, "c3", {"request_id": "r3", "session_key": "attacker"})
    assert ctx3.session_key == "sess-generated"
    ctx4 = mod.build_context(network, bus, "c4", {"request_id": "r4", "session_key": "attacker"})
    assert ctx4.session_key == "sess-generated"
    network._extract_auth = lambda _msg: SimpleNamespace(
        user=None,
        role=None,
        organization_id=None,
        access_level=None,
        error="token_expired",
    )
    ctx_expired = mod.build_context(network, bus, "c5", {"request_id": "r-expired"})
    assert getattr(ctx_expired, "auth_error") == "token_expired"

    auth_errors = []
    ensured = []
    network._send_auth_error = lambda _b, _c, _m, err: auth_errors.append(err)
    network._default_stream_id = lambda cid: f"stream_{cid}"
    network._bind_stream_to_owner = lambda sid, **kw: network._stream_owners.__setitem__(sid, (id(kw["bus"]), kw["client_id"]))
    network._ensure_stream_piped = lambda _b, _c, sid: ensured.append(sid)
    network._stream_owner_matches = lambda sid, **kw: sid == "allowed"
    ctx_guest = SimpleNamespace(user=None, organization_id=None)
    msg = {}
    assert mod.authorize_and_bind_stream(network, bus, "c1", msg, ctx_guest, reject_on_unauthenticated=False) == "stream_c1"
    assert mod.authorize_and_bind_stream(network, bus, "c1", {"stream_id": "x"}, ctx_guest, reject_on_unauthenticated=False) is None
    ctx_user = SimpleNamespace(user=1, organization_id=2)
    msg2 = {}
    assert mod.authorize_and_bind_stream(network, bus, "c1", msg2, ctx_user, reject_on_unauthenticated=True) == "stream_c1"
    assert ensured and msg2["stream_id"] == "stream_c1"
    assert mod.authorize_and_bind_stream(network, bus, "c1", {"stream_id": "   "}, ctx_user, reject_on_unauthenticated=True) is None
    assert mod.authorize_and_bind_stream(network, bus, "c1", {"stream_id": "u1"}, ctx_user, reject_on_unauthenticated=True) is None
    network._stream_owners["allowed"] = (id(bus), "c1")
    assert mod.authorize_and_bind_stream(network, bus, "c1", {"stream_id": "allowed"}, ctx_user, reject_on_unauthenticated=True) == "allowed"
    network._stream_owner_matches = lambda sid, **kw: False
    assert mod.authorize_and_bind_stream(network, bus, "c1", {"stream_id": "allowed"}, ctx_user, reject_on_unauthenticated=True) is None
    assert auth_errors

    launches = []

    async def _launch_request(_b, _c, _m, _ctx):
        launches.append(True)

    network._is_action_allowed_for_context = lambda *_a: False
    network._send_auth_error = lambda *_a: auth_errors.append("auth")
    network._authorize_and_bind_stream = lambda *_a, **_k: "s1"
    network._launch_request = _launch_request
    with _request_context():
        await mod.handle_action(network, bus, "c1", {})
    assert "auth" in auth_errors

    network._is_action_allowed_for_context = lambda *_a: True
    network._authorize_and_bind_stream = lambda *_a, **_k: None
    with _request_context():
        await mod.handle_action(network, bus, "c1", {"stream_id": "x"})
    assert not launches

    network._authorize_and_bind_stream = lambda *_a, **_k: "sid"
    with _request_context():
        await mod.handle_action(network, bus, "c1", {})
    assert launches

    # task response/cancel/get basic branches
    task = SimpleNamespace(user_id=1, organization_id=2, status="completed", id="t1", label="L", result=json.dumps({"ok": 1}), error=None, progress=10, checkpoint=False, updated_at=123)
    task_manager = SimpleNamespace(
        get_task=lambda tid: task if tid == "t1" else None,
        respond_confirmation=lambda *_a: asyncio.sleep(0),
        cancel=lambda *_a: asyncio.sleep(0),
    )
    network.task_manager = task_manager
    with _request_context():
        await mod.handle_task_response(network, bus, "c1", {"backgroundTaskResponse": {"taskId": "t1", "response": {}}})
        await mod.handle_task_cancel(network, bus, "c1", {"backgroundTaskCancel": {"taskId": "t1"}})

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.utils.timezone",
        SimpleNamespace(format_app_datetime=lambda *_a: "label", serialize_app_datetime=lambda *_a: "ts"),
    )
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert any("backgroundTaskCompleted" in payload for _, payload in sent)

    task.status = "failed"
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert any("backgroundTaskError" in payload for _, payload in sent)

    task.status = "running"
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert any("backgroundTaskProgress" in payload for _, payload in sent)

    with _request_context(user=None, organization_id=None, session_key=None):
        await mod.handle_task_response(network, bus, "c1", {"backgroundTaskResponse": {"taskId": "t1", "response": {}}})
        await mod.handle_task_cancel(network, bus, "c1", {"backgroundTaskCancel": {"taskId": "t1"}})
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert logger.warnings

    piped = []
    network._authorize_and_bind_stream = lambda *_a, **_k: piped.append(True)
    with _request_context():
        await mod.handle_stream_piping(network, bus, "c1", {})
    assert piped


@pytest.mark.asyncio
async def test_protocol_handlers_additional_branches(monkeypatch):
    from democrai.core.infrastructure.network.protocol import handlers as mod

    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(mod, "trace_request_step", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "generate_session_key", lambda: "generated")

    sent = []
    bus = SimpleNamespace(send=lambda cid, payload: sent.append((cid, payload)))

    # Build context branches: existing session key + non-new connection + flush callback path.
    flushed = []
    network = SimpleNamespace(
        _stream_scopes={},
        _authenticated_clients={},
        _client_session_keys={(id(bus), "c1"): "existing"},
        connection_registry=SimpleNamespace(
            is_online=lambda *_a: True,
            register=lambda *_a, **_k: None,
        ),
        _notification_queue=SimpleNamespace(
            flush=lambda _u, send_fn, _o: (flushed.append(True), send_fn({"type": "notif"}))
        ),
        _extract_auth=lambda _m: (1, "Super", None, 1),
    )
    network.register_authenticated_client = lambda *a, **k: mod.register_authenticated_client(network, *a, **k)
    ctx = mod.build_context(network, bus, "c1", {"request_id": "r1"})
    assert ctx.session_key == "existing"
    assert flushed and sent[-1][1]["type"] == "notif"

    # register_client_session_key no-op branch
    mod.register_client_session_key(network, bus, "c2", "")
    assert (id(bus), "c2") not in network._client_session_keys
    assert mod.is_legacy_message_allowed_for_context(SimpleNamespace(_GUEST_ALLOWED_MESSAGE_TYPES={"x"}), {}, SimpleNamespace(user=1)) is True

    # Ownership-denied response/cancel branches.
    network.task_manager = SimpleNamespace(
        get_task=lambda _tid: SimpleNamespace(user_id=999, organization_id=2),
        respond_confirmation=lambda *_a: asyncio.sleep(0),
        cancel=lambda *_a: asyncio.sleep(0),
    )
    with _request_context():
        await mod.handle_task_response(network, bus, "c1", {"backgroundTaskResponse": {"taskId": "t-deny", "response": {}}})
        await mod.handle_task_cancel(network, bus, "c1", {"backgroundTaskCancel": {"taskId": "t-deny"}})
    assert logger.warnings

    # Missing task id branch.
    logger.warnings.clear()
    network.task_manager = SimpleNamespace(
        get_task=lambda _tid: None,
        respond_confirmation=lambda *_a: asyncio.sleep(0),
        cancel=lambda *_a: asyncio.sleep(0),
    )
    with _request_context():
        await mod.handle_task_response(network, bus, "c1", {"backgroundTaskResponse": {"response": {}}})
        await mod.handle_task_cancel(network, bus, "c1", {"backgroundTaskCancel": {}})
    assert not logger.warnings

    # handle_task_get DB fallback: query error then empty return.
    class _Db:
        def __init__(self, fail=True, task=None):
            self.fail = fail
            self.task = task
            self.closed = False

        def query(self, _model):
            if self.fail:
                raise RuntimeError("db-fail")
            return SimpleNamespace(filter=lambda *_a, **_k: SimpleNamespace(first=lambda: self.task))

        def close(self):
            self.closed = True

    db1 = _Db(fail=True, task=None)
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.tasks.models",
        SimpleNamespace(BackgroundTaskRecord=SimpleNamespace(id="id-col")),
    )
    network.task_manager = SimpleNamespace(get_task=lambda _tid: None, _get_db=lambda: db1)
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert db1.closed is True

    # DB fallback task found but org mismatch and non-json result branch.
    task = SimpleNamespace(
        user_id=1,
        organization_id=99,
        status="completed",
        id="t1",
        label="L",
        result="not-json",
        error=None,
        progress=1,
        checkpoint=False,
        updated_at=1,
    )
    db2 = _Db(fail=False, task=task)
    network.task_manager = SimpleNamespace(get_task=lambda _tid: None, _get_db=lambda: db2)
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.platform.utils.timezone",
        SimpleNamespace(format_app_datetime=lambda *_a: "lbl", serialize_app_datetime=lambda *_a: "ts"),
    )
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert not sent or all("backgroundTaskCompleted" not in payload for _, payload in sent[-1:])

    task.organization_id = 2
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
    assert any("backgroundTaskCompleted" in payload for _, payload in sent)
    task.user_id = 999
    with _request_context():
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {"taskId": "t1"}})
        await mod.handle_task_get(network, bus, "c1", {"backgroundTaskGet": {}})

    # _push_initial_notifications_if_super helper branches.
    pushed = []
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.auth.roles",
        SimpleNamespace(is_super_role=lambda role: role == "Super"),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.database.access_policy",
        SimpleNamespace(get_pending_access_requests=lambda: [{}] * 11),
    )
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.network.protocol.auth",
        SimpleNamespace(push_notifications_update=lambda _b, _c, count=0: pushed.append(count)),
    )
    mod._push_initial_notifications_if_super(network, bus, "c1", role="User", organization_id=None)
    mod._push_initial_notifications_if_super(network, bus, "c1", role="Super", organization_id=1)
    assert not pushed
    mod._push_initial_notifications_if_super(network, bus, "c1", role="Super", organization_id=None)
    assert pushed == [11]
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.network.protocol.auth",
        SimpleNamespace(push_notifications_update=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x"))),
    )
    mod._push_initial_notifications_if_super(network, bus, "c1", role="Super", organization_id=None)
