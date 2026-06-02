import asyncio
import importlib
import sys
from types import SimpleNamespace
from urllib.parse import quote

class _FakeRedis:
    def __init__(self):
        self.published = []
        self.closed = False

    async def publish(self, channel, payload):
        self.published.append((channel, payload))

    async def aclose(self):
        self.closed = True


class _FakePubSub:
    def __init__(self, messages):
        self.messages = list(messages)
        self.patterns = []
        self.closed = False

    async def psubscribe(self, *patterns):
        self.patterns.extend(patterns)

    async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
        if self.messages:
            return self.messages.pop(0)
        await asyncio.sleep(0)
        return None

    async def punsubscribe(self, *patterns):
        return None

    async def close(self):
        self.closed = True


class _FakeSubRedis:
    def __init__(self, pubsub):
        self._pubsub = pubsub
        self.closed = False

    def pubsub(self):
        return self._pubsub

    async def aclose(self):
        self.closed = True


class _FakeBus:
    def __init__(self):
        self.sent = []

    def send(self, client_id, message):
        self.sent.append((client_id, message))


class _FakeRegistry:
    def __init__(self, connections):
        self.connections = connections
        self.lookups = []

    def get_connections(self, user_id, organization_id=None):
        self.lookups.append((user_id, organization_id))
        return list(self.connections.get((user_id, organization_id), []))


def _load_bridge_module(monkeypatch):
    fake_redis_module = SimpleNamespace(asyncio=SimpleNamespace(Redis=object))
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)
    monkeypatch.setitem(sys.modules, "redis.asyncio", SimpleNamespace(Redis=object))
    bridge_mod = importlib.import_module("democrai.core.application.tasks.redis_task_bridge")
    return bridge_mod, bridge_mod.RedisTaskBridge


def test_redis_task_bridge_publish_includes_organization_scope(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    registry = _FakeRegistry({})
    bridge = RedisTaskBridge("redis://cluster:6379/0", registry)
    bridge._redis = _FakeRedis()

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )

    async def _run():
        bridge.publish(1, {"kind": "event"}, 1)
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert bridge._redis.published == [
        ("task_notify:1:1", '{"kind": "event"}'),
    ]


def test_redis_task_bridge_listener_delivers_only_matching_scope(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    bus = _FakeBus()
    registry = _FakeRegistry({(1, 1): [(bus, "client-1")]})
    pubsub = _FakePubSub(
        [
            {
                "type": "pmessage",
                "channel": b"task_notify:1:1",
                "data": b'{"kind":"event"}',
            }
        ]
    )
    bridge = RedisTaskBridge("redis://cluster:6379/0", registry)
    bridge._sub_redis = _FakeSubRedis(pubsub)
    bridge._running = True

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )

    async def _run():
        task = asyncio.create_task(bridge._listener())
        await asyncio.sleep(0.05)
        bridge._running = False
        await task

    asyncio.run(_run())

    assert registry.lookups == [(1, 1)]
    assert bus.sent == [("client-1", {"kind": "event"})]


def test_redis_task_bridge_channel_helpers_roundtrip():
    bridge_mod = importlib.import_module("democrai.core.application.tasks.redis_task_bridge")

    channel = bridge_mod._channel_name(1, 2)

    assert channel == "task_notify:1:2"
    assert bridge_mod._parse_channel_name(channel) == (1, 2)
    assert bridge_mod._parse_channel_name("invalid") == (None, None)


def test_redis_task_bridge_start_stop_and_publish_error_paths(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    logs = {"info": [], "error": []}

    pubsub = _FakePubSub([])
    connections = _FakeRegistry({})
    bridge = RedisTaskBridge("redis://cluster:6379/0", connections)
    created = []
    publisher = _FakeRedis()

    def _from_url(url):
        created.append(url)
        if len(created) == 1:
            return _FakeSubRedis(pubsub)
        return publisher

    monkeypatch.setattr(
        bridge_mod,
        "aioredis",
        SimpleNamespace(from_url=_from_url, Redis=object),
    )
    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda message, *a, **k: logs["info"].append(message),
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda message, *a, **k: logs["error"].append(message),
            )
        ),
    )

    async def _run():
        await bridge.start()
        await bridge.start()
        assert bridge._running is True
        await asyncio.sleep(0.01)
        await bridge._ensure_connected()
        await bridge.stop()

    asyncio.run(_run())

    assert created == ["redis://cluster:6379/0", "redis://cluster:6379/0"]
    assert "[RedisTaskBridge] Listening on task_notify:*" in logs["info"][0]
    assert "[RedisTaskBridge] Stopped." in logs["info"][-1]
    assert publisher.closed is True
    assert bridge._sub_redis is None
    assert bridge._listener_task is None

    bridge = RedisTaskBridge("redis://cluster:6379/0", connections)
    bridge._redis = SimpleNamespace(
        publish=lambda channel, payload: (_ for _ in ()).throw(RuntimeError("publish boom"))
    )
    monkeypatch.setattr(bridge_mod.asyncio, "get_event_loop", lambda: (_ for _ in ()).throw(RuntimeError("no loop")))
    bridge.publish(1, {"kind": "event"}, 1)
    assert "[RedisTaskBridge] No event loop for publish" in logs["error"][-1]

    class _Loop:
        def is_running(self):
            return False

        def run_until_complete(self, coro):
            return asyncio.run(coro)

    bridge = RedisTaskBridge("redis://cluster:6379/0", connections)
    bridge._redis = publisher = _FakeRedis()
    monkeypatch.setattr(bridge_mod.asyncio, "get_event_loop", lambda: _Loop())
    bridge.publish(1, {"kind": "event"}, 1)
    assert publisher.published == [("task_notify:1:1", '{"kind": "event"}')]


