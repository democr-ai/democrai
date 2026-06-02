from __future__ import annotations

import asyncio
import sys
import threading
from types import SimpleNamespace

import pytest


class _Logger:
    def __init__(self):
        self.errors = []
        self.debugs = []

    def error(self, msg, *args, **kwargs):
        self.errors.append(str(msg))

    def debug(self, msg, *args, **kwargs):
        self.debugs.append(str(msg))


@pytest.mark.asyncio
async def test_protocol_dispatcher_all_paths(monkeypatch):
    from democrai.core.infrastructure.network.protocol.dispatcher import ProtocolDispatcher

    logger = _Logger()
    monkeypatch.setattr(
        "democrai.core.infrastructure.network.protocol.dispatcher.app_ctx",
        lambda: SimpleNamespace(logger=logger),
    )

    disp = ProtocolDispatcher()
    calls = []

    async def _by_key(bus, cid, msg):
        calls.append(("key", cid, msg))

    async def _by_type(bus, cid, msg):
        calls.append(("type", cid, msg))

    async def _default(bus, cid, msg):
        calls.append(("default", cid, msg))

    async def _boom(*_a, **_k):
        raise RuntimeError("boom")

    disp.register("userAction", _by_key)
    await disp.dispatch("b", "c1", {"userAction": {}})
    assert calls and calls[-1][0] == "key"

    disp.register("ping", _by_type)
    await disp.dispatch("b", "c2", {"type": "ping"})
    assert calls[-1][0] == "type"

    disp.register("badKey", _boom)
    await disp.dispatch("b", "c3", {"badKey": True})
    assert logger.errors

    disp.register("badType", _boom)
    await disp.dispatch("b", "c4", {"type": "badType"})
    assert len(logger.errors) >= 2

    disp.set_default_handler(_default)
    await disp.dispatch("b", "c5", {"unknown": True})
    assert calls[-1][0] == "default"

    disp.set_default_handler(None)
    await disp.dispatch("b", "c6", {"none": 1})
    assert logger.debugs


