from __future__ import annotations

import asyncio
import importlib
import json
import sys
from types import SimpleNamespace

import pytest


class _Logger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, msg, *args, **kwargs):
        self.infos.append(str(msg))

    def error(self, msg, *args, **kwargs):
        self.errors.append(str(msg))


class _Config:
    def __init__(self, values: dict[str, object] | None = None):
        self.values = values or {}

    def get(self, key: str, default=None):
        return self.values.get(key, default)


def _install_fake_redis_module(monkeypatch, *, from_url):
    fake_asyncio_mod = SimpleNamespace(from_url=from_url, Redis=object)
    monkeypatch.setitem(sys.modules, "redis", SimpleNamespace(asyncio=fake_asyncio_mod))
    monkeypatch.setitem(sys.modules, "redis.asyncio", fake_asyncio_mod)


def test_connection_registry_roundtrip():
    from democrai.core.infrastructure.network.registry.connection_registry import (
        ConnectionRegistry,
        _scope_key,
    )

    assert _scope_key(10, None) == (10, None)
    assert _scope_key(10, 20) == (10, 20)

    registry = ConnectionRegistry()
    bus_a = object()
    bus_b = object()

    registry.register(1, bus_a, "c1")
    assert registry.is_online(1)
    assert registry.get_user_for_client(bus_a, "c1") == 1
    assert registry.get_scope_for_client(bus_a, "c1") == (1, None)

    # Re-register same client in another scoped identity: old mapping is removed.
    registry.register(2, bus_a, "c1", organization_id=7)
    assert not registry.is_online(1)
    assert registry.is_online(2, 7)
    assert registry.get_scope_for_client(bus_a, "c1") == (2, 7)

    registry.register(2, bus_b, "c2", organization_id=7)
    conns = registry.get_connections(2, 7)
    assert len(conns) == 2

    assert registry.unregister(bus_a, "missing") is None
    assert registry.unregister(bus_a, "c1") == 2
    assert registry.get_user_for_client(bus_a, "c1") is None
    assert registry.unregister(bus_b, "c2") == 2
    assert not registry.is_online(2, 7)


def test_http_websocket_helpers():
    from democrai.core.infrastructure.network.http.websocket import (
        is_local_websocket,
        is_secure_websocket,
    )

    ws_local = SimpleNamespace(
        url=SimpleNamespace(hostname="localhost", scheme="ws"), headers={}
    )
    ws_ip = SimpleNamespace(
        url=SimpleNamespace(hostname="127.0.0.1", scheme="ws"), headers={}
    )
    ws_forwarded = SimpleNamespace(
        url=SimpleNamespace(hostname="example.com", scheme="ws"),
        headers={"x-forwarded-proto": "https"},
    )
    ws_secure = SimpleNamespace(
        url=SimpleNamespace(hostname="example.com", scheme="wss"), headers={}
    )
    ws_insecure = SimpleNamespace(
        url=SimpleNamespace(hostname="example.com", scheme="ws"), headers={}
    )

    assert is_local_websocket(ws_local) is True
    assert is_local_websocket(ws_ip) is True
    assert is_local_websocket(ws_insecure) is False
    assert is_secure_websocket(ws_forwarded) is True
    assert is_secure_websocket(ws_secure) is True
    assert is_secure_websocket(ws_insecure) is False


