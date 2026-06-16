"""Tests for the third-review fixes: same-node reclaim guard, install-check
age valve, mark_cancelled owner guard, combined lease/cancel round trip,
sequence reset across attempts and the reader failure paths."""

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
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.infrastructure.database.models import (
    Base,
    EngineInvocationQueue,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from tests.runtime.fake_redis import FakeRedisStream


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'r3.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


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
        if callable(self._unary):
            return await self._unary(request, context)
        if isinstance(self._unary, BaseException):
            raise self._unary
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
    with store._session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        return store._snapshot(row)


# ----- same-node reclaim guard ----------------------------------------------


def test_decide_skips_row_with_live_local_job(make_worker, store):
    service = _FakeService(unary=None)
    worker, _redis = make_worker(service)
    worker._predict_target = lambda row: {
        "engine_row_id": 1,
        "engine_id": "",
        "model_registry_id": 1,
    }
    row = {
        "id": "req-live",
        "requires_origin_hitl": False,
        "origin_node_id": "node-a",
        "selector_type": "objective",
    }
    service._job_registry.jobs["req-live"] = SimpleNamespace(done=False)
    assert asyncio.run(worker._decide(dict(row))) == "skip"
    service._job_registry.jobs["req-live"] = SimpleNamespace(done=True)
    assert asyncio.run(worker._decide(dict(row))) == "claim"


# ----- install check guard ----------------------------------------------------


def test_install_check_not_bypassed_past_force_claim_age(make_worker, store):
    service = _FakeService(unary=None)
    worker, _redis = make_worker(service)
    worker._predict_target = lambda row: {
        "engine_row_id": 1,
        "engine_id": "vllm",
        "model_registry_id": 1,
    }
    # vllm registered on another node only
    installed = (frozenset({"vllm"}), frozenset())
    fresh = {
        "id": "x",
        "requires_origin_hitl": False,
        "origin_node_id": "node-a",
        "selector_type": "objective",
        "available_at": utc_now_naive(),
    }
    old = dict(fresh, available_at=utc_now_naive() - timedelta(seconds=60))
    assert (
        asyncio.run(worker._decide(dict(fresh), installed_engines=installed))
        == "skip"
    )
    assert (
        asyncio.run(worker._decide(dict(old), installed_engines=installed))
        == "skip"
    )


# ----- mark_cancelled owner guard ---------------------------------------------


def test_mark_cancelled_owner_guard(store, session_factory):
    row = _enqueue_and_claim(store, owner="node-a")
    request_id = row["id"]
    with session_factory() as session:
        record = session.get(EngineInvocationQueue, request_id)
        record.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
        session.commit()
    store.claim([request_id], owner="node-b", lease_seconds=60)
    # zombie node-a cannot cancel a row node-b now owns
    store.mark_cancelled(request_id, owner="node-a")
    assert store.get_status(request_id)["status"] == "processing"
    store.mark_cancelled(request_id, owner="node-b")
    assert store.get_status(request_id)["status"] == "cancelled"


# ----- combined renew+cancel round trip ---------------------------------------


def test_renew_lease_and_check_cancel(store):
    row = _enqueue_and_claim(store, owner="node-b")
    request_id = row["id"]
    renewed, cancel_requested = store.renew_lease_and_check_cancel(
        request_id, owner="node-b", lease_seconds=60
    )
    assert (renewed, cancel_requested) == (True, False)
    store.request_cancel(request_id)
    renewed, cancel_requested = store.renew_lease_and_check_cancel(
        request_id, owner="node-b", lease_seconds=60
    )
    assert (renewed, cancel_requested) == (True, True)
    renewed, _ = store.renew_lease_and_check_cancel(
        request_id, owner="node-other", lease_seconds=60
    )
    assert renewed is False


# ----- lease-lost zombie stays silent ------------------------------------------


def test_lease_lost_zombie_exits_silently(make_worker, store, session_factory):
    async def blocked_until_cancelled(request, context):
        # mimics _await_job_result: polls the fake context until cancelled
        while not context.cancelled():
            await asyncio.sleep(0.05)
        raise asyncio.CancelledError()

    service = _FakeService(unary=blocked_until_cancelled)
    worker, redis = make_worker(service)
    worker._lease_seconds = 1  # ancillary interval floors at 0.5s
    row = _enqueue_and_claim(store, owner="node-b")
    request_id = row["id"]

    async def scenario():
        task = asyncio.create_task(
            worker._execute_row(dict(row), engine_row_id=0)
        )
        await asyncio.sleep(0.2)
        # another node takes the row over
        with session_factory() as session:
            record = session.get(EngineInvocationQueue, request_id)
            record.lease_expires_at = utc_now_naive() - timedelta(seconds=1)
            session.commit()
        store.claim([request_id], owner="node-c", lease_seconds=60)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(scenario())
    # the zombie must not have touched row state owned by node-c
    state = store.get_status(request_id)
    assert state["status"] == "processing"
    assert state["lease_owner"] == "node-c"
    # and must not have written anything past its accepted entry
    kinds = [
        fields.get("kind")
        for _id, fields in redis.streams.get(row["response_stream_key"], [])
    ]
    assert kinds == ["accepted"]


# ----- reader: seq reset across attempts and failure paths ---------------------


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


def test_sequence_resets_on_new_attempt(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-reset",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        key = f"democrai:engine:resp:{request_id}"
        reader = _reader(redis, store, request_id)
        first = EngineResponseStreamWriter(redis, key, node_id="node-b")
        await first.chunk("a")  # seq 0
        await first.chunk("b")  # seq 1
        await first.retry(attempt=1, error="quota")
        second = EngineResponseStreamWriter(redis, key, node_id="node-c")
        await second.accepted(attempt=2)
        await second.chunk("a2")  # seq restarts at 0: must NOT trip the gap
        await second.chunk("b2")
        await second.end()
        kinds = [entry.kind async for entry in reader.entries()]
        assert kinds == ["chunk", "chunk", "retry", "accepted", "chunk", "chunk", "end"]

    asyncio.run(scenario())


def test_reader_wraps_redis_failures(store):
    class _BrokenSubscription:
        async def get(self):
            raise ConnectionError("stream down")

    class _BrokenStream(EngineResponseStream):
        def subscribe(self, channel_id):
            return _BrokenSubscription()

        def unsubscribe(self, channel_id, queue):
            return None

        async def publish(self, channel_id, data):
            return None

    async def scenario():
        request_id = store.enqueue(
            request_id="req-redis-down",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        reader = _reader(_BrokenStream(), store, request_id)
        with pytest.raises(RuntimeError, match="response_stream_unavailable"):
            async for _entry in reader.entries():
                pass

    asyncio.run(scenario())


def test_reader_total_timeout(store):
    async def scenario():
        redis = FakeRedisStream()
        request_id = store.enqueue(
            request_id="req-timeout",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )
        store.claim([request_id], owner="node-b", lease_seconds=60)
        reader = _reader(
            redis,
            store,
            request_id,
            keepalive_timeout_seconds=30,
            total_timeout_seconds=0.3,
        )
        with pytest.raises(TimeoutError):
            async for _entry in reader.entries():
                pass

    asyncio.run(scenario())


def test_reader_missing_row_raises(store):
    async def scenario():
        redis = FakeRedisStream()
        reader = _reader(redis, store, "req-ghost", keepalive_timeout_seconds=0.2)
        with pytest.raises(RuntimeError, match="request_row_missing"):
            async for _entry in reader.entries():
                pass

    asyncio.run(scenario())