@pytest.mark.asyncio
async def test_runtime_callbacks_paths(monkeypatch):
    from democrai.core.infrastructure.network.runtime import callbacks as mod

    logger = _Logger()
    network_mod = __import__(
        "democrai.core.infrastructure.network.runtime.network", fromlist=["dummy"]
    )
    monkeypatch.setattr(network_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    class _Bus:
        def __init__(self):
            self.on_message = None
            self.on_disconnect = None

    bus = _Bus()
    bus_no_attrs = object()
    network = SimpleNamespace(
        buses=[bus, bus_no_attrs],
        _on_bus_message=lambda b, c, m: ("msg", b, c, m),
        _on_bus_disconnect=lambda b, c: ("disc", b, c),
    )
    mod.configure_bus_callbacks(network)
    assert callable(bus.on_message) and callable(bus.on_disconnect)

    scheduled = []
    loop = SimpleNamespace(is_running=lambda: True)
    network = SimpleNamespace(
        _loop=loop,
        _process_message=lambda *_a: asyncio.sleep(0),
        _pending_network_messages=0,
        _pending_network_messages_lock=threading.Lock(),
        _ingress_dispatcher=None,
    )
    monkeypatch.setattr(
        mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: (scheduled.append(True), coro.close()),
    )
    mod.on_bus_message(network, "b", "c1", {"x": 1})
    assert scheduled

    network._loop = None
    mod.on_bus_message(network, "b", "c2", {"x": 2})
    assert logger.errors
    network._loop = SimpleNamespace(is_running=lambda: False)
    mod.on_bus_message(network, "b", "c3", {"x": 3})

    started = []
    finished = []
    traced = []

    class _Profiler:
        def __init__(self):
            self.timings = []
            self.fin = False

        def add_ms(self, name, value):
            self.timings.append((name, value))

        def add_metric(self, name, value):
            self.timings.append((name, value))

        def span(self, _name):
            class _Span:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return False

            return _Span()

        def finish(self):
            self.fin = True

    prof = _Profiler()
    monkeypatch.setattr(mod, "infer_request_kind", lambda msg: "kind")
    monkeypatch.setattr(mod, "start_request_flow", lambda *a, **k: started.append((a, k)))
    monkeypatch.setattr(mod, "finish_request_flow", lambda *a, **k: finished.append((a, k)))
    monkeypatch.setattr(mod, "trace_request_step", lambda *a, **k: traced.append((a, k)))
    monkeypatch.setattr(network_mod, "ensure_request_profile", lambda *_a, **_k: (prof, "tok", True))
    monkeypatch.setattr(network_mod, "stop_request_profile", lambda tok: finished.append((("stop", tok), {})))

    class _Dispatcher:
        async def dispatch(self, bus, cid, msg):
            from democrai.core.runtime.foundation.app import req_ctx

            assert req_ctx().request_id == msg["request_id"]
            msg["seen"] = True

    from democrai.core.runtime.foundation.app import RequestContext

    network = SimpleNamespace(
        dispatcher=_Dispatcher(),
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
    msg = {"type": "ping", "_ws_decode_ms": 1.2, "_ws_handoff_started_at": asyncio.get_running_loop().time()}
    await mod.process_message(network, "b", "c1", msg)
    assert "request_id" in msg and prof.fin and started and finished and traced

    # action with module prefix + non-owned profile branch
    prof2 = _Profiler()
    monkeypatch.setattr(network_mod, "ensure_request_profile", lambda *_a, **_k: (prof2, None, False))
    msg2 = {"userAction": {"name": "demo.action"}}
    await mod.process_message(network, "b", "c11", msg2)
    assert "request_id" in msg2
    # request_id present + owns_profile true with token None branch
    monkeypatch.setattr(network_mod, "ensure_request_profile", lambda *_a, **_k: (prof2, None, True))
    msg3 = {"request_id": "rid-1", "type": "ping"}
    await mod.process_message(network, "b", "c12", msg3)
    assert msg3["request_id"] == "rid-1"

    class _BoomDispatcher:
        async def dispatch(self, *_a, **_k):
            raise RuntimeError("dispatch-boom")

    network.dispatcher = _BoomDispatcher()
    with pytest.raises(RuntimeError):
        await mod.process_message(network, "b", "c2", {"type": "x"})

    registered = []
    defaulted = []
    network = SimpleNamespace(
        dispatcher=SimpleNamespace(
            register=lambda m, fn: registered.append((m, fn)),
            set_default_handler=lambda fn: defaulted.append(fn),
        ),
        _handle_action=lambda *_a: None,
        _handle_task_response=lambda *_a: None,
        _handle_task_cancel=lambda *_a: None,
        _handle_task_get=lambda *_a: None,
        _handle_client_query_result=lambda *_a: None,
        _handle_stream_piping=lambda *_a: None,
        _handle_legacy_launch=lambda *_a: None,
        _handle_media_resolve=lambda *_a: None,
        _handle_media_stream_open=lambda *_a: None,
        _handle_media_stream_close=lambda *_a: None,
        _handle_stream_binding_subscribe=lambda *_a: None,
        _handle_stream_binding_unsubscribe=lambda *_a: None,
    )
    mod.init_dispatcher(network)
    assert registered and defaulted


def test_targets_extra_branches(monkeypatch):
    from democrai.core.infrastructure.network import targets as mod

    assert mod._is_ip_literal("") is False
    assert mod._is_ip_literal("127.0.0.1") is True
    assert mod._is_ip_literal("[::1]") is True
    assert mod._is_ip_literal("example.com") is False

    assert mod._split_netloc("") == ("", None)
    assert mod._split_netloc("[::1]") == ("[::1]", None)
    assert mod._split_netloc("host") == ("host", None)

    assert mod._parse_endpoint_target("") == (None, "", None)
    assert mod._parse_endpoint_target("host:not-a-port") == (None, "host", None)

    assert mod._url_matches_pattern("https://a/b", "http://a/*") is False
    assert mod._url_matches_pattern("https://a/b", "https://a/*") is True

    assert mod._hosts_for_match("localhost")[0] == "localhost"
    assert "localhost" in mod._hosts_for_match("127.0.0.1")

    # DNS resolve + cache hit/evict path.
    monkeypatch.setattr(
        mod.socket,
        "getaddrinfo",
        lambda *_a, **_k: [
            (None, None, None, None, ("1.2.3.4", 0)),
            (None, None, None, None, ("::1", 0, 0, 0)),
        ],
    )
    with mod._RESOLVED_IPS_LOCK:
        mod._RESOLVED_IPS.clear()
    ips = mod._resolve_host_ips("example.org")
    assert "1.2.3.4" in ips
    assert mod._resolve_host_ips("example.org") == ips

    assert (
        mod._endpoint_pattern_matches(
            host="api.local", port=443, pattern="tcp://api.local:443", protocol="udp"
        )
        is False
    )
    assert (
        mod._endpoint_pattern_matches(
            host="1.2.3.4", port=443, pattern="example.org", protocol=None
        )
        is True
    )

    assert mod.is_network_target_allowed("", ["*"]) is False
    assert mod.is_network_target_allowed("redis://cache.local:6379", []) is False


@pytest.mark.asyncio
async def test_memory_stream_provider_additional_branches(monkeypatch):
    from democrai.core.infrastructure.network.providers.stream import memory as mod

    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    provider = mod.MemoryStreamProvider()
    q = provider.subscribe("room")
    provider.unsubscribe("missing", q)  # noop branch

    class _FakeLoop:
        def __init__(self):
            self.calls = []

        def is_running(self):
            return True

        def call_soon_threadsafe(self, fn, data):
            self.calls.append((fn, data))
            fn(data)

    fake_loop = _FakeLoop()
    q2 = asyncio.Queue()
    q2._loop = fake_loop  # exercise queue-loop branch
    provider._channels["room"] = {q2}
    await provider.broadcast("room", {"x": 1})
    assert fake_loop.calls and q2.get_nowait() == {"x": 1}

    class _BrokenLoop(_FakeLoop):
        def call_soon_threadsafe(self, fn, data):
            raise RuntimeError("broken")

    q3 = asyncio.Queue()
    q3._loop = _BrokenLoop()
    provider._channels["room"] = {q3}
    await provider.broadcast("room", {"y": 2})
    assert logger.errors


def test_runtime_network_init_and_notify(monkeypatch):
    mod = __import__("democrai.core.infrastructure.network.runtime.network", fromlist=["dummy"])

    configured = []
    inited = []
    notified = []

    monkeypatch.setattr(
        mod.runtime_callbacks,
        "configure_bus_callbacks",
        lambda net: configured.append(net),
    )
    monkeypatch.setattr(mod, "ProtocolDispatcher", lambda: "dispatcher")

    def _init_state(net):
        net._active_subscriptions = {}
        net._authenticated_clients = {}
        net._client_session_keys = {}
        net._session_external_approvals = {}
        net._stream_scopes = {}
        net._media_stream_tasks = {}
        net._client_media_streams = {}
        net._notification_queue = object()
        net.connection_registry = object()
        net.task_manager = object()
        net.core = object()

    monkeypatch.setattr(mod, "init_state", _init_state)
    monkeypatch.setattr(mod.Network, "_init_dispatcher", lambda self: inited.append(True))
    monkeypatch.setattr(
        mod.media_flow,
        "notify_external_access_approved",
        lambda *a, **k: notified.append((a, k)),
    )

    buses = [object()]
    streams = object()
    net = mod.Network(buses, streams)
    assert net.buses is buses and net.stream_manager is streams
    assert configured and inited and net.dispatcher == "dispatcher"

    net.notify_external_access_approved(
        subject_type="module",
        subject_name="demo",
        resource_type="network",
        operation="receive",
        target="https://x",
    )
    assert notified