@pytest.mark.asyncio
async def test_redis_stream_provider_paths(monkeypatch):
    _install_fake_redis_module(monkeypatch, from_url=lambda _url: None)
    mod = importlib.import_module("democrai.core.infrastructure.network.providers.stream.redis")
    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    class _PubSub:
        def __init__(self, mode="ok"):
            self.mode = mode
            self.unsubscribed = []
            self.closed = False

        async def subscribe(self, _channel):
            return None

        async def listen(self):
            if self.mode == "err":
                raise RuntimeError("listener boom")
            if self.mode == "cancel":
                raise asyncio.CancelledError()
            yield {"type": "message", "data": json.dumps({"x": 1})}

        async def unsubscribe(self, channel):
            self.unsubscribed.append(channel)

        async def close(self):
            self.closed = True

    class _Redis:
        def __init__(self):
            self.published = []
            self.pubsub_obj = _PubSub()

        async def publish(self, channel, payload):
            self.published.append((channel, payload))

        def pubsub(self):
            return self.pubsub_obj

    fake = _Redis()
    monkeypatch.setattr(mod, "redis", SimpleNamespace(from_url=lambda _url: fake))
    provider = mod.RedisStreamProvider("redis://demo")

    q = provider.subscribe("room")
    q_b = provider.subscribe("room")  # existing-channel branch
    await provider.broadcast("room", {"a": 1})
    assert fake.published == [("room", '{"a": 1}')]

    await provider._redis_listener("room")
    assert await q.get() == {"x": 1}

    provider.unsubscribe("room", q)
    provider.unsubscribe("room", asyncio.Queue())  # queue-not-found branch
    provider.unsubscribe("missing", asyncio.Queue())  # channel-missing branch
    provider.unsubscribe("room", q_b)
    assert "room" not in provider._local_queues

    # Cancel branch in unsubscribe (listener task exists)
    t = asyncio.get_running_loop().create_task(asyncio.sleep(1))
    provider._local_queues["room2"] = [asyncio.Queue()]
    provider._listener_tasks["room2"] = t
    provider.unsubscribe("room2", provider._local_queues["room2"][0])
    await asyncio.sleep(0)
    assert t.cancelled() or t.done()
    provider._local_queues["room3x"] = []
    provider._listener_tasks["room3x"] = None
    provider.unsubscribe("room3x", asyncio.Queue())  # task None branch

    # Listener error branch
    fake2 = _Redis()
    fake2.pubsub_obj = _PubSub(mode="err")
    monkeypatch.setattr(mod, "redis", SimpleNamespace(from_url=lambda _url: fake2))
    provider2 = mod.RedisStreamProvider("redis://demo")
    provider2._local_queues["room3"] = [asyncio.Queue()]
    await provider2._redis_listener("room3")
    assert logger.errors

    # CancelledError branch with unsubscribe
    fake_cancel = _Redis()
    fake_cancel.pubsub_obj = _PubSub(mode="cancel")
    monkeypatch.setattr(mod, "redis", SimpleNamespace(from_url=lambda _url: fake_cancel))
    provider_cancel = mod.RedisStreamProvider("redis://demo")
    await provider_cancel._redis_listener("room-cancel")
    assert fake_cancel.pubsub_obj.unsubscribed == ["room-cancel"]

    # listener branches: redis remains None and non-message payload
    monkeypatch.setattr(mod, "redis", SimpleNamespace(from_url=lambda _url: None))
    provider3 = mod.RedisStreamProvider("redis://demo")
    await provider3._redis_listener("room-none")

    class _PubSubNonMessage(_PubSub):
        async def listen(self):
            yield {"type": "subscribe", "data": "ok"}
            yield {"type": "message", "data": json.dumps({"k": 1})}

    fake4 = _Redis()
    fake4.pubsub_obj = _PubSubNonMessage()
    monkeypatch.setattr(mod, "redis", SimpleNamespace(from_url=lambda _url: fake4))
    provider4 = mod.RedisStreamProvider("redis://demo")
    provider4._local_queues["room4"] = [asyncio.Queue()]
    await provider4._redis_listener("room4")

    # broadcast false branch when redis remains None
    monkeypatch.setattr(mod, "redis", SimpleNamespace(from_url=lambda _url: None))
    provider_none = mod.RedisStreamProvider("redis://demo")
    await provider_none.broadcast("room-none", {"a": 1})
    assert provider_none.redis is None


