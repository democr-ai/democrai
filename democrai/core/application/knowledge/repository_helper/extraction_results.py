"""Persistence helpers for completed knowledge extraction results."""

from __future__ import annotations

from uuid import uuid4

from democrai.core.platform.utils.timezone import utc_now_naive


def complete_extraction_with_items(
    repo,
    *,
    request_id: str,
    user_id: int,
    organization_id: int | None,
    items: list[dict],
    enqueue_ingestion: bool,
    priority: int = 0,
) -> None:
    """Persist extracted items and complete the extraction request atomically."""
    now = utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=organization_id)
        request = session.get(repo.KnowledgeExtractionRequestRecord, request_id)
        if request is None:
            return
        (
            session.query(repo.KnowledgeExtractedItemRecord)
            .filter(
                repo.KnowledgeExtractedItemRecord.extraction_request_id == request_id
            )
            .delete(synchronize_session=False)
        )
        ingestion_status = "pending" if enqueue_ingestion else "skipped"
        for item in items:
            session.add(
                repo.KnowledgeExtractedItemRecord(
                    id=str(uuid4()),
                    extraction_request_id=request_id,
                    user_id=user_id,
                    organization_id=organization_id,
                    item_type=item["item_type"],
                    ordinal=item["ordinal"],
                    title=item.get("title"),
                    content_text=item.get("content_text") or None,
                    content_json=repo._json_dump(item.get("content")),
                    metadata_json=repo._json_dump(item.get("metadata")),
                    is_public=1 if item.get("is_public", request.is_public) else 0,
                    ingestion_status=ingestion_status,
                    created_at=now,
                    updated_at=now,
                )
            )
        if enqueue_ingestion:
            session.add(
                repo.KnowledgeIngestionRequestRecord(
                    id=str(uuid4()),
                    extraction_request_id=request_id,
                    origin_type="extraction",
                    user_id=user_id,
                    organization_id=organization_id,
                    source_json=repo._json_dump({}),
                    items_json=repo._json_dump([]),
                    request_context_json=str(request.request_context_json or "{}"),
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
            )
        request.status = "completed"
        request.completed_at = now
        request.lease_owner = None
        request.lease_expires_at = None
        request.updated_at = now
        session.commit()
