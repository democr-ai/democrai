from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

import democrai.core.infrastructure.ai.engine.invocation.queue.claim_worker as claim_worker_mod
from democrai.core.infrastructure.ai.engine.invocation.queue.claim_worker import (
    EngineQueueClaimWorker,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.database.models import Base, EngineInvocationQueue
from tests.runtime.fake_redis import FakeRedisStream


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'worker.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def store(session_factory):
    return EngineInvocationQueueStore(session_factory=session_factory)


class _FakeJobRegistry:
    def __init__(self):
        self.cancelled = []
        self.jobs = {}

    def get(self, request_id):
        return self.jobs.get(request_id)

    def remove(self, request_id):
        return self.jobs.pop(request_id, None)

    def cancel(self, request_id, reason=""):
        self.cancelled.append((request_id, reason))
        return True


class _FakeService:
    def __init__(self, *, unary=None, stream=None):
        self._job_registry = _FakeJobRegistry()
        self._unary = unary
        self._stream = stream

    def active_job(self, request_id):
        return self._job_registry.get(request_id)

    def has_running_job(self, request_id):
        job = self.active_job(request_id)
        return job is not None and not getattr(job, "done", False)

    def evict_terminal_job(self, request_id):
        job = self.active_job(request_id)
        if job is not None and getattr(job, "done", False):
            self._job_registry.remove(request_id)

    async def invoke_request(self, request, context):
        return await self._invoke_unary_job(request, context)

    def invoke_stream_request(self, request, context):
        return self._invoke_stream_job(request, context)

    async def _invoke_unary_job(self, request, context):
        if isinstance(self._unary, Exception):
            raise self._unary
        if callable(self._unary):
            result = self._unary(request, context)
            if hasattr(result, "__await__"):
                return await result
            return result
        return self._unary

    async def _invoke_stream_job(self, request, context):
        if isinstance(self._stream, Exception):
            raise self._stream
        for chunk in self._stream or []:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


@pytest.fixture
def make_worker(store, monkeypatch):
    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        node_id="node-b",
        logger=None,
    )
    monkeypatch.setattr(claim_worker_mod, "app_ctx", lambda: fake_ctx)

    def _factory(service):
        redis = FakeRedisStream()
        worker = EngineQueueClaimWorker(
            node_id="node-b",
            service=service,
            store=store,
            response_stream=redis,
        )
        worker._keepalive_seconds = 0.5
        return worker, redis

    return _factory


def _enqueue_and_claim(store, **overrides):
    values = {
        "selector_type": "objective",
        "objective": "chat",
        "method": "generate_completion",
        "origin_node_id": "node-a",
    }
    values.update(overrides)
    request_id = store.enqueue(**values)
    return store.claim([request_id], owner="node-b", lease_seconds=60)[0]


def _entries(redis, key):
    return [
        {**{"kind": fields.get("kind")}, **fields}
        for _id, fields in redis.streams.get(key, [])
    ]


def test_unary_success_completes_row(make_worker, store):
    worker, redis = make_worker(_FakeService(unary={"text": "ok"}))
    row = _enqueue_and_claim(store)
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "completed"
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["accepted", "result", "end"]


def test_objective_execution_uses_claim_predicted_model_registry_id(make_worker, store):
    captured = {}

    def _unary(request, context):
        captured["selector_type"] = request.selector_type
        captured["model_registry_id"] = request.model_registry_id
        return {"ok": True}

    worker, _redis = make_worker(_FakeService(unary=_unary))
    row = _enqueue_and_claim(store, selector_type="objective", objective="chat")
    asyncio.run(
        worker._execute_row(
            dict(row),
            engine_row_id=7,
            target={"engine_row_id": 7, "engine_id": "demo", "model_registry_id": 42},
        )
    )

    assert captured == {
        "selector_type": "model_registry_id",
        "model_registry_id": 42,
    }


def test_unary_retriable_failure_requeues(make_worker, store):
    worker, redis = make_worker(
        _FakeService(unary=RuntimeError("HTTP 429 too many requests"))
    )
    row = _enqueue_and_claim(store)
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    state = store.get_status(row["id"])
    assert state["status"] == "failed"
    assert state["attempts"] == 1
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["accepted", "retry"]


def test_unary_terminal_failure_dead_letters(make_worker, store):
    worker, redis = make_worker(
        _FakeService(unary=RuntimeError("HTTP 401 unauthorized"))
    )
    row = _enqueue_and_claim(store)
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "dead_letter"
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["accepted", "error"]


def test_capacity_unavailable_releases_for_origin(make_worker, store, session_factory):
    worker, redis = make_worker(
        _FakeService(
            unary=RuntimeError(
                "engine_orchestrator_node_capacity_unavailable:status=need_confirmation"
            )
        )
    )
    row = _enqueue_and_claim(store)
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    state = store.get_status(row["id"])
    assert state["status"] == "pending"
    assert state["attempts"] == 0
    with session_factory() as session:
        db_row = session.get(EngineInvocationQueue, row["id"])
        assert db_row.requires_origin_hitl is True
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["accepted"]


def test_stream_success_marks_first_chunk_and_completes(make_worker, store, session_factory):
    chunks = [
        SimpleNamespace(kind="chunk", chunk_json='"hello"'),
        SimpleNamespace(kind="message", chunk_json='{"type":"x"}'),
        SimpleNamespace(kind="chunk", chunk_json='"world"'),
    ]
    worker, redis = make_worker(_FakeService(stream=chunks))
    row = _enqueue_and_claim(store, response_mode="stream", method="generate_stream")
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "completed"
    with session_factory() as session:
        assert session.get(EngineInvocationQueue, row["id"]).first_chunk_at is not None
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["accepted", "chunk", "message", "chunk", "end"]


