from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from democrai.core.application.ai.engine.invocation import (
    EngineInvocationRequest,
    EngineInvocationTarget,
)
import democrai.core.infrastructure.ai.engine.invocation.transports.queue as queue_client_mod
import democrai.core.infrastructure.ai.engine.response.providers.redis as redis_provider_mod
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.ai.engine.invocation.transports.queue import (
    EngineQueueTransport,
)
from democrai.core.infrastructure.ai.engine.response.reader import (
    EngineResponseStreamReader,
)
from democrai.core.infrastructure.ai.engine.response.factory import (
    EngineResponseStreamFactory,
    resolve_engine_response_stream,
)
from democrai.core.infrastructure.ai.engine.response.providers.memory import (
    MemoryEngineResponseStream,
)
from democrai.core.infrastructure.ai.engine.response.providers.redis import (
    RedisEngineResponseStream,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.infrastructure.network.providers.stream.memory import (
    MemoryStreamProvider,
)
from democrai.core.infrastructure.database.models import Base
from tests.runtime.fake_redis import FakeRedisStream


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'stream.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def store(session_factory):
    return EngineInvocationQueueStore(session_factory=session_factory)


def _reader(redis, store, request_id, **kwargs):
    return EngineResponseStreamReader(
        redis,
        f"democrai:engine:resp:{request_id}",
        request_id=request_id,
        store=store,
        keepalive_timeout_seconds=kwargs.pop("keepalive_timeout_seconds", 0.5),
        block_ms=kwargs.pop("block_ms", 100),
        **kwargs,
    )


def _target(*, objective="chat"):
    return EngineInvocationTarget(selector_type="objective", objective=objective)


def _request(method, payload=None):
    return EngineInvocationRequest(method=method, payload=payload)


def _writer(redis, request_id):
    return EngineResponseStreamWriter(
        redis, f"democrai:engine:resp:{request_id}", node_id="node-b"
    )


async def _collect(reader):
    return [entry async for entry in reader.entries()]


class _LocalTestStream(EngineResponseStream):
    def subscribe(self, channel_id):
        return asyncio.Queue()

    def unsubscribe(self, channel_id, queue):
        return None

    async def publish(self, channel_id, data):
        return None


class _ClosableLocalTestStream(_LocalTestStream):
    def __init__(self, **_kwargs):
        self.closed = 0

    async def aclose(self):
        self.closed += 1


class _FailsNextZaddRedis(FakeRedisStream):
    def __init__(self):
        super().__init__()
        self.fail_next_zadd = False

    async def zadd(self, key, mapping):
        if self.fail_next_zadd:
            self.fail_next_zadd = False
            raise ConnectionError("zadd down")
        return await super().zadd(key, mapping)


def test_stream_roundtrip_chunks_and_end(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-1",
            selector_type="objective",
            objective="chat",
            method="generate_stream",
            response_mode="stream",
            origin_node_id="node-a",
        )
        reader = _reader(redis, store, request_id)
        writer = _writer(redis, request_id)
        await writer.queued()
        await writer.accepted(attempt=1)
        await writer.chunk({"text": "ciao"})
        await writer.message({"type": "progress"})
        await writer.keepalive()
        await writer.chunk({"text": "mondo"})
        await writer.end()
        entries = await _collect(reader)
        kinds = [entry.kind for entry in entries]
        assert kinds == ["accepted", "chunk", "message", "chunk", "end"]
        assert entries[1].data == {"text": "ciao"}
        assert entries[0].node == "node-b"
        assert f"democrai:engine:resp:{request_id}" not in redis.subscriptions

    asyncio.run(scenario())


def test_memory_response_stream_applies_backpressure_when_subscriber_queue_full():
    async def scenario():
        stream = MemoryEngineResponseStream()
        queue = stream.subscribe("req-backpressure")
        for index in range(queue.maxsize):
            queue.put_nowait({"kind": "filler", "index": index})

        publish_task = asyncio.create_task(
            stream.publish("req-backpressure", {"kind": "chunk"})
        )
        await asyncio.sleep(0.05)
        assert not publish_task.done()

        queue.get_nowait()
        await asyncio.wait_for(publish_task, timeout=1.0)
        stream.unsubscribe("req-backpressure", queue)

    asyncio.run(scenario())


def test_redis_response_stream_applies_backpressure_when_buffer_full():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = FakeRedisStream()
        stream._redis = redis
        channel_id = "req-redis-backpressure"
        queue = stream.subscribe(channel_id)
        for index in range(queue.maxsize):
            queue.put_nowait({"kind": "filler", "index": index})
        for index in range(stream._maxlen):
            await redis.xadd(channel_id, {"kind": "filler", "index": index})

        publish_task = asyncio.create_task(
            stream.publish(channel_id, {"kind": "chunk"})
        )
        await asyncio.sleep(0.05)
        assert not publish_task.done()

        queue.get_nowait()
        await asyncio.wait_for(publish_task, timeout=1.0)
        stream.unsubscribe(channel_id, queue)

    asyncio.run(scenario())


def test_redis_response_stream_fails_when_buffer_full_without_subscriber():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = FakeRedisStream()
        stream._redis = redis
        channel_id = "req-redis-no-subscriber"
        for index in range(stream._maxlen):
            await redis.xadd(channel_id, {"kind": "filler", "index": index})

        with pytest.raises(RuntimeError, match="no_active_subscriber"):
            await stream.publish(channel_id, {"kind": "chunk"})

    asyncio.run(scenario())


def test_redis_response_stream_capacity_check_is_atomic():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = FakeRedisStream()
        stream._redis = redis
        channel_id = "req-redis-atomic"
        queue = stream.subscribe(channel_id)
        for index in range(queue.maxsize):
            queue.put_nowait({"kind": "filler", "index": index})
        for index in range(stream._maxlen - 1):
            await redis.xadd(channel_id, {"kind": "filler", "index": index})

        first = asyncio.create_task(stream.publish(channel_id, {"kind": "chunk"}))
        second = asyncio.create_task(stream.publish(channel_id, {"kind": "chunk"}))
        await asyncio.sleep(0.05)
        assert sum(task.done() for task in (first, second)) == 1
        assert await redis.xlen(channel_id) == stream._maxlen

        queue.get_nowait()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=1.0)
        stream.unsubscribe(channel_id, queue)

    asyncio.run(scenario())


