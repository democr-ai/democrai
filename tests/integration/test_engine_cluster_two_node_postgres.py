"""Two-node cluster integration on REAL postgres + redis (containers).

Covers exactly what the sqlite/fakeredis simulation cannot: FOR UPDATE
SKIP LOCKED under true concurrency, LISTEN/NOTIFY wake-up, redis streams
transport and lease takeover with a live zombie run.

Requires the services from docker/cluster-test/docker-compose.yml:

    docker compose -f docker/cluster-test/docker-compose.yml up -d --wait
    DEMOCRAI_CLUSTER_TEST_PG=postgresql://democrai:democrai@127.0.0.1:5440/democrai_cluster_test \
    DEMOCRAI_CLUSTER_TEST_REDIS=redis://127.0.0.1:6390/0 \
      .venv/bin/python -m pytest -c tests/pytest.ini \
      tests/integration/test_engine_cluster_two_node_postgres.py -v

Skipped automatically when the services are not reachable.
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from democrai.core.application.ai.engine.invocation import (
    EngineInvocationRequest,
    EngineInvocationTarget,
)
import democrai.core.infrastructure.ai.engine.invocation.queue.claim_worker as claim_worker_mod
import democrai.core.infrastructure.ai.engine.invocation.transports.queue as queue_client_mod
from democrai.core.infrastructure.ai.engine.invocation.queue.claim_worker import (
    EngineQueueClaimWorker,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.ai.engine.invocation.transports.queue import (
    EngineQueueTransport,
)
from democrai.core.infrastructure.ai.engine.response.providers.redis import (
    RedisEngineResponseStream,
)
from democrai.core.infrastructure.database.models import (
    EngineInvocationQueue,
    EngineNodeInstallRegistry,
    EngineNodeInstanceRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.platform.utils.timezone import utc_now_naive


PG_URL = os.environ.get("DEMOCRAI_CLUSTER_TEST_PG", "")
REDIS_URL = os.environ.get("DEMOCRAI_CLUSTER_TEST_REDIS", "")


def _target(*, objective="chat"):
    return EngineInvocationTarget(selector_type="objective", objective=objective)


def _request(method, payload=None):
    return EngineInvocationRequest(method=method, payload=payload)

_TABLES = [
    EngineInvocationQueue.__table__,
    RuntimeNodeRegistry.__table__,
    EngineNodeInstanceRegistry.__table__,
    EngineNodeInstallRegistry.__table__,
]


def _services_available() -> bool:
    if not PG_URL or not REDIS_URL:
        return False
    try:
        engine = sa.create_engine(PG_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
        engine.dispose()
    except Exception:
        return False
    try:
        import redis as redis_sync

        client = redis_sync.from_url(REDIS_URL, socket_connect_timeout=2)
        client.ping()
        client.close()
    except Exception:
        return False
    return True


if not _services_available():
    pytest.skip(
        "postgres/redis cluster-test services not reachable "
        "(see docker/cluster-test/docker-compose.yml)",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def pg_engine():
    engine = sa.create_engine(PG_URL)
    sa.MetaData()  # noqa: F841 - keep import obvious
    for table in _TABLES:
        table.drop(engine, checkfirst=True)
    for table in _TABLES:
        table.create(engine)
    yield engine
    for table in reversed(_TABLES):
        table.drop(engine, checkfirst=True)
    engine.dispose()


@pytest.fixture
def session_factory(pg_engine):
    with pg_engine.connect() as connection:
        for table in reversed(_TABLES):
            connection.execute(table.delete())
        connection.commit()
    return sessionmaker(bind=pg_engine)


@pytest.fixture
def store(session_factory):
    return EngineInvocationQueueStore(session_factory=session_factory)


class _FakeJobRegistry:
    def __init__(self):
        self.jobs = {}
        self.cancelled = []

    def get(self, request_id):
        return self.jobs.get(request_id)

    def remove(self, request_id):
        return self.jobs.pop(request_id, None)

    def cancel(self, request_id, reason=""):
        self.cancelled.append((request_id, reason))
        job = self.jobs.get(request_id)
        if job is not None:
            job.done = True
        return True


class _NodeService:
    def __init__(self, node_id, *, unary=None, stream=None, delay=0.0):
        self.node_id = node_id
        self._job_registry = _FakeJobRegistry()
        self._unary = unary
        self._stream = stream
        self._delay = delay
        self.executed = []

    async def _invoke_unary_job(self, request, context):
        self.executed.append(request.request_id)
        if self._delay:
            await asyncio.sleep(self._delay)
        if callable(self._unary):
            return await self._unary(request, context)
        if isinstance(self._unary, BaseException):
            raise self._unary
        return {"served_by": self.node_id}

    async def _invoke_stream_job(self, request, context):
        self.executed.append(request.request_id)
        for chunk in self._stream or []:
            yield chunk


@pytest.fixture
def cluster(store, session_factory, monkeypatch):
    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        node_id="node-a",
        logger=None,
    )
    for module in (claim_worker_mod, queue_client_mod):
        monkeypatch.setattr(module, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(
        queue_client_mod,
        "build_request_context_json",
        lambda *, origin, request_id: "{}",
    )
    # the NOTIFY listener resolves its connection through this
    monkeypatch.setattr(claim_worker_mod, "SessionLocal", session_factory)

    import redis.asyncio as aioredis

    def make_redis():
        return aioredis.from_url(REDIS_URL)

    def make_response_stream():
        return RedisEngineResponseStream(redis_url=REDIS_URL)

    def make_node(node_id, *, response_stream, unary=None, stream=None, delay=0.0):
        service = _NodeService(node_id, unary=unary, stream=stream, delay=delay)
        worker = EngineQueueClaimWorker(
            node_id=node_id,
            service=service,
            store=store,
            response_stream=response_stream,
        )
        worker._keepalive_seconds = 0.5
        worker._predict_target = lambda row: {
            "engine_row_id": 1,
            "engine_id": "",
            "model_registry_id": 1,
        }
        worker._engine_capacity_limit = lambda engine_row_id: 64
        return worker, service

    return SimpleNamespace(
        store=store,
        session_factory=session_factory,
        make_node=make_node,
        make_redis=make_redis,
        make_response_stream=make_response_stream,
    )


def _enqueue(store, request_id, **overrides):
    values = {
        "request_id": request_id,
        "selector_type": "objective",
        "objective": "chat",
        "method": "generate_completion",
        "origin_node_id": "node-a",
    }
    values.update(overrides)
    return store.enqueue(**values)


async def _flush_redis(redis_client):
    await redis_client.flushdb()


async def _drain(worker):
    await worker._tick()
    if worker._tasks:
        await asyncio.gather(*list(worker._tasks), return_exceptions=True)


def test_concurrent_claims_never_double_execute(cluster):
    """Real FOR UPDATE SKIP LOCKED: two nodes ticking concurrently must
    split 20 rows with no row executed twice."""

    async def scenario():
        redis_client = cluster.make_redis()
        await _flush_redis(redis_client)
        response_stream = cluster.make_response_stream()
        worker_a, service_a = cluster.make_node(
            "node-a", response_stream=response_stream, delay=0.01
        )
        worker_b, service_b = cluster.make_node(
            "node-b", response_stream=response_stream, delay=0.01
        )
        for index in range(20):
            _enqueue(cluster.store, f"req-{index:02d}")

        for _ in range(30):
            await asyncio.gather(_drain(worker_a), _drain(worker_b))
            statuses = [
                cluster.store.get_status(f"req-{index:02d}")["status"]
                for index in range(20)
            ]
            if all(status == "completed" for status in statuses):
                break
            await asyncio.sleep(0.05)

        await redis_client.aclose()
        return service_a.executed, service_b.executed

    executed_a, executed_b = asyncio.run(scenario())
    all_executed = executed_a + executed_b
    # the property under test is exactly-once execution under concurrent
    # claims (which node wins each batch is scheduling luck)
    assert sorted(all_executed) == sorted(f"req-{index:02d}" for index in range(20))
    assert len(all_executed) == len(set(all_executed)), "row executed twice"


def test_listen_notify_wakes_claim_loop(cluster):
    """With the poll failsafe pushed to 30s, a claim within a couple of
    seconds proves the LISTEN/NOTIFY wake-up path works end to end."""

    async def scenario():
        redis_client = cluster.make_redis()
        await _flush_redis(redis_client)
        response_stream = cluster.make_response_stream()
        worker, service = cluster.make_node("node-a", response_stream=response_stream)
        worker._poll_seconds = 30.0
        stop_event = asyncio.Event()
        loop_task = asyncio.create_task(worker.run_until_stopped(stop_event))
        try:
            # let the first (empty) tick pass and the LISTEN attach
            await asyncio.sleep(1.5)
            enqueued_at = time.monotonic()
            await asyncio.to_thread(_enqueue, cluster.store, "req-notify")
            while not service.executed:
                if time.monotonic() - enqueued_at > 10:
                    raise AssertionError(
                        "row not claimed within 10s: NOTIFY wake-up dead "
                        "(poll failsafe is 30s)"
                    )
                await asyncio.sleep(0.05)
            return time.monotonic() - enqueued_at
        finally:
            stop_event.set()
            try:
                await asyncio.wait_for(loop_task, timeout=10)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                loop_task.cancel()
            await redis_client.aclose()

    latency = asyncio.run(scenario())
    assert latency < 5.0, f"claim latency {latency:.2f}s: NOTIFY not effective"


def test_stream_end_to_end_on_real_redis(cluster):
    """EngineQueueTransport against real redis streams: chunks ordered, seq
    contiguous, and end terminates."""

    async def scenario():
        redis_client = cluster.make_redis()
        await _flush_redis(redis_client)
        response_stream = cluster.make_response_stream()
        chunks = [
            SimpleNamespace(kind="chunk", chunk_json=f'"tok-{index}"')
            for index in range(50)
        ]
        worker, service = cluster.make_node(
            "node-b", response_stream=response_stream, stream=chunks
        )
        client = EngineQueueTransport(store=cluster.store, response_stream=response_stream)
        client._keepalive_seconds = 0.5

        done = asyncio.Event()

        async def ticks():
            while not done.is_set():
                await _drain(worker)
                await asyncio.sleep(0.05)

        tick_task = asyncio.create_task(ticks())
        received = []
        try:
            async for item in client.invoke_stream(
                _target(objective="chat"),
                _request("generate_stream", {}),
            ):
                received.append(item)
        finally:
            done.set()
            await asyncio.wait_for(tick_task, timeout=10)

        await redis_client.aclose()
        return received, service.executed

    received, executed = asyncio.run(scenario())
    assert received == [f"tok-{index}" for index in range(50)]
    assert len(executed) == 1


def test_lease_takeover_zombie_stays_silent(cluster):
    """Node A stalls past its lease; node B takes the row over and serves
    it; A's zombie run must settle nothing and write nothing further."""

    async def blocked_until_cancelled(request, context):
        while not context.cancelled():
            await asyncio.sleep(0.05)
        raise asyncio.CancelledError()

    async def scenario():
        redis_client = cluster.make_redis()
        await _flush_redis(redis_client)
        response_stream = cluster.make_response_stream()
        worker_a, service_a = cluster.make_node(
            "node-a", response_stream=response_stream, unary=blocked_until_cancelled
        )
        # widen A's renew interval so it cannot re-extend the lease in the
        # window between the forced expiry and B's claim
        worker_a._keepalive_seconds = 3
        worker_b, service_b = cluster.make_node("node-b", response_stream=response_stream)

        request_id = _enqueue(cluster.store, "req-takeover")
        await _drain_start(worker_a)
        await asyncio.sleep(0.2)
        # A is executing and stuck; a live run renews its lease (by design),
        # so the stall is simulated by force-expiring it in the DB
        def _expire_lease():
            with cluster.session_factory() as session:
                row = session.get(EngineInvocationQueue, request_id)
                row.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
                session.commit()

        await asyncio.to_thread(_expire_lease)
        for _ in range(40):
            await _drain(worker_b)
            state = cluster.store.get_status(request_id)
            if state["status"] == "completed":
                break
            await asyncio.sleep(0.1)
        # let A's zombie notice and exit
        await asyncio.gather(*list(worker_a._tasks), return_exceptions=True)

        entries = await redis_client.xrange(f"democrai:engine:resp:{request_id}")
        await redis_client.aclose()
        return cluster.store.get_status(request_id), entries, service_b.executed

    state, entries, executed_b = asyncio.run(scenario())
    assert state["status"] == "completed"
    assert executed_b == ["req-takeover"]
    kinds = [fields.get(b"kind", b"").decode() for _id, fields in entries]
    # A: accepted(1). B: accepted(2), result, end. No zombie writes after.
    assert kinds == ["accepted", "accepted", "result", "end"]


async def _drain_start(worker):
    """Run one tick but do NOT await the spawned execution tasks."""
    await worker._tick()
