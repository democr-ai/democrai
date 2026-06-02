import asyncio
import threading
import zlib
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.network.codec import ws as ws_codec_mod
from democrai.core.infrastructure.network.protocol import auth as auth_mod
from democrai.core.infrastructure.network.protocol.dispatcher import ProtocolDispatcher
from democrai.core.infrastructure.network.runtime import callbacks as callbacks_mod
from democrai.core.infrastructure.network.runtime import network as runtime_network_mod
from democrai.core.infrastructure.network.runtime import state as state_mod
from democrai.core.runtime.foundation.app import RequestContext


def test_ws_codec_roundtrip_and_errors(monkeypatch):
    monkeypatch.setenv("DEMOCRAI_DEBUG_WS_RUNTIME", "1")
    diagnostics = ws_codec_mod.runtime_diagnostics()
    assert diagnostics["ws_codec_env"] == "1"

    assert ws_codec_mod.normalize_codec("deflate-json") == "deflate-json"
    assert ws_codec_mod.normalize_codec("unknown") == "json"

    kind, payload = ws_codec_mod.encode_message({"x": 1}, "json")
    assert kind == "text"
    assert ws_codec_mod.decode_message(text=payload, data=None, codec="json") == {"x": 1}

    kind2, payload2 = ws_codec_mod.encode_message({"x": 2}, "deflate-json")
    assert kind2 == "bytes"
    assert ws_codec_mod.decode_message(text=None, data=payload2, codec="deflate-json") == {"x": 2}

    plain_json_bytes = b'{"ok":true}'
    with pytest.raises(zlib.error):
        ws_codec_mod.decode_message(text=None, data=plain_json_bytes, codec="deflate-json")

    with pytest.raises(ValueError):
        ws_codec_mod.decode_message(text=None, data=None, codec="json")
    with pytest.raises(ValueError):
        ws_codec_mod.decode_message(text='["a"]', data=None, codec="json")


def test_protocol_auth_helpers(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.application.auth.jwt.decode_access_token_result",
        lambda _jwt: SimpleNamespace(
            payload={
                "user_id": "7",
                "organization_id": "8",
                "role": "admin",
                "access_level": 1,
            },
            error=None,
        ),
    )
    assert auth_mod.extract_auth({"jwt": "x"}) == (7, "admin", 8, 1)
    assert auth_mod.extract_auth({}) == (None, None, None, None)

    monkeypatch.setattr(
        "democrai.core.application.auth.jwt.decode_access_token_result",
        lambda _jwt: SimpleNamespace(payload=None, error="token_expired"),
    )
    expired = auth_mod.extract_auth_state({"jwt": "expired"})
    assert expired.user is None and expired.error == "token_expired"

    decode_calls = []
    monkeypatch.setattr(auth_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=True))
    monkeypatch.setattr(
        "democrai.core.application.auth.jwt.decode_access_token_result",
        lambda _jwt: decode_calls.append(_jwt),
    )
    setup_auth = auth_mod.extract_auth_state({"jwt": "stale"})
    assert setup_auth == auth_mod.ExtractedAuth()
    assert decode_calls == []

    network = SimpleNamespace(
        _client_session_keys={(1, "c1"): "sess"},
        _authenticated_clients={(1, "c2"): (9, "role")},
    )
    bus = object()
    assert auth_mod.session_scope_key(network, bus, "c3").startswith("client:")
    network._client_session_keys[(id(bus), "c1")] = "sess"
    network._authenticated_clients[(id(bus), "c2")] = (9, "role")
    assert auth_mod.session_scope_key(network, bus, "c1") == "session:sess"
    assert auth_mod.session_scope_key(network, bus, "c2") == "user:9"

    sent = []
    fake_bus = SimpleNamespace(send=lambda cid, msg: sent.append((cid, msg)))
    auth_mod.push_notifications_update(fake_bus, "u1", count=3)
    auth_mod.push_external_access_approved(fake_bus, "u1", module_name="m", target="t")
    assert sent[0][1]["type"] == "notifications_update"
    assert sent[1][1]["type"] == "external_access_approved"