def test_redis_response_stream_subscribe_is_visible_before_heartbeat_runs():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = FakeRedisStream()
        stream._redis = redis
        channel_id = "req-redis-subscribe-race"
        queue = stream.subscribe(channel_id)
        for index in range(queue.maxsize):
            queue.put_nowait({"kind": "filler", "index": index})
        for index in range(stream._maxlen):
            await redis.xadd(channel_id, {"kind": "filler", "index": index})

        publish_task = asyncio.create_task(
            stream.publish(channel_id, {"kind": "chunk"})
        )
        await asyncio.sleep(0.05)
        assert not publish_task.done()

        queue.get_nowait()
        await asyncio.wait_for(publish_task, timeout=1.0)
        stream.unsubscribe(channel_id, queue)

    asyncio.run(scenario())


def test_redis_response_stream_subscriber_heartbeat_survives_transient_error():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = _FailsNextZaddRedis()
        stream._redis = redis
        channel_id = "req-redis-heartbeat"
        queue = stream.subscribe(channel_id)
        await asyncio.sleep(0.05)

        redis.fail_next_zadd = True
        await asyncio.sleep(1.2)

        state = stream._states[channel_id]
        assert state.heartbeat_task is not None
        assert not state.heartbeat_task.done()
        assert redis.zsets[stream._subscribers_key(channel_id)]
        stream.unsubscribe(channel_id, queue)

    asyncio.run(scenario())


def test_redis_response_stream_unsubscribe_async_removes_subscriber_token():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = FakeRedisStream()
        stream._redis = redis
        channel_id = "req-redis-unsubscribe"
        queue = stream.subscribe(channel_id)
        await asyncio.sleep(0.05)
        subscribers_key = stream._subscribers_key(channel_id)
        assert redis.zsets[subscribers_key]

        await stream.unsubscribe_async(channel_id, queue)

        assert redis.zsets[subscribers_key] == {}
        assert channel_id not in stream._states

    asyncio.run(scenario())