def test_stream_failure_after_first_chunk_is_terminal(make_worker, store):
    chunks = [
        SimpleNamespace(kind="chunk", chunk_json='"partial"'),
        RuntimeError("connection reset"),  # retriable class, but tokens are out
    ]
    worker, redis = make_worker(_FakeService(stream=chunks))
    row = _enqueue_and_claim(store, response_mode="stream", method="generate_stream")
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "dead_letter"
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["accepted", "chunk", "error"]


def test_stream_reclaim_with_first_chunk_fails_terminal(make_worker, store):
    worker, redis = make_worker(_FakeService(stream=[]))
    row = _enqueue_and_claim(store, response_mode="stream", method="generate_stream")
    store.mark_first_chunk(row["id"])
    row = dict(row)
    row["first_chunk_at"] = "set"
    asyncio.run(worker._execute_row(row, engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "dead_letter"
    kinds = [e["kind"] for e in _entries(redis, row["response_stream_key"])]
    assert kinds == ["error"]


def test_precancelled_row_goes_cancelled(make_worker, store):
    worker, redis = make_worker(_FakeService(unary={"text": "never"}))
    row = _enqueue_and_claim(store)
    store.request_cancel(row["id"])
    row = dict(row)
    row["cancel_requested"] = True
    asyncio.run(worker._execute_row(row, engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "cancelled"


def test_decide_skips_origin_hitl_rows_on_other_nodes(make_worker, store):
    worker, _redis = make_worker(_FakeService(unary=None))
    worker._predict_target = lambda row: {"engine_row_id": 1, "model_registry_id": 1}
    row_other = {
        "id": "x",
        "requires_origin_hitl": True,
        "origin_node_id": "node-a",
        "selector_type": "objective",
    }
    row_mine = dict(row_other, origin_node_id="node-b")
    assert asyncio.run(worker._decide(dict(row_other))) == "skip"
    assert asyncio.run(worker._decide(dict(row_mine))) == "claim"


def test_tick_scans_beyond_first_page_for_claimable_row(make_worker, store):
    worker, _redis = make_worker(_FakeService(unary={"ok": True}))
    target_id = "req-17"
    for index in range(20):
        store.enqueue(
            request_id=f"req-{index}",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )

    async def _decide(row, **_kwargs):
        return "claim" if row["id"] == target_id else "skip"

    async def scenario():
        worker._decide = _decide
        await worker._tick()
        if worker._tasks:
            await asyncio.gather(*list(worker._tasks))

    asyncio.run(scenario())

    assert store.get_status(target_id)["status"] == "completed"


def test_tick_reserves_engine_capacity_within_page(make_worker, store, session_factory):
    release = asyncio.Event()

    async def _unary(_request, _context):
        await release.wait()
        return {"ok": True}

    worker, _redis = make_worker(_FakeService(unary=_unary))
    worker._predict_target = lambda row: {
        "engine_row_id": 7,
        "engine_id": "",
        "model_registry_id": 1,
    }
    worker._engine_capacity_limit = lambda engine_row_id: 1
    for index in range(3):
        store.enqueue(
            request_id=f"req-capacity-{index}",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )

    async def scenario():
        await worker._tick()
        await asyncio.sleep(0.05)
        with session_factory() as session:
            statuses = [
                row.status
                for row in (
                    session.query(EngineInvocationQueue)
                    .order_by(EngineInvocationQueue.id.asc())
                    .all()
                )
            ]
        assert statuses.count("processing") == 1
        assert statuses.count("pending") == 2
        release.set()
        if worker._tasks:
            await asyncio.gather(*list(worker._tasks))

    asyncio.run(scenario())


def test_tick_requests_immediate_drain_after_full_claim_page(make_worker, store):
    worker, _redis = make_worker(_FakeService(unary={"ok": True}))
    worker._predict_target = lambda row: {
        "engine_row_id": 0,
        "engine_id": "",
        "model_registry_id": 1,
    }
    for index in range(16):
        store.enqueue(
            request_id=f"req-drain-{index}",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )

    async def scenario():
        drain_more = await worker._tick()
        if worker._tasks:
            await asyncio.gather(*list(worker._tasks))
        return drain_more

    assert asyncio.run(scenario()) is True


def test_decide_skips_when_engine_saturated(make_worker, store):
    worker, _redis = make_worker(_FakeService(unary=None))
    worker._predict_target = lambda row: {"engine_row_id": 7, "model_registry_id": 1}
    worker._engine_capacity_limit = lambda engine_row_id: 1
    row = {
        "id": "x",
        "requires_origin_hitl": False,
        "origin_node_id": "node-a",
        "selector_type": "objective",
    }
    assert asyncio.run(worker._decide(dict(row))) == "claim"
    worker._track_engine(7, 1)
    assert asyncio.run(worker._decide(dict(row))) == "skip"
    worker._track_engine(7, -1)
    assert asyncio.run(worker._decide(dict(row))) == "claim"


def test_decide_claims_unresolvable_selector_for_deterministic_failure(
    make_worker, store
):
    worker, _redis = make_worker(_FakeService(unary=None))

    def _boom(row):
        raise RuntimeError("model_registry_row_not_found:99")

    worker._predict_target = _boom
    row = {
        "id": "x",
        "requires_origin_hitl": False,
        "origin_node_id": "node-a",
        "selector_type": "model_registry_id",
    }
    assert asyncio.run(worker._decide(dict(row))) == "claim"
