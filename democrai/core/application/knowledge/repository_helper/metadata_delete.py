"""Metadata-scoped deletion helpers for canonical knowledge records."""

from __future__ import annotations

from typing import Any

from democrai.core.infrastructure.database.models import MediaUpload


def _filter_values(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple, set)):
        return tuple(
            str(item).strip()
            for item in value
            if str(item).strip()
        )
    rendered = str(value).strip()
    return (rendered,) if rendered else ()


def _matches_metadata(metadata: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, raw_value in filters.items():
        values = _filter_values(raw_value)
        if not values:
            return False
        if str(metadata.get(key) or "").strip() not in values:
            return False
    return True


def _metadata_with_media_module(session, metadata: dict[str, Any]) -> dict[str, Any]:
    if metadata.get("module_name"):
        return metadata
    file_id = str(metadata.get("file_id") or "").strip()
    if not file_id:
        return metadata
    upload = (
        session.query(MediaUpload.module_name)
        .filter(MediaUpload.file_id == file_id)
        .one_or_none()
    )
    if upload is None:
        return metadata
    return {**metadata, "module_name": upload[0]}


def _source_item_metadata(repo, session, source, item=None) -> dict[str, Any]:
    metadata = repo._json_load(source.metadata_json)
    if item is not None:
        metadata.update(repo._json_load(item.metadata_json))
    metadata = _metadata_with_media_module(session, metadata)
    return metadata


def _ingestion_request_matches(repo, session, row, filters: dict[str, Any]) -> bool:
    if row.extraction_request_id:
        extraction = session.get(
            repo.KnowledgeExtractionRequestRecord,
            row.extraction_request_id,
        )
        if extraction is not None and _extraction_request_matches(
            repo,
            extraction,
            filters,
        ):
            return True
    source = repo._json_load(row.source_json)
    source_metadata = dict(source.get("metadata") or {})
    source_metadata = _metadata_with_media_module(session, source_metadata)
    if _matches_metadata(source_metadata, filters):
        return True
    for item in list(repo._json_load(row.items_json) or []):
        if not isinstance(item, dict):
            continue
        metadata = dict(source_metadata)
        metadata.update(dict(item.get("metadata") or {}))
        metadata = _metadata_with_media_module(session, metadata)
        if _matches_metadata(metadata, filters):
            return True
    return False


def _extraction_request_matches(repo, row, filters: dict[str, Any]) -> bool:
    metadata = {"module_name": row.module_name}
    metadata.update(repo._json_load(row.source_context_json))
    metadata.update(repo._json_load(row.metadata_json))
    return _matches_metadata(metadata, filters)


def _chat_upload_context_matches(repo, session, row, filters: dict[str, Any]) -> bool:
    return _matches_metadata(
        _metadata_with_media_module(session, repo._json_load(row.context_json)),
        filters,
    )


def delete_by_metadata(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    metadata_filters: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    """Delete owned knowledge records matched by top-level metadata filters."""
    filters = dict(metadata_filters or {})
    if not filters:
        raise ValueError("metadata_filters are required")
    org_id = repo._organization_id(organization_id)
    now = repo.utc_now_naive()
    deleted_items: list[dict[str, Any]] = []
    deleted_source_ids: set[str] = set()
    cancelled_ingestion_ids: list[str] = []
    deleted_ingestion_ids: list[str] = []
    cancelled_extraction_ids: list[str] = []
    deleted_extracted_items = 0
    deleted_context_ids: list[str] = []

    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        sources = (
            session.query(repo.KnowledgeSourceRecord)
            .filter(
                repo.KnowledgeSourceRecord.user_id == user_id,
                repo.KnowledgeSourceRecord.organization_id == org_id,
                repo.KnowledgeSourceRecord.deleted_at.is_(None),
            )
            .all()
        )
        sources_by_id = {source.id: source for source in sources}
        source_match_ids = {
            source.id
            for source in sources
            if _matches_metadata(
                _metadata_with_media_module(
                    session,
                    repo._json_load(source.metadata_json),
                ),
                filters,
            )
        }
        items = (
            session.query(repo.KnowledgeItemRecord)
            .filter(
                repo.KnowledgeItemRecord.user_id == user_id,
                repo.KnowledgeItemRecord.organization_id == org_id,
                repo.KnowledgeItemRecord.deleted_at.is_(None),
            )
            .all()
        )
        item_match_ids: set[str] = set()
        for item in items:
            source = sources_by_id.get(item.source_id)
            if source is None:
                continue
            if item.source_id in source_match_ids or _matches_metadata(
                _source_item_metadata(repo, session, source, item),
                filters,
            ):
                item_match_ids.add(item.id)

        for source in sources:
            if source.id not in source_match_ids:
                continue
            source.version += 1
            source.status = "deleted"
            source.deleted_at = now
            source.updated_at = now
            deleted_source_ids.add(source.id)

        for item in items:
            if item.id not in item_match_ids:
                continue
            item.version += 1
            item.deleted_at = now
            item.vector_status = "pending"
            item.kg_status = "pending"
            item.updated_at = now
            deleted_items.append(
                {
                    "item_id": item.id,
                    "item_version": item.version,
                    "source_id": item.source_id,
                }
            )

        ingestion_rows = (
            session.query(repo.KnowledgeIngestionRequestRecord)
            .filter(
                repo.KnowledgeIngestionRequestRecord.user_id == user_id,
                repo.KnowledgeIngestionRequestRecord.organization_id == org_id,
            )
            .all()
        )
        for row in ingestion_rows:
            if not _ingestion_request_matches(repo, session, row, filters):
                continue
            if force:
                deleted_ingestion_ids.append(row.id)
                session.delete(row)
                continue
            if row.status not in ("pending", "failed"):
                continue
            row.status = "cancelled"
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now
            cancelled_ingestion_ids.append(row.id)

        extraction_rows = (
            session.query(repo.KnowledgeExtractionRequestRecord)
            .filter(
                repo.KnowledgeExtractionRequestRecord.user_id == user_id,
                repo.KnowledgeExtractionRequestRecord.organization_id == org_id,
            )
            .all()
        )
        for row in extraction_rows:
            if not _extraction_request_matches(repo, row, filters):
                continue
            row.status = "cancelled"
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now
            cancelled_extraction_ids.append(row.id)
            extracted_items = (
                session.query(repo.KnowledgeExtractedItemRecord)
                .filter(
                    repo.KnowledgeExtractedItemRecord.extraction_request_id == row.id,
                    repo.KnowledgeExtractedItemRecord.user_id == user_id,
                    repo.KnowledgeExtractedItemRecord.organization_id == org_id,
                )
                .all()
            )
            for item in extracted_items:
                session.delete(item)
                deleted_extracted_items += 1

        context_rows = (
            session.query(repo.KnowledgeChatUploadContextRecord)
            .filter(
                repo.KnowledgeChatUploadContextRecord.user_id == user_id,
                repo.KnowledgeChatUploadContextRecord.organization_id == org_id,
            )
            .all()
        )
        for row in context_rows:
            if not _chat_upload_context_matches(repo, session, row, filters):
                continue
            deleted_context_ids.append(row.id)
            session.delete(row)

        session.commit()

    return {
        "deleted_source_ids": tuple(sorted(deleted_source_ids)),
        "deleted_items": tuple(deleted_items),
        "cancelled_ingestion_ids": tuple(cancelled_ingestion_ids),
        "deleted_ingestion_ids": tuple(deleted_ingestion_ids),
        "cancelled_extraction_ids": tuple(cancelled_extraction_ids),
        "deleted_extracted_items": deleted_extracted_items,
        "deleted_chat_upload_context_ids": tuple(deleted_context_ids),
        "force": bool(force),
    }


def purge_deleted_item_if_ready(repo, *, item_id: str) -> bool:
    """Physically remove a deleted item once all derived delete projections completed."""
    if not str(item_id or "").strip():
        return False
    with repo._session_factory() as session:
        repo._attach_actor(session)
        item = session.get(repo.KnowledgeItemRecord, item_id)
        if item is None or item.deleted_at is None:
            return False
        if item.vector_status != "deleted" or item.kg_status != "deleted":
            return False
        states = (
            session.query(repo.KnowledgeProjectionStateRecord)
            .filter(
                repo.KnowledgeProjectionStateRecord.aggregate_type == "knowledge_item",
                repo.KnowledgeProjectionStateRecord.aggregate_id == item_id,
            )
            .all()
        )
        if not states or any(state.status != "deleted" for state in states):
            return False
        unfinished_jobs = (
            session.query(repo.KnowledgeOutboxRecord)
            .filter(
                repo.KnowledgeOutboxRecord.aggregate_type == "knowledge_item",
                repo.KnowledgeOutboxRecord.aggregate_id == item_id,
                repo.KnowledgeOutboxRecord.status != "completed",
            )
            .count()
        )
        if unfinished_jobs:
            return False

        source_id = item.source_id
        session.query(repo.KnowledgeRelationRecord).filter(
            repo.KnowledgeRelationRecord.item_id == item_id
        ).delete(synchronize_session=False)
        session.query(repo.KnowledgeEntityRecord).filter(
            repo.KnowledgeEntityRecord.item_id == item_id
        ).delete(synchronize_session=False)
        session.query(repo.KnowledgeItemClassificationRecord).filter(
            repo.KnowledgeItemClassificationRecord.item_id == item_id
        ).delete(synchronize_session=False)
        session.query(repo.KnowledgeProjectionStateRecord).filter(
            repo.KnowledgeProjectionStateRecord.aggregate_type == "knowledge_item",
            repo.KnowledgeProjectionStateRecord.aggregate_id == item_id,
        ).delete(synchronize_session=False)
        session.query(repo.KnowledgeOutboxRecord).filter(
            repo.KnowledgeOutboxRecord.aggregate_type == "knowledge_item",
            repo.KnowledgeOutboxRecord.aggregate_id == item_id,
            repo.KnowledgeOutboxRecord.status == "completed",
        ).delete(synchronize_session=False)
        session.delete(item)
        session.flush()

        remaining_source_items = (
            session.query(repo.KnowledgeItemRecord)
            .filter(repo.KnowledgeItemRecord.source_id == source_id)
            .count()
        )
        source = session.get(repo.KnowledgeSourceRecord, source_id)
        if source is not None and source.deleted_at is not None and remaining_source_items == 0:
            session.delete(source)
        session.commit()
        return True
