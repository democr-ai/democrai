from __future__ import annotations

from datetime import timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from democrai.core.infrastructure.ai.engine.invocation.queue.errors import (
    EngineInvocationError,
    classify_error_retryable,
    error_retry_after_seconds,
    retry_delay_seconds,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.database.models import Base, EngineInvocationQueue
from democrai.core.platform.utils.timezone import utc_now_naive


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


@pytest.fixture
def store(session_factory):
    return EngineInvocationQueueStore(session_factory=session_factory)


def _enqueue(store, **overrides):
    values = {
        "selector_type": "objective",
        "objective": "chat",
        "method": "generate_completion",
        "origin_node_id": "node-a",
    }
    values.update(overrides)
    return store.enqueue(**values)


def test_enqueue_idempotent_by_request_id(store):
    request_id = _enqueue(store, request_id="req-1")
    assert request_id == "req-1"
    assert _enqueue(store, request_id="req-1", method="other") == "req-1"
    rows = store.peek_claimable()
    assert len(rows) == 1
    assert rows[0]["method"] == "generate_completion"
    assert rows[0]["response_stream_key"] == "democrai:engine:resp:req-1"


def test_claim_marks_processing_and_counts_attempt(store):
    request_id = _enqueue(store)
    claimed = store.claim([request_id], owner="node-b", lease_seconds=60)
    assert len(claimed) == 1
    assert claimed[0]["status"] == "processing"
    assert claimed[0]["attempts"] == 1
    assert claimed[0]["lease_owner"] == "node-b"
    # already claimed: not claimable again while lease holds
    assert store.claim([request_id], owner="node-c", lease_seconds=60) == []
    assert store.peek_claimable() == []


def test_expired_processing_lease_is_reclaimable(store, session_factory):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.lease_expires_at = utc_now_naive() - timedelta(seconds=5)
        session.commit()
    rows = store.peek_claimable()
    assert [item["id"] for item in rows] == [request_id]
    reclaimed = store.claim([request_id], owner="node-c", lease_seconds=60)
    assert reclaimed[0]["attempts"] == 2
    assert reclaimed[0]["lease_owner"] == "node-c"


def test_priority_and_fifo_ordering(store):
    low = _enqueue(store, priority=0)
    high = _enqueue(store, priority=5)
    low2 = _enqueue(store, priority=0)
    ordered = [row["id"] for row in store.peek_claimable()]
    assert ordered == [high, low, low2]


def test_fail_retriable_backoff_then_dead_letter(store, session_factory):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    status = store.fail(
        request_id, owner="node-b", error="quota", retriable=True, max_attempts=3
    )
    assert status == "failed"
    state = store.get_status(request_id)
    assert state["attempts"] == 1
    # backoff: not claimable right now
    assert store.peek_claimable() == []
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        assert row.available_at > utc_now_naive()
        row.available_at = utc_now_naive()
        session.commit()

    store.claim([request_id], owner="node-b", lease_seconds=60)
    store.fail(request_id, owner="node-b", error="quota", retriable=True, max_attempts=3)
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.available_at = utc_now_naive()
        session.commit()
    store.claim([request_id], owner="node-b", lease_seconds=60)
    status = store.fail(
        request_id, owner="node-b", error="quota", retriable=True, max_attempts=3
    )
    assert status == "dead_letter"
    assert store.peek_claimable() == []


def test_fail_non_retriable_dead_letters_immediately(store):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    status = store.fail(
        request_id, owner="node-b", error="invalid_request", retriable=False, max_attempts=3
    )
    assert status == "dead_letter"


def test_release_gives_back_attempt_and_defers(store, session_factory):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    store.release(
        request_id,
        defer_seconds=30,
        reason="needs origin hitl",
        requires_origin_hitl=True,
    )
    state = store.get_status(request_id)
    assert state["status"] == "pending"
    assert state["attempts"] == 0
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        assert row.requires_origin_hitl is True
        assert row.available_at > utc_now_naive()


def test_request_cancel_pending_goes_terminal(store):
    request_id = _enqueue(store)
    assert store.request_cancel(request_id) == "cancelled"
    assert store.get_status(request_id)["status"] == "cancelled"
    assert store.request_cancel("missing") == "missing"


def test_request_cancel_processing_sets_flag(store):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    assert store.request_cancel(request_id) == "requested"
    assert store.cancel_requested(request_id) is True
    assert store.get_status(request_id)["status"] == "processing"


def test_renew_lease_only_for_owner(store):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    assert store.renew_lease(request_id, owner="node-b", lease_seconds=60) is True
    assert store.renew_lease(request_id, owner="node-c", lease_seconds=60) is False


def test_mark_first_chunk_is_sticky(store, session_factory):
    request_id = _enqueue(store, response_mode="stream")
    store.mark_first_chunk(request_id)
    with session_factory() as session:
        first = session.get(EngineInvocationQueue, request_id).first_chunk_at
    store.mark_first_chunk(request_id)
    with session_factory() as session:
        assert session.get(EngineInvocationQueue, request_id).first_chunk_at == first


def test_purge_terminal(store, session_factory):
    request_id = _enqueue(store)
    store.claim([request_id], owner="node-b", lease_seconds=60)
    store.complete(request_id)
    assert store.purge_terminal(retention_seconds=3600) == 0
    with session_factory() as session:
        row = session.get(EngineInvocationQueue, request_id)
        row.updated_at = utc_now_naive() - timedelta(seconds=7200)
        session.commit()
    assert store.purge_terminal(retention_seconds=3600) == 1


def test_error_classification():
    assert classify_error_retryable("HTTP 429 too many requests") is True
    assert classify_error_retryable("quota exceeded for project") is True
    assert classify_error_retryable("upstream 503 service unavailable") is True
    assert classify_error_retryable("connection reset by peer") is True
    assert classify_error_retryable("HTTP 401 unauthorized") is False
    assert classify_error_retryable("invalid_request: bad payload") is False
    assert classify_error_retryable("context_length exceeded") is False
    assert classify_error_retryable("something opaque happened") is None
    assert (
        classify_error_retryable(
            EngineInvocationError("custom", retryable=False)
        )
        is False
    )
    assert (
        classify_error_retryable(EngineInvocationError("custom", retryable=True))
        is True
    )


def test_retry_after_and_backoff():
    err = EngineInvocationError("429", retryable=True, retry_after_seconds=42)
    assert error_retry_after_seconds(err) == 42
    assert error_retry_after_seconds("rate limited, Retry-After: 17") == 17.0
    assert error_retry_after_seconds("plain error") is None
    assert retry_delay_seconds(1) == 2.0
    assert retry_delay_seconds(10) == 300.0
    assert retry_delay_seconds(1, retry_after=42) == 42.0
