"""Two simulated cluster nodes sharing one queue DB and one redis.

Exercises the real components (queue store, claim worker, placement,
queue client) end-to-end without real postgres/redis: SKIP LOCKED and
LISTEN/NOTIFY are postgres-only and the workers here tick sequentially,
so the simulation stays deterministic. Real-concurrency claim behavior
is covered by the postgres-marked tests when the service is available.
"""

from __future__ import annotations

import asyncio
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
import democrai.core.application.ai.engine.orchestrator.placement as placement_mod
import democrai.core.infrastructure.ai.engine.invocation.transports.queue as queue_client_mod
from democrai.core.infrastructure.ai.engine.invocation.queue.claim_worker import (
    EngineQueueClaimWorker,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.application.ai.engine.orchestrator.node_views import (
    NodeResourcesView,
)
from democrai.core.application.ai.engine.orchestrator.placement import (
    EnginePlacement,
)
from democrai.core.infrastructure.ai.engine.invocation.transports.queue import (
    EngineQueueTransport,
)
from democrai.core.infrastructure.database.models import Base, EngineInvocationQueue
from democrai.core.platform.utils.timezone import utc_now_naive
from tests.runtime.fake_redis import FakeRedisStream


def _target(*, objective="chat"):
    return EngineInvocationTarget(selector_type="objective", objective=objective)


def _request(method, payload=None):
    return EngineInvocationRequest(method=method, payload=payload)


class _FakeJobRegistry:
    def get(self, request_id):
        return None

    def remove(self, request_id):
        return None

    def cancel(self, request_id, reason=""):
        return True


class _NodeService:
    """Stand-in for EngineOrchestratorService executing on one node."""

    def __init__(self, node_id, *, unary=None, stream=None):
        self.node_id = node_id
        self._job_registry = _FakeJobRegistry()
        self._unary = unary
        self._stream = stream
        self.executed = []

    def has_running_job(self, request_id):
        return False

    def evict_terminal_job(self, request_id):
        self._job_registry.remove(request_id)

    def cancel_job(self, request_id, reason):
        return self._job_registry.cancel(request_id, reason)

    async def invoke_request(self, request, context):
        return await self._invoke_unary_job(request, context)

    def invoke_stream_request(self, request, context):
        return self._invoke_stream_job(request, context)

    async def _invoke_unary_job(self, request, context):
        self.executed.append(request.request_id)
        if isinstance(self._unary, Exception):
            raise self._unary
        return {"served_by": self.node_id}

    async def _invoke_stream_job(self, request, context):
        self.executed.append(request.request_id)
        for chunk in self._stream or []:
            yield chunk


@pytest.fixture
def cluster(tmp_path, monkeypatch):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'cluster.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    store = EngineInvocationQueueStore(session_factory=session_factory)
    redis = FakeRedisStream()

    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        node_id="node-a",
        logger=None,
    )
    for module in (claim_worker_mod, queue_client_mod, placement_mod):
        monkeypatch.setattr(module, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(
        queue_client_mod,
        "build_request_context_json",
        lambda *, origin, request_id: "{}",
    )

    views = [
        NodeResourcesView(node_id="node-a", has_gpu=True, ram_gb=64.0, vram_gb=24.0),
        NodeResourcesView(node_id="node-b", has_gpu=True, ram_gb=64.0, vram_gb=24.0),
    ]
    monkeypatch.setattr(
        placement_mod, "load_active_node_views", lambda threshold_seconds: views
    )

    def make_node(node_id, *, scores, unary=None, stream=None):
        service = _NodeService(node_id, unary=unary, stream=stream)
        placement = EnginePlacement(node_id=node_id)
        placement._score = lambda row, view: scores.get(view.node_id)
        worker = EngineQueueClaimWorker(
            node_id=node_id,
            service=service,
            store=store,
            response_stream=redis,
            placement=placement,
        )
        worker._keepalive_seconds = 0.5
        worker._predict_target = lambda row: {
            "engine_row_id": 1,
            "model_registry_id": 1,
        }
        worker._engine_capacity_limit = lambda engine_row_id: 4
        return worker, service

    client = EngineQueueTransport(store=store, response_stream=redis)
    client._keepalive_seconds = 0.3
    return SimpleNamespace(
        store=store,
        redis=redis,
        client=client,
        make_node=make_node,
        session_factory=session_factory,
    )


async def _drain(worker):
    await worker._tick()
    if worker._tasks:
        await asyncio.gather(*list(worker._tasks), return_exceptions=True)


async def _run_with_ticks(coro, *workers, timeout=15.0):
    """Run a client call while ticking the workers until it finishes."""
    done = asyncio.Event()

    async def ticks():
        while not done.is_set():
            for worker in workers:
                await _drain(worker)
            await asyncio.sleep(0.05)

    tick_task = asyncio.create_task(ticks())
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    finally:
        done.set()
        # No cancel: a cancel would propagate through _drain's gather to the
        # in-flight worker task, which would record the job as failed.
        await asyncio.wait_for(tick_task, timeout=10)


def test_warm_node_wins_and_serves(cluster):
    # node-b is warm for this selector: higher score everywhere.
    scores = {"node-a": 50, "node-b": 100}
    worker_a, service_a = cluster.make_node("node-a", scores=scores)
    worker_b, service_b = cluster.make_node("node-b", scores=scores)

    async def scenario():
        return await _run_with_ticks(
            cluster.client.invoke(
                _target(objective="chat"),
                _request("generate_completion", {"messages": []}),
            ),
            worker_a,
            worker_b,
        )

    result = asyncio.run(scenario())
    assert result == {"served_by": "node-b"}
    assert service_a.executed == []
    assert len(service_b.executed) == 1


def test_capacity_unavailable_hands_job_to_origin(cluster):
    # node-b scores best but would need a resource swap it cannot confirm.
    scores = {"node-a": 50, "node-b": 100}
    worker_a, service_a = cluster.make_node("node-a", scores=scores)
    worker_b, service_b = cluster.make_node(
        "node-b",
        scores=scores,
        unary=RuntimeError(
            "engine_orchestrator_node_capacity_unavailable:need_confirmation"
        ),
    )

    async def scenario():
        return await _run_with_ticks(
            cluster.client.invoke(
                _target(objective="chat"),
                _request("generate_completion", {}),
            ),
            worker_b,
            worker_a,
        )

    result = asyncio.run(scenario())
    # node-b tried, released with requires_origin_hitl; only origin node-a
    # may claim it afterwards.
    assert result == {"served_by": "node-a"}
    assert len(service_b.executed) == 1
    assert len(service_a.executed) == 1
    state = cluster.store.get_status(service_a.executed[0])
    assert state["status"] == "completed"
    # node-b's claim was given back by the release: only node-a's counts
    assert state["attempts"] == 1


def test_crashed_claimer_unary_recovered_by_peer(cluster):
    scores = {"node-a": 100, "node-b": 100}  # tie: node-a wins tie-break
    worker_a, service_a = cluster.make_node("node-a", scores=scores)

    async def scenario():
        # node-b claims directly (simulated crash: never executes)
        request_id = cluster.store.enqueue(
            request_id="req-crash",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        cluster.store.claim([request_id], owner="node-b", lease_seconds=60)
        # lease expires
        with cluster.session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            row.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
            session.commit()

        reader_entries = []

        async def consume():
            from democrai.core.infrastructure.ai.engine.response.reader import (
                EngineResponseStreamReader,
            )

            reader = EngineResponseStreamReader(
                cluster.redis,
                f"democrai:engine:resp:{request_id}",
                request_id=request_id,
                store=cluster.store,
                keepalive_timeout_seconds=0.3,
                block_ms=100,
            )
            async for entry in reader.entries():
                reader_entries.append(entry)

        consumer = asyncio.create_task(consume())
        await asyncio.sleep(0.1)
        await _drain(worker_a)
        await asyncio.wait_for(consumer, timeout=5)
        return request_id, reader_entries

    request_id, entries = asyncio.run(scenario())
    kinds = [entry.kind for entry in entries]
    assert kinds == ["accepted", "result", "end"]
    assert entries[0].node == "node-a"
    assert entries[0].attempt == 2  # second claim after the crashed one
    state = cluster.store.get_status(request_id)
    assert state["status"] == "completed"


def test_stream_served_cross_node(cluster):
    scores = {"node-a": 10, "node-b": 90}
    worker_a, _service_a = cluster.make_node("node-a", scores=scores)
    worker_b, service_b = cluster.make_node(
        "node-b",
        scores=scores,
        stream=[
            SimpleNamespace(kind="chunk", chunk_json='"ciao "'),
            SimpleNamespace(kind="chunk", chunk_json='"mondo"'),
        ],
    )

    async def scenario():
        async def consume():
            chunks = []
            async for item in cluster.client.invoke_stream(
                _target(objective="chat"),
                _request("generate_stream", {}),
            ):
                chunks.append(item)
            return chunks

        return await _run_with_ticks(consume(), worker_a, worker_b)

    chunks = asyncio.run(scenario())
    assert chunks == ["ciao ", "mondo"]
    assert len(service_b.executed) == 1
