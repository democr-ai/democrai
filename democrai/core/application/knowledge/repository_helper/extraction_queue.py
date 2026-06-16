"""DB-backed queue helpers for knowledge extraction workers."""

from __future__ import annotations

from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_

from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload


def _node_coordination_enabled() -> bool:
    from democrai.core.infrastructure.ai.engine.invocation.config import (
        EngineInvocationRuntimeConfig,
    )

    return EngineInvocationRuntimeConfig.load(
        getattr(app_ctx(), "config", None)
    ).node_coordination_enabled


def _resolve_extractor_id_for_mime(mime_type: str) -> str | None:
    try:
        from democrai.core.application.knowledge.extractor.bindings import (
            resolve_bound_extractor,
        )

        bound = resolve_bound_extractor(mime_type=mime_type)
    except Exception:
        return None
    if not isinstance(bound, dict):
        return None
    return str(bound.get("extractor_id") or "") or None


def enqueue_extraction_request(
    repo,
    *,
    request_id: str | None = None,
    media_upload_id: int | None = None,
    user_id: int,
    organization_id: int | None,
    owner_access_level: int,
    module_name: str,
    storage_path: str,
    original_filename: str,
    mime_type: str | None = None,
    source_context: dict | None = None,
    metadata: dict | None = None,
    request_context: dict | None = None,
    is_public: bool = False,
    ingest_enabled: bool = True,
    extractor_id: str | None = None,
    extractor_config: dict | None = None,
    priority: int = 0,
):
    """Create a durable extraction queue entry."""
    now = utc_now_naive()
    org_id = to_optional_int(organization_id)
    resolved_request_context = (
        dict(request_context)
        if isinstance(request_context, dict)
        else current_request_context_payload("knowledge_extraction.enqueue")
    )
    if extractor_id is None and mime_type and _node_coordination_enabled():
        extractor_id = _resolve_extractor_id_for_mime(mime_type)
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        row = repo.KnowledgeExtractionRequestRecord(
            id=request_id or str(uuid4()),
            media_upload_id=media_upload_id,
            user_id=user_id,
            organization_id=org_id,
            owner_access_level=owner_access_level,
            module_name=module_name,
            storage_path=storage_path,
            original_filename=original_filename,
            mime_type=mime_type,
            source_context_json=repo._json_dump(source_context),
            metadata_json=repo._json_dump(metadata),
            request_context_json=repo._json_dump(resolved_request_context),
            is_public=1 if is_public else 0,
            ingest_enabled=1 if ingest_enabled else 0,
            extractor_id=extractor_id,
            extractor_config_json=repo._json_dump(extractor_config),
            status="pending",
            priority=priority,
            attempts=0,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def get_extraction_request_metadata(repo, request_id: str) -> dict:
    """Return extraction request metadata without claiming queue work."""
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeExtractionRequestRecord, request_id)
        if row is None:
            return {}
        return repo._json_load(row.metadata_json)


def claim_extraction_requests(
    repo,
    *,
    batch_size: int,
    owner: str,
    lease_seconds: int,
    installed_extractor_ids: list[str] | None = None,
):
    """Lease pending extraction requests for one worker instance.

    ``installed_extractor_ids`` filters the claim to rows whose extractor is
    installed on the claiming node (rows with no extractor binding still pass
    and are settled by the post-claim guard). ``None`` keeps the historical
    single-node behavior untouched.
    """
    now = utc_now_naive()
    lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
    with repo._session_factory() as session:
        repo._attach_actor(session)
        query = (
            session.query(repo.KnowledgeExtractionRequestRecord)
            .filter(
                repo.KnowledgeExtractionRequestRecord.status.in_(("pending", "failed")),
                repo.KnowledgeExtractionRequestRecord.available_at <= now,
                or_(
                    repo.KnowledgeExtractionRequestRecord.lease_expires_at.is_(None),
                    repo.KnowledgeExtractionRequestRecord.lease_expires_at < now,
                ),
            )
        )
        if installed_extractor_ids is not None:
            query = query.filter(
                or_(
                    repo.KnowledgeExtractionRequestRecord.extractor_id.is_(None),
                    repo.KnowledgeExtractionRequestRecord.extractor_id.in_(
                        list(installed_extractor_ids)
                    ),
                )
            )
        query = (
            query.order_by(
                repo.KnowledgeExtractionRequestRecord.priority.desc(),
                repo.KnowledgeExtractionRequestRecord.created_at.asc(),
            )
            .limit(max(1, batch_size))
        )
        rows = query.with_for_update(skip_locked=True).all()
        claimed = []
        for row in rows:
            row.status = "processing"
            row.lease_owner = owner
            row.lease_expires_at = lease_expires_at
            row.started_at = row.started_at or now
            row.updated_at = now
            claimed.append(
                repo.ClaimedExtractionRequest(
                    id=row.id,
                    media_upload_id=row.media_upload_id,
                    user_id=row.user_id,
                    organization_id=row.organization_id,
                    owner_access_level=row.owner_access_level,
                    module_name=row.module_name,
                    storage_path=row.storage_path,
                    original_filename=row.original_filename,
                    mime_type=row.mime_type,
                    source_context=repo._json_load(row.source_context_json),
                    metadata=repo._json_load(row.metadata_json),
                    request_context=repo._json_load(row.request_context_json),
                    is_public=bool(row.is_public),
                    ingest_enabled=bool(row.ingest_enabled),
                    extractor_id=row.extractor_id,
                    extractor_config=repo._json_load(row.extractor_config_json),
                    attempts=row.attempts,
                )
            )
        session.commit()
        return claimed


def complete_extraction_request(repo, request_id: str) -> None:
    """Mark one leased extraction request as completed."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeExtractionRequestRecord, request_id)
        if row is None:
            return
        row.status = "completed"
        row.completed_at = now
        row.lease_owner = None
        row.lease_expires_at = None
        row.updated_at = now
        session.commit()


def release_extraction_request(
    repo,
    request_id: str,
    *,
    defer_seconds: float,
    reason: str | None = None,
) -> None:
    """Put a claimed request back as pending without consuming an attempt.

    Used when the claiming node cannot process it (extractor installed on a
    different node): the row becomes claimable again after ``defer_seconds``.
    """
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeExtractionRequestRecord, request_id)
        if row is None or row.status != "processing":
            return
        row.status = "pending"
        row.lease_owner = None
        row.lease_expires_at = None
        row.available_at = now + timedelta(seconds=max(0.0, float(defer_seconds)))
        if reason:
            row.last_error = reason
        row.updated_at = now
        session.commit()


def fail_extraction_request(
    repo,
    request_id: str,
    *,
    error: str,
    max_attempts: int,
) -> None:
    """Record an extraction failure and reschedule or dead-letter it."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeExtractionRequestRecord, request_id)
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