@pytest.mark.asyncio
async def test_protocol_dispatcher_paths():
    logs = []
    dispatcher = ProtocolDispatcher()
    dispatcher.logger = SimpleNamespace(debug=lambda *a, **k: logs.append(("debug", a)), error=lambda *a, **k: logs.append(("error", a)))
    called = []

    async def _ok(_bus, _cid, _msg):
        called.append("ok")

    async def _boom(_bus, _cid, _msg):
        raise RuntimeError("boom")

    async def _default(_bus, _cid, _msg):
        called.append("default")

    dispatcher.register("userAction", _ok)
    await dispatcher.dispatch(object(), "c1", {"userAction": {}})
    assert called == ["ok"]

    dispatcher.register("bindingAction", _boom)
    await dispatcher.dispatch(object(), "c1", {"bindingAction": {}})
    assert any(item[0] == "error" for item in logs)

    dispatcher.set_default_handler(_default)
    await dispatcher.dispatch(object(), "c1", {"type": "unknown"})
    assert called[-1] == "default"


def test_runtime_state_init(monkeypatch):
    monkeypatch.setattr(state_mod, "ConnectionRegistry", lambda: "cr")
    monkeypatch.setattr(runtime_network_mod, "Core", lambda: "core")
    monkeypatch.setattr(runtime_network_mod, "TaskManager", lambda: "tm")
    monkeypatch.setattr(runtime_network_mod, "NotificationQueue", lambda: "nq")
    fake_ctx = SimpleNamespace()
    monkeypatch.setattr(runtime_network_mod, "app_ctx", lambda: fake_ctx)

    network = SimpleNamespace()
    state_mod.init_state(network)

    assert network.core == "core"
    assert network.connection_registry == "cr"
    assert network.task_manager == "tm"
    assert network._notification_queue == "nq"
    assert network._active_subscriptions == {}
    assert fake_ctx.connection_registry == "cr"
    assert fake_ctx.task_manager == "tm"


def test_callbacks_configure_and_on_bus_message(monkeypatch):
    bus = SimpleNamespace(on_message=None, on_disconnect=None)
    calls = []
    network = SimpleNamespace(
        buses=[bus],
        _on_bus_message=lambda b, cid, msg: calls.append(("msg", b, cid, msg)),
        _on_bus_disconnect=lambda b, cid: calls.append(("disc", b, cid)),
        _loop=None,
        _process_message=None,
    )
    callbacks_mod.configure_bus_callbacks(network)
    bus.on_message("c1", {"a": 1})
    bus.on_disconnect("c1")
    assert calls and calls[0][0] == "msg"

    errs = []
    monkeypatch.setattr(
        runtime_network_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(error=lambda *a, **k: errs.append(a))),
    )
    callbacks_mod.on_bus_message(network, bus, "c1", {"a": 1})
    assert errs


@pytest.mark.asyncio
async def test_callbacks_process_message_and_dispatch_init(monkeypatch):
    steps = []
    monkeypatch.setattr(callbacks_mod, "start_request_flow", lambda *a, **k: steps.append("start"))
    monkeypatch.setattr(callbacks_mod, "finish_request_flow", lambda *a, **k: steps.append("finish"))
    monkeypatch.setattr(callbacks_mod, "trace_request_step", lambda *a, **k: steps.append("trace"))
    monkeypatch.setattr(callbacks_mod, "infer_request_kind", lambda _msg: "action")
    monkeypatch.setattr(callbacks_mod, "uuid", SimpleNamespace(uuid4=lambda: "req-1"))

    class _Profiler:
        def add_ms(self, *_a, **_k):
            return None

        def add_metric(self, *_a, **_k):
            return None

        def span(self, *_a, **_k):
            class _Ctx:
                def __enter__(self_inner):
                    return None

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Ctx()

        def finish(self):
            steps.append("prof_finish")

    monkeypatch.setattr(
        runtime_network_mod,
        "ensure_request_profile",
        lambda *_a, **_k: (_Profiler(), "tok", True),
    )
    monkeypatch.setattr(
        runtime_network_mod,
        "stop_request_profile",
        lambda _tok: steps.append("stop_profile"),
    )

    async def _dispatch(_bus, _cid, _msg):
        from democrai.core.runtime.foundation.app import req_ctx

        assert req_ctx().request_id == "req-1"
        steps.append("dispatch")

    network = SimpleNamespace(
        dispatcher=SimpleNamespace(dispatch=_dispatch),
        _pending_network_messages=1,
        _pending_network_messages_lock=threading.Lock(),
        _build_context=lambda _bus, _cid, msg: RequestContext(
            app=None,
            request_id=msg["request_id"],
            user=None,
            role=None,
            organization_id=None,
            access_level=None,
            channel="bus",
        ),
    )
    msg = {"type": "x"}
    await callbacks_mod.process_message(network, object(), "c1", msg)
    assert msg["request_id"] == "req-1"
    assert "dispatch" in steps and "finish" in steps and "stop_profile" in steps

    regs = []
    class _Disp:
        def register(self, k, v):
            regs.append((k, v))
        def set_default_handler(self, h):
            regs.append(("default", h))

    n2 = SimpleNamespace(
        dispatcher=_Disp(),
        _handle_action=lambda *_a: None,
        _handle_task_response=lambda *_a: None,
        _handle_task_cancel=lambda *_a: None,
        _handle_task_get=lambda *_a: None,
        _handle_client_query_result=lambda *_a: None,
        _handle_stream_piping=lambda *_a: None,
        _handle_media_resolve=lambda *_a: None,
        _handle_media_stream_open=lambda *_a: None,
        _handle_media_stream_close=lambda *_a: None,
        _handle_stream_binding_subscribe=lambda *_a: None,
        _handle_stream_binding_unsubscribe=lambda *_a: None,
        _handle_legacy_launch=lambda *_a: None,
    )
    callbacks_mod.init_dispatcher(n2)
    assert any(item[0] == "default" for item in regs)