def test_redis_response_stream_unsubscribe_releases_loop_local_client(monkeypatch):
    class _ClosableFakeRedis(FakeRedisStream):
        def __init__(self):
            super().__init__()
            self.closed = 0

        async def aclose(self):
            self.closed += 1
            await super().aclose()

    clients: list[_ClosableFakeRedis] = []

    def fake_from_url(_redis_url):
        client = _ClosableFakeRedis()
        clients.append(client)
        return client

    monkeypatch.setattr(redis_provider_mod.redis, "from_url", fake_from_url)
    stream = RedisEngineResponseStream(maxlen=100)

    async def scenario():
        queue = stream.subscribe("req-redis-release")
        await asyncio.sleep(0.05)
        await stream.unsubscribe_async("req-redis-release", queue)

    thread = threading.Thread(target=lambda: asyncio.run(scenario()))
    thread.start()
    thread.join(timeout=2)

    assert not thread.is_alive()
    assert len(clients) == 1
    assert clients[0].closed == 1
    assert stream._loop_states == {}


def test_redis_response_stream_aclose_removes_subscribers_and_closes_client():
    async def scenario():
        stream = RedisEngineResponseStream(maxlen=100)
        redis = FakeRedisStream()
        stream._redis = redis
        channel_id = "req-redis-close"
        stream.subscribe(channel_id)
        await asyncio.sleep(0.05)
        subscribers_key = stream._subscribers_key(channel_id)
        assert redis.zsets[subscribers_key]

        await stream.aclose()

        assert stream._states == {}
        assert stream._redis is None
        assert redis.zsets[subscribers_key] == {}

    asyncio.run(scenario())


def test_redis_response_stream_aclose_only_closes_current_loop_state(monkeypatch):
    clients: list[FakeRedisStream] = []

    def fake_from_url(_redis_url):
        client = FakeRedisStream()
        clients.append(client)
        return client

    monkeypatch.setattr(redis_provider_mod.redis, "from_url", fake_from_url)
    stream = RedisEngineResponseStream(maxlen=100)
    ready = threading.Event()
    errors: list[BaseException] = []
    holder: dict[str, object] = {}

    async def thread_main():
        holder["loop"] = asyncio.get_running_loop()
        holder["stop"] = asyncio.Event()
        stream.subscribe("req-cross-loop")
        ready.set()
        await holder["stop"].wait()
        await stream.aclose()

    def run_thread():
        try:
            asyncio.run(thread_main())
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run_thread, daemon=True)
    thread.start()
    assert ready.wait(timeout=2)

    asyncio.run(stream.aclose())
    assert thread.is_alive()

    loop = holder["loop"]
    stop = holder["stop"]
    loop.call_soon_threadsafe(stop.set)
    thread.join(timeout=2)

    assert errors == []
    assert not thread.is_alive()


def test_queue_transport_rejects_any_non_cross_process_response_stream(monkeypatch):
    registry = dict(EngineResponseStreamFactory._registry)
    monkeypatch.setattr(EngineResponseStreamFactory, "_registry", registry)
    EngineResponseStreamFactory.register(
        "local-test-stream",
        _LocalTestStream,
        cross_process=False,
    )
    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(
            get=lambda key, default=None: {
                "ai.engine_orchestrator.response_stream.type": "local-test-stream",
            }.get(key, default)
        ),
        node_id="node-a",
    )
    monkeypatch.setattr(queue_client_mod, "app_ctx", lambda: fake_ctx)

    with pytest.raises(
        RuntimeError,
        match="engine_queue_response_stream_cross_process_provider_required",
    ):
        EngineQueueTransport()


def test_engine_response_stream_rejects_generic_network_stream_provider():
    with pytest.raises(RuntimeError, match="engine_response_stream_provider_object_invalid"):
        resolve_engine_response_stream(MemoryStreamProvider())


