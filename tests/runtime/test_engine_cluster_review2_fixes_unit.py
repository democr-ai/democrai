"""Tests for the second-review fixes: lease-owner guards, stale terminal job
eviction, user-cancel semantics, chunk sequence gap detection, terminal grace
window and the engine install claim filter."""

from __future__ import annotations

import asyncio
from datetime import timedelta
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
from democrai.core.infrastructure.ai.engine.response.reader import (
    EngineResponseStreamReader,
)
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.infrastructure.database.models import (
    Base,
    EngineInvocationQueue,
    EngineNodeInstallRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from tests.runtime.fake_redis import FakeRedisStream


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'fixes.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def store(session_factory):
    return EngineInvocationQueueStore(session_factory=session_factory)


def _enqueue_and_claim(store, *, owner="node-b", **overrides):
    values = {
        "selector_type": "objective",
        "objective": "chat",
        "method": "generate_completion",
        "origin_node_id": "node-a",
    }
    values.update(overrides)
    request_id = store.enqueue(**values)
    store.claim([request_id], owner=owner, lease_seconds=60)
    return request_id


def _seed_active_node(session, node_id: str) -> None:
    now = utc_now_naive()
    session.add(
        RuntimeNodeRegistry(
            node_id=node_id,
            hostname=node_id,
            status="active",
            orchestrator_last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )


# ----- owner guards (fix 4) -------------------------------------------------


def test_stale_owner_cannot_complete(store, session_factory):
    request_id = _enqueue_and_claim(store, owner="node-a")
    # node-a's lease expires; node-b reclaims and completes
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()
    store.claim([request_id], owner="node-b", lease_seconds=60)
    store.complete(request_id, owner="node-b")
    # the zombie's late complete/fail must not overwrite
    store.complete(request_id, owner="node-a")
    assert store.get_status(request_id)["status"] == "completed"
    assert (
        store.fail(
            request_id,
            owner="node-a",
            error="late",
            retriable=True,
            max_attempts=3,
        )
        == "stale"
    )


def test_stale_owner_cannot_fail_or_release(store, session_factory):
    request_id = _enqueue_and_claim(store, owner="node-a")
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()
    store.claim([request_id], owner="node-b", lease_seconds=60)
    assert (
        store.fail(
            request_id, owner="node-a", error="late", retriable=True, max_attempts=3
        )
        == "stale"
    )
    store.release(request_id, owner="node-a", defer_seconds=5)
    state = store.get_status(request_id)
    assert state["status"] == "processing"
    assert state["lease_owner"] == "node-b"


def test_stale_owner_cannot_mark_first_chunk(store, session_factory):
    request_id = _enqueue_and_claim(store, owner="node-a", response_mode="stream")
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()
    store.claim([request_id], owner="node-b", lease_seconds=60)
    store.mark_first_chunk(request_id, owner="node-a")
    with session_factory() as session:
        assert session.get(EngineInvocationQueue, request_id).first_chunk_at is None
    store.mark_first_chunk(request_id, owner="node-b")
    with session_factory() as session:
        assert session.get(EngineInvocationQueue, request_id).first_chunk_at is not None


def test_admin_fail_settles_idle_rows_but_not_processing(store):
    # maintenance-style call (owner=None) settles pending/failed rows...
    request_id = _enqueue_and_claim(store, owner="node-a")
    store.release(request_id, owner="node-a", defer_seconds=0)
    assert (
        store.fail(
            request_id, error="orphaned", retriable=False, max_attempts=1
        )
        == "dead_letter"
    )
    # ...but must not kill a row a worker claimed meanwhile
    other = _enqueue_and_claim(store, owner="node-a")
    assert (
        store.fail(other, error="orphaned", retriable=False, max_attempts=1)
        == "stale"
    )
    assert store.get_status(other)["status"] == "processing"


def test_renew_lease_false_after_reclaim(store, session_factory):
    request_id = _enqueue_and_claim(store, owner="node-a")
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()
    store.claim([request_id], owner="node-b", lease_seconds=60)
    assert store.renew_lease(request_id, owner="node-a", lease_seconds=60) is False
    assert store.renew_lease(request_id, owner="node-b", lease_seconds=60) is True


# ----- claim worker behavior (fixes 1, 2, 5) --------------------------------


class _FakeJobRegistry:
    def __init__(self):
        self.jobs = {}
        self.removed = []
        self.cancelled = []

    def get(self, request_id):
        return self.jobs.get(request_id)

    def remove(self, request_id):
        self.removed.append(request_id)
        return self.jobs.pop(request_id, None)

    def cancel(self, request_id, reason=""):
        self.cancelled.append((request_id, reason))
        return True


class _FakeService:
    def __init__(self, *, unary=None):
        self._job_registry = _FakeJobRegistry()
        self._unary = unary

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
        if isinstance(self._unary, BaseException):
            raise self._unary
        if callable(self._unary):
            result = self._unary(request, context)
            if hasattr(result, "__await__"):
                return await result
            return result
        return self._unary

    async def _invoke_stream_job(self, request, context):
        return
        yield  # pragma: no cover


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


def _claimed_row(store, **overrides):
    request_id = _enqueue_and_claim(store, owner="node-b", **overrides)
    # rebuild the snapshot the worker receives from claim()
    with store._session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        return store._snapshot(row)


def test_stale_terminal_job_evicted_before_run(make_worker, store):
    service = _FakeService(unary={"text": "fresh"})
    worker, _redis = make_worker(service)
    row = _claimed_row(store)
    service._job_registry.jobs[row["id"]] = SimpleNamespace(done=True)
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert service._job_registry.removed == [row["id"]]
    assert store.get_status(row["id"])["status"] == "completed"


def test_live_job_not_evicted(make_worker, store):
    service = _FakeService(unary={"text": "fresh"})
    worker, _redis = make_worker(service)
    row = _claimed_row(store)
    service._job_registry.jobs[row["id"]] = SimpleNamespace(done=False)
    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert service._job_registry.removed == []


def test_user_cancel_during_execution_marks_cancelled(make_worker, store):
    service = _FakeService(unary=asyncio.CancelledError())
    worker, redis = make_worker(service)
    row = _claimed_row(store)
    # the cancel arrives while the job runs (flag set on the row)
    store.request_cancel(row["id"])

    asyncio.run(worker._execute_row(dict(row), engine_row_id=0))
    assert store.get_status(row["id"])["status"] == "cancelled"
    kinds = [
        fields.get("kind")
        for _id, fields in redis.streams.get(row["response_stream_key"], [])
    ]
    assert kinds == ["accepted", "error"]


def test_shutdown_cancel_still_requeues(make_worker, store):
    service = _FakeService(unary=asyncio.CancelledError())
    worker, redis = make_worker(service)
    row = _claimed_row(store)

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await worker._execute_row(dict(row), engine_row_id=0)

    asyncio.run(scenario())
    assert store.get_status(row["id"])["status"] == "failed"


def test_decide_skips_engine_not_installed_here(make_worker, store, session_factory):
    worker, _redis = make_worker(_FakeService(unary=None))
    worker._predict_target = lambda row: {
        "engine_row_id": 1,
        "engine_id": "vllm",
        "model_registry_id": 1,
    }
    with session_factory() as session:
        _seed_active_node(session, "node-other")
        session.add(
            EngineNodeInstallRegistry(
                engine_id="vllm", node_id="node-other", status="installed"
            )
        )
        session.commit()
    monkey_session_factory = session_factory
    original = claim_worker_mod.SessionLocal
    claim_worker_mod.SessionLocal = monkey_session_factory
    try:
        row = {
            "id": "x",
            "requires_origin_hitl": False,
            "origin_node_id": "node-a",
            "selector_type": "objective",
        }
        assert asyncio.run(worker._decide(dict(row))) == "skip"
        with session_factory() as session:
            session.add(
                EngineNodeInstallRegistry(
                    engine_id="vllm", node_id="node-b", status="installed"
                )
            )
            session.commit()
        assert asyncio.run(worker._decide(dict(row))) == "claim"
    finally:
        claim_worker_mod.SessionLocal = original


def test_decide_fails_when_engine_installed_only_on_inactive_nodes(
    make_worker, store, session_factory
):
    worker, _redis = make_worker(_FakeService(unary=None))
    worker._predict_target = lambda row: {
        "engine_row_id": 1,
        "engine_id": "vllm",
        "model_registry_id": 1,
    }
    with session_factory() as session:
        session.add(
            EngineNodeInstallRegistry(
                engine_id="vllm", node_id="node-offline", status="installed"
            )
        )
        session.commit()
    original = claim_worker_mod.SessionLocal
    claim_worker_mod.SessionLocal = session_factory
    try:
        row = {
            "id": "x",
            "requires_origin_hitl": False,
            "origin_node_id": "node-a",
            "selector_type": "objective",
        }
        assert asyncio.run(worker._decide(dict(row))) == "fail_missing_engine_install"
    finally:
        claim_worker_mod.SessionLocal = original


def test_decide_fails_when_engine_not_installed_anywhere(
    make_worker, store, session_factory
):
    worker, _redis = make_worker(_FakeService(unary=None))
    worker._predict_target = lambda row: {
        "engine_row_id": 1,
        "engine_id": "llamacpp",
        "model_registry_id": 1,
    }
    original = claim_worker_mod.SessionLocal
    claim_worker_mod.SessionLocal = session_factory
    try:
        row = {
            "id": "x",
            "requires_origin_hitl": False,
            "origin_node_id": "node-a",
            "selector_type": "objective",
        }
        assert asyncio.run(worker._decide(dict(row))) == "fail_missing_engine_install"
    finally:
        claim_worker_mod.SessionLocal = original


def test_tick_paginates_past_rows_not_claimable_on_this_node(
    make_worker, store, session_factory, monkeypatch
):
    worker, _redis = make_worker(_FakeService(unary={"ok": True}))
    monkeypatch.setattr(claim_worker_mod, "SessionLocal", session_factory)
    with session_factory() as session:
        _seed_active_node(session, "node-other")
        session.add(
            EngineNodeInstallRegistry(
                engine_id="remote-engine",
                node_id="node-other",
                status="installed",
            )
        )
        session.add(
            EngineNodeInstallRegistry(
                engine_id="local-engine",
                node_id="node-b",
                status="installed",
            )
        )
        session.commit()

    def _target(row):
        request_id = str(row["id"])
        if request_id == "local-claimable":
            return {
                "engine_row_id": 2,
                "engine_id": "local-engine",
                "model_registry_id": 1,
            }
        return {
            "engine_row_id": 1,
            "engine_id": "remote-engine",
            "model_registry_id": 1,
        }

    worker._predict_target = _target
    for index in range(16):
        store.enqueue(
            request_id=f"remote-{index:02d}",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
    store.enqueue(
        request_id="local-claimable",
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin_node_id="node-a",
    )

    async def scenario():
        await worker._tick()
        await asyncio.gather(*list(worker._tasks), return_exceptions=True)

    asyncio.run(scenario())

    assert store.get_status("local-claimable")["status"] == "completed"
    assert store.get_status("remote-00")["status"] == "pending"


def test_unclaimable_fail_does_not_emit_error_when_row_was_claimed(
    make_worker, store
):
    worker, redis = make_worker(_FakeService(unary=None))
    request_id = store.enqueue(
        request_id="req-race",
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin_node_id="node-a",
    )
    with store._session_factory() as session:
        row = store._snapshot(session.get(EngineInvocationQueue, request_id))
    store.claim([request_id], owner="node-other", lease_seconds=60)

    asyncio.run(worker._fail_unclaimable_row(row, "engine_not_installed"))

    assert store.get_status(request_id)["status"] == "processing"
    assert redis.streams.get(row["response_stream_key"], []) == []


# ----- stream protocol hardening (fixes 6, 7) -------------------------------


def _writer(redis, key):
    return EngineResponseStreamWriter(redis, key, node_id="node-b")


def _reader(redis, store, request_id, **kwargs):
    return EngineResponseStreamReader(
        redis,
        f"democrai:engine:resp:{request_id}",
        request_id=request_id,
        store=store,
        keepalive_timeout_seconds=kwargs.pop("keepalive_timeout_seconds", 0.3),
        block_ms=kwargs.pop("block_ms", 100),
        **kwargs,
    )


def test_chunk_sequence_gap_raises(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-gap",
            selector_type="objective",
            objective="chat",
            method="generate_stream",
            response_mode="stream",
            origin_node_id="node-a",
        )
        key = f"democrai:engine:resp:{request_id}"
        reader = _reader(redis, store, request_id)
        await redis.publish(key, {"kind": "chunk", "data": '"a"', "seq": "0", "node": "b"})
        # seq 1 lost to MAXLEN trimming
        await redis.publish(key, {"kind": "chunk", "data": '"c"', "seq": "2", "node": "b"})
        with pytest.raises(RuntimeError, match="response_stream_gap"):
            async for _entry in reader.entries():
                pass

    asyncio.run(scenario())


def test_chunk_sequence_missing_prefix_raises(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-prefix-gap",
            selector_type="objective",
            objective="chat",
            method="generate_stream",
            response_mode="stream",
            origin_node_id="node-a",
        )
        key = f"democrai:engine:resp:{request_id}"
        reader = _reader(redis, store, request_id)
        await redis.publish(key, {"kind": "accepted", "attempt": "1", "node": "b"})
        await redis.publish(
            key,
            {"kind": "chunk", "data": '"late"', "seq": "3", "node": "b"},
        )
        with pytest.raises(RuntimeError, match="response_stream_gap"):
            async for _entry in reader.entries():
                pass

    asyncio.run(scenario())


def test_chunk_sequence_continuous_passes(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-seq",
            selector_type="objective",
            objective="chat",
            method="generate_stream",
            response_mode="stream",
            origin_node_id="node-a",
        )
        reader = _reader(redis, store, request_id)
        writer = _writer(redis, f"democrai:engine:resp:{request_id}")
        await writer.chunk("a")
        await writer.chunk("b")
        await writer.end()
        kinds = [entry.kind async for entry in reader.entries()]
        assert kinds == ["chunk", "chunk", "end"]

    asyncio.run(scenario())


def test_terminal_grace_delivers_late_error_entry(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-grace",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        store.claim([request_id], owner="node-b", lease_seconds=60)
        # DB settles terminal BEFORE the stream entry lands
        store.fail(
            request_id,
            owner="node-b",
            error="kaput",
            retriable=False,
            max_attempts=3,
        )

        async def late_writer():
            await asyncio.sleep(0.6)
            await _writer(redis, f"democrai:engine:resp:{request_id}").error("kaput")

        producer = asyncio.create_task(late_writer())
        reader = _reader(redis, store, request_id, keepalive_timeout_seconds=0.2)
        entries = [entry async for entry in reader.entries()]
        await producer
        assert entries[-1].kind == "error"

    asyncio.run(scenario())


def test_terminal_without_any_entry_raises_after_grace(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-dead2",
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
        with pytest.raises(RuntimeError, match="terminated_without_end"):
            async for _entry in reader.entries():
                pass

    asyncio.run(scenario())