def test_redis_task_bridge_listener_handles_invalid_json_and_send_errors(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    errors = []
    warnings = []

    class _BrokenBus:
        def send(self, client_id, message):
            raise RuntimeError("send boom")

    registry = _FakeRegistry({(1, 1): [(_BrokenBus(), "client-1")]})
    pubsub = _FakePubSub(
        [
            {"type": "ignore", "channel": "task_notify:1:1", "data": "{}"},
            {"type": "pmessage", "channel": b"task_notify:1:1", "data": b"not-json"},
            {"type": "pmessage", "channel": b"task_notify:1:1", "data": b'{"kind":"ok"}'},
        ]
    )
    bridge = RedisTaskBridge("redis://cluster:6379/0", registry)
    bridge._sub_redis = _FakeSubRedis(pubsub)
    bridge._running = True

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda *a, **k: None,
                warning=lambda message, *a, **k: warnings.append(message),
                error=lambda message, *a, **k: errors.append(message),
            )
        ),
    )

    async def _run():
        task = asyncio.create_task(bridge._listener())
        await asyncio.sleep(0.05)
        bridge._running = False
        await task

    asyncio.run(_run())

    assert "Invalid JSON" in warnings[0]
    assert "Local send error: send boom" in errors[0]


def test_redis_task_bridge_listener_handles_missing_subscriber_and_bad_channels(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    logs = {"debug": [], "error": []}
    registry = _FakeRegistry({})
    bridge = RedisTaskBridge("redis://cluster:6379/0", registry)

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda message, *a, **k: logs["debug"].append(message),
                warning=lambda *a, **k: None,
                error=lambda message, *a, **k: logs["error"].append(message),
            )
        ),
    )

    asyncio.run(bridge._listener())
    assert "Listener started without subscriber connection" in logs["error"][0]

    pubsub = _FakePubSub(
        [
            {"type": "pmessage", "channel": b"bad-channel", "data": b"{}"},
            {"type": "pmessage", "channel": "task_notify:1:1", "data": '{"kind":"ok"}'},
        ]
    )
    bridge._sub_redis = _FakeSubRedis(pubsub)
    bridge._running = True

    async def _run():
        task = asyncio.create_task(bridge._listener())
        await asyncio.sleep(0.05)
        bridge._running = False
        await task

    asyncio.run(_run())
    assert registry.lookups == [(1, 1)]


def test_redis_task_bridge_publish_logs_runtime_publish_failures(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    errors = []
    bridge = RedisTaskBridge("redis://cluster:6379/0", _FakeRegistry({}))
    bridge._redis = SimpleNamespace(
        publish=lambda channel, payload: (_ for _ in ()).throw(RuntimeError("publish boom"))
    )
    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda message, *a, **k: errors.append(message),
            )
        ),
    )

    async def _run():
        bridge.publish(1, {"kind": "event"}, 1)
        await asyncio.sleep(0)

    asyncio.run(_run())

    assert any("Publish error: publish boom" in message for message in errors)


def test_redis_task_bridge_stop_noop_and_listener_outer_error(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    errors = []
    infos = []
    bridge = RedisTaskBridge("redis://cluster:6379/0", _FakeRegistry({}))

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda message, *a, **k: infos.append(message),
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda message, *a, **k: errors.append(message),
            )
        ),
    )

    asyncio.run(bridge.stop())
    assert infos[-1] == "[RedisTaskBridge] Stopped."

    class _ExplodingPubSub(_FakePubSub):
        async def get_message(self, ignore_subscribe_messages=True, timeout=1.0):
            raise RuntimeError("listen boom")

    pubsub = _ExplodingPubSub([])
    bridge._sub_redis = _FakeSubRedis(pubsub)
    bridge._running = True

    asyncio.run(bridge._listener())
    assert "Listener error: listen boom" in errors[-1]
    assert pubsub.closed is True


def test_redis_task_bridge_stop_swallow_cancelled_listener(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    infos = []
    bridge = RedisTaskBridge("redis://cluster:6379/0", _FakeRegistry({}))

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda message, *a, **k: infos.append(message),
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )

    async def _listener():
        await asyncio.sleep(10)

    async def _run():
        bridge._listener_task = asyncio.create_task(_listener())
        await asyncio.sleep(0)
        await bridge.stop()

    asyncio.run(_run())
    assert infos[-1] == "[RedisTaskBridge] Stopped."


def test_redis_task_bridge_listener_accepts_string_payload(monkeypatch):
    bridge_mod, RedisTaskBridge = _load_bridge_module(monkeypatch)
    bus = _FakeBus()
    registry = _FakeRegistry({(1, 1): [(bus, "client-1")]})
    pubsub = _FakePubSub(
        [{"type": "pmessage", "channel": "task_notify:1:1", "data": '{"kind":"event"}'}]
    )
    bridge = RedisTaskBridge("redis://cluster:6379/0", registry)
    bridge._sub_redis = _FakeSubRedis(pubsub)
    bridge._running = True

    monkeypatch.setattr(
        bridge_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(
                info=lambda *a, **k: None,
                debug=lambda *a, **k: None,
                warning=lambda *a, **k: None,
                error=lambda *a, **k: None,
            )
        ),
    )

    async def _run():
        task = asyncio.create_task(bridge._listener())
        await asyncio.sleep(0.05)
        bridge._running = False
        await task

    asyncio.run(_run())
    assert bus.sent == [("client-1", {"kind": "event"})]