@pytest.mark.asyncio
async def test_callbacks_process_message_expired_token_redirects_guest(monkeypatch):
    steps = []
    monkeypatch.setattr(callbacks_mod, "start_request_flow", lambda *a, **k: steps.append("start"))
    monkeypatch.setattr(callbacks_mod, "finish_request_flow", lambda *a, **k: steps.append("finish"))
    monkeypatch.setattr(callbacks_mod, "trace_request_step", lambda *a, **k: steps.append("trace"))
    monkeypatch.setattr(callbacks_mod, "infer_request_kind", lambda _msg: "action")
    monkeypatch.setattr(callbacks_mod, "uuid", SimpleNamespace(uuid4=lambda: "req-1"))
    monkeypatch.setattr(
        "democrai.core.application.home.resolve_guest_page_path",
        lambda: "/auth/login",
    )
    monkeypatch.setattr(
        "democrai.core.application.routing.router_resolution.is_public_path",
        lambda path: path == "/auth/login",
    )

    class _Profiler:
        def add_ms(self, *_a, **_k):
            return None

        def add_metric(self, *_a, **_k):
            return None

        def span(self, *_a, **_k):
            class _Ctx:
                def __enter__(self_inner):
                    return None

                def __exit__(self_inner, exc_type, exc, tb):
                    return False

            return _Ctx()

        def finish(self):
            steps.append("prof_finish")

    monkeypatch.setattr(
        runtime_network_mod,
        "ensure_request_profile",
        lambda *_a, **_k: (_Profiler(), None, True),
    )

    sent = []
    cleaned = []
    dispatched = []
    bus = SimpleNamespace(send=lambda cid, payload: sent.append((cid, payload)))

    async def _cleanup(_bus, _cid):
        cleaned.append((_bus, _cid))

    async def _render(session, force_shell=False):
        sent_sessions.append((dict(session), force_shell))
        return [{"beginRendering": {"root": "root", "surfaceId": "main"}}]

    def _build_context(_bus, _cid, msg):
        ctx = RequestContext(
            app=None,
            request_id=msg["request_id"],
            user=None,
            role=None,
            organization_id=None,
            access_level=None,
            channel="bus",
            session_key="sess-expired",
        )
        ctx.auth_error = "token_expired"
        return ctx

    sent_sessions = []
    network = SimpleNamespace(
        core=SimpleNamespace(
            get_session=lambda *_a, **_k: {},
            render=_render,
        ),
        dispatcher=SimpleNamespace(dispatch=lambda *_a: dispatched.append(True)),
        _pending_network_messages=1,
        _pending_network_messages_lock=threading.Lock(),
        _build_context=_build_context,
        _cleanup_client=_cleanup,
    )

    await callbacks_mod.process_message(network, bus, "c1", {"jwt": "expired"})

    assert not dispatched
    assert cleaned == [(bus, "c1")]
    assert sent[0][1]["jwt"] == ""
    assert sent[0][1]["current_path"] == "/auth/login"
    assert sent[0][1]["eventNotification"]["variant"] == "warning"
    assert sent[1][1]["beginRendering"]["surfaceId"] == "main"
    assert sent[1][1]["request_id"] == sent[0][1]["request_id"]
    assert sent_sessions[0][0]["current_path"] == "/auth/login"
    assert sent_sessions[0][1] is True
    assert "finish" in steps

    sent.clear()
    cleaned.clear()
    await callbacks_mod.process_message(
        network,
        bus,
        "c1",
        {"jwt": "expired", "current_path": "/auth/login"},
    )

    assert cleaned == [(bus, "c1")]
    assert sent[0][1]["jwt"] == ""
    assert "current_path" not in sent[0][1]
