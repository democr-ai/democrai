"""DB-backed queue helpers for canonical knowledge ingestion."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import or_

from democrai.core.application.knowledge.models import KnowledgeIngestRequest
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import current_request_context_payload


def _payload(value):
    if is_dataclass(value):
        return asdict(value)
    return value


def _source_payload(source) -> dict:
    return dict(_payload(source) or {})


def _items_payload(items) -> list[dict]:
    return [dict(_payload(item) or {}) for item in tuple(items or ())]


def enqueue_ingestion_request(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    source,
    items,
    origin_type: str,
    extraction_request_id: str | None = None,
    request_context: dict | None = None,
    priority: int = 0,
):
    """Create a durable ingestion queue entry."""
    now = utc_now_naive()
    org_id = to_optional_int(organization_id)
    resolved_request_context = (
        dict(request_context)
        if isinstance(request_context, dict)
        else current_request_context_payload("knowledge_ingestion.enqueue")
    )
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        row = repo.KnowledgeIngestionRequestRecord(
            id=str(uuid4()),
            extraction_request_id=extraction_request_id,
            origin_type=origin_type,
            user_id=user_id,
            organization_id=org_id,
            source_json=repo._json_dump(_source_payload(source)),
            items_json=repo._json_dump(_items_payload(items)),
            request_context_json=repo._json_dump(resolved_request_context),
            embedding_enabled=0,
            embedding_config_json=repo._json_dump({}),
            kg_enabled=0,
            kg_config_json=repo._json_dump({}),
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


def claim_ingestion_requests(repo, *, batch_size: int, owner: str, lease_seconds: int):
    """Lease pending ingestion requests for one worker instance."""
    now = utc_now_naive()
    lease_expires_at = now + timedelta(seconds=max(1, lease_seconds))
    with repo._session_factory() as session:
        repo._attach_actor(session)
        rows = (
            session.query(repo.KnowledgeIngestionRequestRecord)
            .filter(
                repo.KnowledgeIngestionRequestRecord.status.in_(("pending", "failed")),
                repo.KnowledgeIngestionRequestRecord.available_at <= now,
                or_(
                    repo.KnowledgeIngestionRequestRecord.lease_expires_at.is_(None),
                    repo.KnowledgeIngestionRequestRecord.lease_expires_at < now,
                ),
            )
            .order_by(
                repo.KnowledgeIngestionRequestRecord.priority.desc(),
                repo.KnowledgeIngestionRequestRecord.created_at.asc(),
            )
            .limit(max(1, batch_size))
            .with_for_update(skip_locked=True)
            .all()
        )
        claimed = []
        for row in rows:
            row.status = "processing"
            row.lease_owner = owner
            row.lease_expires_at = lease_expires_at
            row.started_at = row.started_at or now
            row.updated_at = now
            claimed.append(
                repo.ClaimedIngestionRequest(
                    id=row.id,
                    extraction_request_id=row.extraction_request_id,
                    origin_type=row.origin_type,
                    user_id=row.user_id,
                    organization_id=row.organization_id,
                    source=repo._json_load(row.source_json),
                    items=list(repo._json_load(row.items_json) or []),
                    request_context=repo._json_load(row.request_context_json),
                    attempts=row.attempts,
                )
            )
        session.commit()
        return claimed


def build_ingestion_request_payload(repo, *, request) -> KnowledgeIngestRequest:
    """Build the service ingestion request for a claimed queue entry."""
    from democrai.core.application.knowledge.models import EntityInput
    from democrai.core.application.knowledge.models import KnowledgeIngestItem
    from democrai.core.application.knowledge.models import KnowledgeSourceInput
    from democrai.core.application.knowledge.models import RelationInput

    source_payload = dict(request.source or {})
    item_payloads = list(request.items or [])
    if not source_payload or not item_payloads:
        source_payload, item_payloads = _payload_from_extraction(repo, request)
    return KnowledgeIngestRequest(
        user_id=request.user_id,
        organization_id=request.organization_id,
        source=KnowledgeSourceInput(**source_payload),
        items=tuple(
            KnowledgeIngestItem(
                **{
                    **dict(item),
                    "entities": tuple(
                        EntityInput(**dict(entity))
                        for entity in list(dict(item).get("entities") or [])
                    ),
                    "relations": tuple(
                        RelationInput(**dict(relation))
                        for relation in list(dict(item).get("relations") or [])
                    ),
                }
            )
            for item in item_payloads
        ),
    )


def _payload_from_extraction(repo, request) -> tuple[dict, list[dict]]:
    if not request.extraction_request_id:
        raise RuntimeError("knowledge_ingestion_payload_missing")
    with repo._session_factory() as session:
        extraction = session.get(
            repo.KnowledgeExtractionRequestRecord,
            request.extraction_request_id,
        )
        if extraction is None:
            raise RuntimeError("knowledge_ingestion_extraction_request_missing")
        extracted_items = (
            session.query(repo.KnowledgeExtractedItemRecord)
            .filter(
                repo.KnowledgeExtractedItemRecord.extraction_request_id
                == request.extraction_request_id,
                repo.KnowledgeExtractedItemRecord.ingestion_status == "pending",
            )
            .order_by(repo.KnowledgeExtractedItemRecord.ordinal.asc())
            .all()
        )
        extracted_items = sorted(
            extracted_items,
            key=lambda item: (
                item.ordinal,
                0 if item.item_type == "document" else 1,
                item.item_type,
            ),
        )
        if not extracted_items:
            raise RuntimeError("knowledge_ingestion_extracted_items_missing")
        source_context = repo._json_load(extraction.source_context_json)
        metadata = {
            **repo._json_load(extraction.metadata_json),
            **source_context,
            "storage_path": extraction.storage_path,
            "mime_type": extraction.mime_type,
        }
        source_id = (
            str(source_context.get("source_id") or "").strip()
            or (
                f"media:{source_context.get('file_id')}"
                if source_context.get("file_id")
                else ""
            )
            or f"extraction:{request.extraction_request_id}"
        )
        source = {
            "source_id": source_id,
            "source_type": source_context.get("source_type") or "document",
            "title": extraction.original_filename,
            "mime_type": extraction.mime_type,
            "media_uri": extraction.storage_path,
            "is_public": extraction.is_public,
            "metadata": metadata,
        }
        items = []
        for item in extracted_items:
            item_metadata = {
                **repo._json_load(item.metadata_json),
                "item_type": item.item_type,
                "ordinal": item.ordinal,
                "file_id": source_context.get("file_id"),
            }
            content = item.content_text.strip() if item.content_text is not None else ""
            if not content:
                content = repo._json_dump(repo._json_load(item.content_json))
            items.append(
                {
                    "item_id": (
                        f"{request.extraction_request_id}:"
                        f"{item.item_type}:{item.ordinal}"
                    ),
                    "kind": "document_chunk",
                    "title": item.title,
                    "content": content,
                    "is_public": item.is_public,
                    "metadata": item_metadata,
                }
            )
        return source, items


def complete_ingestion_request(repo, request_id: str) -> None:
    """Mark one leased ingestion request as completed."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeIngestionRequestRecord, request_id)
        if row is None:
            return
        row.status = "completed"
        row.completed_at = now
        row.lease_owner = None
        row.lease_expires_at = None
        row.updated_at = now
        if row.extraction_request_id:
            (
                session.query(repo.KnowledgeExtractedItemRecord)
                .filter(
                    repo.KnowledgeExtractedItemRecord.extraction_request_id
                    == row.extraction_request_id,
                    repo.KnowledgeExtractedItemRecord.ingestion_status == "pending",
                )
                .update(
                    {"ingestion_status": "ingested", "ingested_at": now, "updated_at": now},
                    synchronize_session=False,
                )
            )
        session.commit()


def fail_ingestion_request(
    repo,
    request_id: str,
    *,
    error: str,
    max_attempts: int,
) -> None:
    """Record an ingestion failure and reschedule or dead-letter it."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeIngestionRequestRecord, request_id)
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