def test_engine_response_stream_factory_reuses_and_closes_shared_stream(monkeypatch):
    registry = dict(EngineResponseStreamFactory._registry)
    monkeypatch.setattr(EngineResponseStreamFactory, "_registry", registry)
    monkeypatch.setattr(EngineResponseStreamFactory, "_shared_streams", {})
    EngineResponseStreamFactory.register(
        "shared-test-stream",
        _ClosableLocalTestStream,
        cross_process=True,
    )
    fake_config = SimpleNamespace(
        get=lambda key, default=None: {
            "ai.engine_orchestrator.response_stream.type": "shared-test-stream",
        }.get(key, default)
    )

    first = EngineResponseStreamFactory.get_shared_stream(fake_config)
    second = EngineResponseStreamFactory.get_shared_stream(fake_config)

    assert first is second
    asyncio.run(EngineResponseStreamFactory.aclose_shared_streams())
    assert first.closed == 1
    assert EngineResponseStreamFactory._shared_streams == {}


def test_stream_error_entry(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-err",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        reader = _reader(redis, store, request_id)
        writer = _writer(redis, request_id)
        await writer.error("boom", traceback_text="tb")
        entries = await _collect(reader)
        assert entries[-1].kind == "error"
        assert entries[-1].data == {"error": "boom", "traceback": "tb"}

    asyncio.run(scenario())


def test_retry_entry_keeps_reader_waiting(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-retry",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        reader = _reader(redis, store, request_id)
        writer = _writer(redis, request_id)
        await writer.retry(attempt=1, error="quota")

        async def finish_later():
            await asyncio.sleep(0.2)
            await writer.accepted(attempt=2)
            await writer.result({"answer": 42})
            await writer.end()

        producer = asyncio.create_task(finish_later())
        entries = await _collect(reader)
        await producer
        kinds = [entry.kind for entry in entries]
        assert kinds == ["retry", "accepted", "result", "end"]

    asyncio.run(scenario())


def test_silence_with_terminal_row_raises(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-dead",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        store.claim([request_id], owner="node-b", lease_seconds=60)
        store.fail(
            request_id,
            owner="node-b",
            error="kaput",
            retriable=False,
            max_attempts=3,
        )
        reader = _reader(redis, store, request_id, keepalive_timeout_seconds=0.2)
        with pytest.raises(RuntimeError, match="stream_terminated_without_end"):
            await _collect(reader)

    asyncio.run(scenario())


def test_silence_with_processing_row_keeps_waiting(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-slow",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        store.claim([request_id], owner="node-b", lease_seconds=60)
        writer = _writer(redis, request_id)

        async def finish_later():
            await asyncio.sleep(0.6)
            await writer.result({"ok": True})
            await writer.end()

        producer = asyncio.create_task(finish_later())
        reader = _reader(redis, store, request_id, keepalive_timeout_seconds=0.2)
        entries = await _collect(reader)
        await producer
        assert [entry.kind for entry in entries] == ["result", "end"]

    asyncio.run(scenario())


def test_reader_close_before_terminal_requests_cancel(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-reader-cancel",
            selector_type="objective",
            objective="chat",
            method="generate_stream",
            response_mode="stream",
            origin_node_id="node-a",
        )
        store.claim([request_id], owner="node-b", lease_seconds=60)
        reader = _reader(redis, store, request_id)
        writer = _writer(redis, request_id)
        await writer.accepted(attempt=1)

        entries = reader.entries()
        entry = await entries.__anext__()
        assert entry.kind == "accepted"
        await entries.aclose()

        status = store.get_status(request_id)
        assert status["cancel_requested"] is True

    asyncio.run(scenario())


@pytest.fixture
def queue_client(store, monkeypatch):
    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        node_id="node-a",
    )
    monkeypatch.setattr(queue_client_mod, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(
        queue_client_mod,
        "build_request_context_json",
        lambda *, origin, request_id: "{}",
    )
    redis = FakeRedisStream()
    client = EngineQueueTransport(store=store, response_stream=redis)
    client._keepalive_seconds = 0.2
    return client, redis


def test_queue_client_unary_roundtrip(queue_client, store):
    client, redis = queue_client

    async def scenario():
        async def producer():
            for _ in range(100):
                rows = store.peek_claimable()
                if rows:
                    break
                await asyncio.sleep(0.01)
            row = store.claim([rows[0]["id"]], owner="node-b", lease_seconds=60)[0]
            writer = EngineResponseStreamWriter(
                redis, row["response_stream_key"], node_id="node-b"
            )
            await writer.accepted(attempt=1)
            await writer.result({"text": "ok"})
            await writer.end()
            store.complete(row["id"])

        producer_task = asyncio.create_task(producer())
        result = await client.invoke(
            _target(objective="chat"),
            _request("generate_completion", {"messages": []}),
        )
        await producer_task
        assert result == {"text": "ok"}

    asyncio.run(scenario())


def test_queue_client_stream_roundtrip_and_on_message(queue_client, store):
    client, redis = queue_client

    async def scenario():
        messages = []

        async def producer():
            for _ in range(100):
                rows = store.peek_claimable()
                if rows:
                    break
                await asyncio.sleep(0.01)
            row = store.claim([rows[0]["id"]], owner="node-b", lease_seconds=60)[0]
            assert row["response_mode"] == "stream"
            writer = EngineResponseStreamWriter(
                redis, row["response_stream_key"], node_id="node-b"
            )
            await writer.accepted(attempt=1)
            await writer.chunk("hello ")
            await writer.message(
                {
                    "type": "engine_orchestrator.provider_resolved",
                    "pipeline_id": "pipe-1",
                    "current_pipeline_id": "pipe-1",
                    "parent_pipeline_id": None,
                    "request_id": row["id"],
                    "root_method": "generate_stream",
                    "status": "running",
                    "payload": {},
                }
            )
            await writer.chunk("world")
            await writer.end()
            store.complete(row["id"])

        producer_task = asyncio.create_task(producer())
        chunks = []
        async for item in client.invoke_stream(
            _target(objective="chat"),
            _request("generate_stream", {}),
            on_message=lambda value: messages.append(value),
        ):
            chunks.append(item)
        await producer_task
        assert chunks == ["hello ", "world"]
        assert len(messages) == 1

    asyncio.run(scenario())


def test_queue_client_error_raises(queue_client, store):
    client, redis = queue_client

    async def scenario():
        async def producer():
            for _ in range(100):
                rows = store.peek_claimable()
                if rows:
                    break
                await asyncio.sleep(0.01)
            row = store.claim([rows[0]["id"]], owner="node-b", lease_seconds=60)[0]
            writer = EngineResponseStreamWriter(
                redis, row["response_stream_key"], node_id="node-b"
            )
            await writer.error("engine exploded", traceback_text="tb")
            store.fail(
                row["id"],
                owner="node-b",
                error="engine exploded",
                retriable=False,
                max_attempts=3,
            )

        producer_task = asyncio.create_task(producer())
        with pytest.raises(RuntimeError, match="engine exploded"):
            await client.invoke(
                _target(objective="chat"),
                _request("generate_completion"),
            )
        await producer_task

    asyncio.run(scenario())


def test_queue_client_cancel_marks_pending_cancelled(queue_client, store):
    client, _redis = queue_client
    request_id = store.enqueue(
        request_id="req-c",
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin_node_id="node-a",
    )
    assert client.cancel_sync(request_id) is True
    assert store.get_status(request_id)["status"] == "cancelled"


def test_queue_client_validate_runs_locally(queue_client, store, monkeypatch):
    client, _redis = queue_client
    captured = {}

    def fake_validate(request):
        captured["selector_type"] = request.selector_type
        return {"status": "ok", "selector_type": request.selector_type}

    import democrai.core.application.ai.engine.orchestrator.resolver as resolver_mod

    monkeypatch.setattr(resolver_mod, "validate_selector", fake_validate)

    async def scenario():
        result = await client.invoke(
            _target(objective="chat"),
            _request("__validate_provider__"),
        )
        assert result["status"] == "ok"
        # nothing was enqueued
        assert store.peek_claimable() == []

    asyncio.run(scenario())