def test_network_runtime_lifecycle_paths(monkeypatch):
    lifecycle_mod = importlib.import_module("democrai.core.infrastructure.network.runtime.lifecycle")
    runtime_network_mod = importlib.import_module("democrai.core.infrastructure.network.runtime.network")
    logger = _Logger()
    ctx = SimpleNamespace(
        config=_Config({"network.redis.enabled": True, "network.redis.url": "redis://x"}),
        logger=logger,
        redis_task_bridge=None,
    )
    monkeypatch.setattr(runtime_network_mod, "app_ctx", lambda: ctx)

    class _FakeFuture:
        def __init__(self, exc: Exception | None = None):
            self.exc = exc

        def result(self, timeout=None):
            if self.exc:
                raise self.exc
            return None

    class _Loop:
        def __init__(self):
            self.stopped = False
            self.forever = False

        def run_forever(self):
            self.forever = True

        def stop(self):
            self.stopped = True

        def call_soon_threadsafe(self, cb):
            cb()

    loop = _Loop()
    monkeypatch.setattr(runtime_network_mod.asyncio, "new_event_loop", lambda: loop)
    monkeypatch.setattr(runtime_network_mod.asyncio, "set_event_loop", lambda _l: None)
    monkeypatch.setattr(
        runtime_network_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: (coro.close() or _FakeFuture()),
    )

    class _Thread:
        def __init__(self, target, name=None, daemon=None):
            self.target = target
            self.name = name
            self.daemon = daemon
            self.started = False
            self.joined = False

        def start(self):
            self.started = True

        def is_alive(self):
            return True

        def join(self, timeout=None):
            self.joined = True

    monkeypatch.setattr(runtime_network_mod.threading, "Thread", _Thread)

    class _Bridge:
        async def start(self):
            return None

        async def stop(self):
            return None

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.tasks.redis_task_bridge",
        SimpleNamespace(RedisTaskBridge=lambda *_a, **_k: _Bridge()),
    )

    class _Bus:
        def __init__(self):
            self.started = 0
            self.stopped = 0

        def start(self):
            self.started += 1

        def stop(self):
            self.stopped += 1

    bus = _Bus()
    task_manager = SimpleNamespace(
        set_loop=lambda _l: setattr(task_manager, "loop_set", True),
        recover_from_db=lambda: setattr(task_manager, "recovered", True),
    )

    network = SimpleNamespace(
        _loop=None,
        _loop_thread=None,
        _http_thread=None,
        _http_server=None,
        _run_network_loop=lambda: None,
        task_manager=task_manager,
        buses=[bus],
        connection_registry=object(),
        redis_task_bridge=None,
        core="core",
    )

    lifecycle_mod.start(network)
    assert network._loop is loop and bus.started == 1 and logger.infos

    ctx.setup_mode = True
    recovered_before_setup_start = getattr(task_manager, "recovered", False)
    delattr(task_manager, "recovered")
    lifecycle_mod.start(network)
    assert getattr(task_manager, "recovered", None) is None
    ctx.setup_mode = False
    task_manager.recovered = recovered_before_setup_start

    # start branch with redis disabled
    ctx.config = _Config({"network.redis.enabled": False})
    network.redis_task_bridge = None
    lifecycle_mod.start(network)
    # start branch with redis enabled but bridge factory returns None
    ctx.config = _Config({"network.redis.enabled": True, "network.redis.url": "redis://x"})
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.tasks.redis_task_bridge",
        SimpleNamespace(RedisTaskBridge=lambda *_a, **_k: None),
    )
    lifecycle_mod.start(network)

    class _UvicornConfig:
        def __init__(self, app, host, port, fd=None, log_level="info", loop="asyncio"):
            self.app = app
            self.host = host
            self.port = port
            self.fd = fd
            self.log_level = log_level
            self.loop = loop

    class _UvicornServer:
        def __init__(self, config):
            self.config = config
            self.should_exit = False
            self.ran = False

        def run(self):
            self.ran = True

    monkeypatch.setitem(
        sys.modules,
        "uvicorn",
        SimpleNamespace(Config=_UvicornConfig, Server=_UvicornServer),
    )
    monkeypatch.setattr(
        lifecycle_mod,
        "build_fastapi_app",
        lambda core, app_mode="full": {"core": core, "mode": app_mode},
    )

    lifecycle_mod.init_http_ws(network, "127.0.0.1", 9999, app_mode="media_proxy_only")
    assert network._http_server.config.port == 9999
    network._http_thread.target()  # run() branch inside _run
    lifecycle_mod.init_http_ws(network, "127.0.0.1", 9998, fd=10, app_mode="full")
    lifecycle_mod.stop_http_ws(network)
    assert network._http_server is None and network._http_thread is None
    lifecycle_mod.stop_http_ws(network)  # no server branch
    network._http_server = _UvicornServer(_UvicornConfig({}, "127.0.0.1", 9997))
    network._http_thread = SimpleNamespace(is_alive=lambda: False, join=lambda timeout=None: None)
    lifecycle_mod.stop_http_ws(network)  # thread not alive branch

    lifecycle_mod.run_network_loop(network)
    assert loop.forever is True

    # stop() error branch in _wait_shutdown
    monkeypatch.setattr(
        runtime_network_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: (coro.close() or _FakeFuture(RuntimeError("x"))),
    )
    network.stop_http_ws = lambda: None
    network.redis_task_bridge = _Bridge()
    lifecycle_mod.stop(network)
    assert bus.stopped == 1 and loop.stopped is True and logger.errors

    # stop success branch and without loop/bridge
    monkeypatch.setattr(
        runtime_network_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: (coro.close() or _FakeFuture()),
    )
    network.redis_task_bridge = None
    network._loop = None
    lifecycle_mod.stop(network)

    # _wait_shutdown branch with missing logger in app_ctx
    monkeypatch.setattr(runtime_network_mod, "app_ctx", lambda: SimpleNamespace())
    network._loop = loop
    network.redis_task_bridge = _Bridge()
    monkeypatch.setattr(
        runtime_network_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, _loop: (coro.close() or _FakeFuture(RuntimeError("x"))),
    )
    lifecycle_mod.stop(network)
