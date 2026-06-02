from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace


def test_outbox_claim_complete_and_fail_paths(monkeypatch):
    mod = __import__(
        "democrai.core.application.knowledge.repository_helper.outbox",
        fromlist=["dummy"],
    )
    monkeypatch.setattr(mod, "utc_now_naive", lambda: datetime(2026, 1, 1, 12, 0, 0))

    class _Query:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_a, **_k):
            return self

        def order_by(self, *_a, **_k):
            return self

        def limit(self, *_a, **_k):
            return self

        def all(self):
            return self.rows

    class _Session:
        def __init__(self, rows=None, by_id=None):
            self.rows = rows or []
            self.by_id = by_id or {}
            self.commits = 0
            self.attached = False

        def query(self, *_a, **_k):
            return _Query(self.rows)

        def get(self, _model, key):
            return self.by_id.get(key)

        def commit(self):
            self.commits += 1

    class _SessionFactory:
        def __init__(self, session):
            self.session = session

        def __call__(self):
            return self

        def __enter__(self):
            return self.session

        def __exit__(self, *_a):
            return False

    row_pending = SimpleNamespace(
        id="j1",
        topic="knowledge.vector_upsert",
        aggregate_type="source",
        aggregate_id="s1",
        aggregate_version=1,
        payload_json='{"a":1}',
        request_context_json='{"user_id":1}',
        status="pending",
        lease_owner=None,
        lease_expires_at=None,
        updated_at=None,
    )
    claim_session = _Session(rows=[row_pending])
    repo = SimpleNamespace(
        _session_factory=_SessionFactory(claim_session),
        _attach_actor=lambda s: setattr(s, "attached", True),
        _json_load=lambda raw: {"decoded": raw},
        ClaimedOutboxJob=lambda **kwargs: SimpleNamespace(**kwargs),
    )
    claimed = mod.claim_outbox_jobs(repo, batch_size=5, owner="w1", lease_seconds=10)
    assert len(claimed) == 1
    assert claimed[0].id == "j1"
    assert row_pending.status == "processing"
    assert row_pending.lease_owner == "w1"
    assert claim_session.commits == 1 and claim_session.attached is True

    row_complete = SimpleNamespace(
        status="processing",
        completed_at=None,
        lease_owner="w1",
        lease_expires_at=datetime(2026, 1, 1, 12, 0, 30),
        updated_at=None,
    )
    complete_session = _Session(by_id={"j1": row_complete})
    repo_complete = SimpleNamespace(
        _session_factory=_SessionFactory(complete_session),
        _attach_actor=lambda s: setattr(s, "attached", True),
    )
    mod.complete_outbox_job(repo_complete, "j1")
    assert row_complete.status == "completed"
    assert row_complete.lease_owner is None
    assert complete_session.commits == 1 and complete_session.attached is True

    complete_missing_session = _Session(by_id={})
    repo_complete_missing = SimpleNamespace(
        _session_factory=_SessionFactory(complete_missing_session),
        _attach_actor=lambda s: setattr(s, "attached", True),
    )
    mod.complete_outbox_job(repo_complete_missing, "missing")
    assert complete_missing_session.commits == 0

    row_retry = SimpleNamespace(
        attempts=0,
        last_error=None,
        lease_owner="w1",
        lease_expires_at=datetime(2026, 1, 1, 12, 0, 30),
        status="processing",
        available_at=None,
        updated_at=None,
    )
    fail_retry_session = _Session(by_id={"j2": row_retry})
    repo_fail_retry = SimpleNamespace(
        _session_factory=_SessionFactory(fail_retry_session),
        _attach_actor=lambda s: setattr(s, "attached", True),
    )
    mod.fail_outbox_job(repo_fail_retry, "j2", error="temporary", max_attempts=3)
    assert row_retry.status == "failed"
    assert row_retry.last_error == "temporary"
    assert row_retry.attempts == 1
    assert row_retry.lease_owner is None
    assert fail_retry_session.commits == 1

    row_dead = SimpleNamespace(
        attempts=2,
        last_error=None,
        lease_owner="w1",
        lease_expires_at=datetime(2026, 1, 1, 12, 0, 30),
        status="processing",
        available_at=None,
        updated_at=None,
    )
    fail_dead_session = _Session(by_id={"j3": row_dead})
    repo_fail_dead = SimpleNamespace(
        _session_factory=_SessionFactory(fail_dead_session),
        _attach_actor=lambda s: setattr(s, "attached", True),
    )
    mod.fail_outbox_job(repo_fail_dead, "j3", error="fatal", max_attempts=3)
    assert row_dead.status == "dead_letter"
    assert row_dead.attempts == 3
    assert fail_dead_session.commits == 1

    fail_missing_session = _Session(by_id={})
    repo_fail_missing = SimpleNamespace(
        _session_factory=_SessionFactory(fail_missing_session),
        _attach_actor=lambda s: setattr(s, "attached", True),
    )
    mod.fail_outbox_job(repo_fail_missing, "missing", error="x", max_attempts=1)
    assert fail_missing_session.commits == 0
