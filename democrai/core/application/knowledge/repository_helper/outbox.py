"""Outbox-leasing helpers for knowledge projection workers."""

from __future__ import annotations

from datetime import timedelta
from sqlalchemy import or_
from democrai.core.application.knowledge.records import KnowledgeOutboxRecord
from democrai.core.platform.utils.timezone import utc_now_naive


def claim_outbox_jobs(repo, *, batch_size: int, owner: str, lease_seconds: int):
    """Lease a batch of pending outbox jobs for one worker instance."""
    now = utc_now_naive()
    lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
    with repo._session_factory() as session:
        repo._attach_actor(session)
        rows = (
            session.query(KnowledgeOutboxRecord)
            .filter(
                KnowledgeOutboxRecord.status.in_(("pending", "failed")),
                KnowledgeOutboxRecord.available_at <= now,
                or_(
                    KnowledgeOutboxRecord.lease_expires_at.is_(None),
                    KnowledgeOutboxRecord.lease_expires_at < now,
                ),
            )
            .order_by(KnowledgeOutboxRecord.created_at.asc())
            .limit(batch_size)
            .all()
        )
        claimed = []
        for row in rows:
            row.status = "processing"
            row.lease_owner = owner
            row.lease_expires_at = lease_expires_at
            row.updated_at = now
            claimed.append(
                repo.ClaimedOutboxJob(
                    id=row.id,
                    topic=row.topic,
                    aggregate_type=row.aggregate_type,
                    aggregate_id=row.aggregate_id,
                    aggregate_version=row.aggregate_version,
                    payload=repo._json_load(row.payload_json),
                    request_context=repo._json_load(row.request_context_json),
                )
            )
        session.commit()
        return claimed


def complete_outbox_job(repo, job_id: str) -> None:
    """Mark a leased outbox job as completed."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(KnowledgeOutboxRecord, job_id)
        if row is None:
            return
        row.status = "completed"
        row.completed_at = now
        row.lease_owner = None
        row.lease_expires_at = None
        row.updated_at = now
        session.commit()


def fail_outbox_job(repo, job_id: str, *, error: str, max_attempts: int) -> None:
    """Record a projection failure and reschedule or dead-letter the job."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(KnowledgeOutboxRecord, job_id)
        if row is None:
            return
        row.attempts += 1
        row.last_error = error
        row.lease_owner = None
        row.lease_expires_at = None
        if row.attempts >= max_attempts:
            row.status = "dead_letter"
            row.available_at = now
        else:
            row.status = "failed"
            row.available_at = now + timedelta(seconds=min(300, 2**row.attempts))
        row.updated_at = now
        session.commit()
