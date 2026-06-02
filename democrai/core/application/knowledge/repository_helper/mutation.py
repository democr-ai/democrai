"""Write-side repository operations for the knowledge canonical store."""

from __future__ import annotations

import json
from uuid import uuid4

from democrai.core.runtime.foundation.app import current_request_context_payload


def upsert_source(repo,
    *,
    user_id: int,
    organization_id: int | None,
    owner_access_level: int,
    source,
):
    """Create or update a source row while preserving version history."""
    source_id = source.source_id or str(uuid4())
    org_id = repo._organization_id(organization_id)
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        row = session.get(repo.KnowledgeSourceRecord, source_id)
        if row is None:
            row = repo.KnowledgeSourceRecord(
                id=source_id,
                user_id=user_id,
                organization_id=org_id,
                source_type=source.source_type,
                title=source.title,
                mime_type=source.mime_type,
                external_ref=source.external_ref,
                media_uri=source.media_uri,
                checksum=source.checksum,
                owner_access_level=owner_access_level,
                is_public=1 if source.is_public else 0,
                metadata_json=repo._json_dump(source.metadata),
                version=1,
                status="active",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            if not repo._is_owned_by(row, user_id=user_id, organization_id=org_id):
                raise PermissionError(f"Knowledge source not owned by scope: {source_id}")
            row.version += 1
            row.source_type = source.source_type
            row.title = source.title
            row.mime_type = source.mime_type
            row.external_ref = source.external_ref
            row.media_uri = source.media_uri
            row.checksum = source.checksum
            row.owner_access_level = owner_access_level
            row.is_public = 1 if source.is_public else 0
            row.metadata_json = repo._json_dump(source.metadata)
            row.status = "active"
            row.deleted_at = None
            row.updated_at = now
        session.commit()
        session.refresh(row)
        return row


def upsert_item(repo,
    *,
    source_id: str,
    user_id: int,
    organization_id: int | None,
    owner_access_level: int,
    item,
    embedding_model_id: str | None,
    embedding_model_version: str | None,
    embedding_dim: int | None,
):
    """Create or update one knowledge item and its embedding metadata."""
    item_id = item.item_id or str(uuid4())
    org_id = repo._organization_id(organization_id)
    now = repo.utc_now_naive()
    embedding_text = item.embedding_text or item.summary or item.content
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        source = session.get(repo.KnowledgeSourceRecord, source_id)
        if source is None:
            raise KeyError(f"Knowledge source not found: {source_id}")
        if not repo._is_owned_by(source, user_id=user_id, organization_id=org_id):
            raise PermissionError(f"Knowledge source not owned by scope: {source_id}")
        item_metadata = dict(item.metadata or {})
        source_metadata = repo._json_load(source.metadata_json)
        source_file_id = source_metadata.get("file_id")
        if source_file_id and not item_metadata.get("file_id"):
            item_metadata["file_id"] = source_file_id
        media_file_id = item_metadata.get("file_id")
        content_hash = repo.build_content_hash(
            item.kind,
            item.title or "",
            item.content,
            item.summary or "",
            embedding_text,
            repo._json_dump(item_metadata),
        )
        row = session.get(repo.KnowledgeItemRecord, item_id)
        vector_status = "ready" if item.vector else "pending"
        item_is_public = (
            1
            if repo.normalize_public_flag(kind=item.kind, is_public=item.is_public)
            else 0
        )
        if row is None:
            row = repo.KnowledgeItemRecord(
                id=item_id,
                source_id=source_id,
                user_id=user_id,
                organization_id=org_id,
                kind=item.kind,
                title=item.title,
                content=item.content,
                summary=item.summary,
                embedding_text=embedding_text,
                metadata_json=repo._json_dump(item_metadata),
                media_file_id=media_file_id,
                external_ref=item.external_ref,
                owner_access_level=owner_access_level,
                is_public=item_is_public,
                content_hash=content_hash,
                version=1,
                vector_status=vector_status,
                kg_status="pending",
                embedding_model_id=embedding_model_id,
                embedding_model_version=embedding_model_version,
                embedding_dim=embedding_dim,
                embedding_vector_json=json.dumps(item.vector) if item.vector else None,
                embedding_updated_at=now if item.vector else None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            if not repo._is_owned_by(row, user_id=user_id, organization_id=org_id):
                raise PermissionError(f"Knowledge item not owned by scope: {item_id}")
            row.source_id = source_id
            row.kind = item.kind
            row.title = item.title
            row.content = item.content
            row.summary = item.summary
            row.embedding_text = embedding_text
            row.metadata_json = repo._json_dump(item_metadata)
            row.media_file_id = media_file_id
            row.external_ref = item.external_ref
            row.owner_access_level = owner_access_level
            row.is_public = item_is_public
            row.content_hash = content_hash
            row.version += 1
            row.vector_status = vector_status
            row.kg_status = "pending"
            row.embedding_model_id = embedding_model_id
            row.embedding_model_version = embedding_model_version
            row.embedding_dim = embedding_dim
            row.embedding_vector_json = json.dumps(item.vector) if item.vector else None
            row.embedding_updated_at = now if item.vector else None
            row.deleted_at = None
            row.updated_at = now
        session.commit()
        session.refresh(row)
        return row


def replace_item_graph(repo,
    *,
    item_id: str,
    user_id: int,
    organization_id: int | None,
    entities,
    relations,
):
    """Replace all relational entities and relations for an item atomically."""
    org_id = repo._organization_id(organization_id)
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        session.query(repo.KnowledgeRelationRecord).filter(
            repo.KnowledgeRelationRecord.item_id == item_id,
            repo.KnowledgeRelationRecord.user_id == user_id,
            repo.KnowledgeRelationRecord.organization_id == org_id,
        ).delete()
        session.query(repo.KnowledgeEntityRecord).filter(
            repo.KnowledgeEntityRecord.item_id == item_id,
            repo.KnowledgeEntityRecord.user_id == user_id,
            repo.KnowledgeEntityRecord.organization_id == org_id,
        ).delete()
        entity_rows = []
        entity_by_name = {}
        for entity in entities:
            entity_row = repo.KnowledgeEntityRecord(
                id=entity.entity_id or str(uuid4()),
                item_id=item_id,
                user_id=user_id,
                organization_id=org_id,
                entity_type=entity.entity_type,
                canonical_name=entity.name,
                metadata_json=repo._json_dump(entity.metadata),
                confidence=entity.confidence,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(entity_row)
            entity_rows.append(entity_row)
            entity_by_name[entity.name] = entity_row
        relation_rows = []
        for relation in relations:
            src = entity_by_name.get(relation.source_entity_name)
            dst = entity_by_name.get(relation.target_entity_name)
            if src is None or dst is None:
                continue
            relation_row = repo.KnowledgeRelationRecord(
                id=relation.relation_id or str(uuid4()),
                item_id=item_id,
                user_id=user_id,
                organization_id=org_id,
                relation_type=relation.relation_type,
                source_entity_id=src.id,
                target_entity_id=dst.id,
                metadata_json=repo._json_dump(relation.metadata),
                confidence=relation.confidence,
                weight=relation.weight,
                version=1,
                created_at=now,
                updated_at=now,
            )
            session.add(relation_row)
            relation_rows.append(relation_row)
        session.commit()
        return entity_rows, relation_rows


def enqueue_projection_job(repo,
    *,
    topic: str,
    aggregate_type: str,
    aggregate_id: str,
    aggregate_version: int,
    payload: dict,
    dedupe_suffix: str | None = None,
):
    """Insert an outbox job unless an equivalent dedupe key already exists."""
    now = repo.utc_now_naive()
    request_context = current_request_context_payload("knowledge_projection.enqueue")
    dedupe_key = f"{topic}:{aggregate_type}:{aggregate_id}:{aggregate_version}"
    if dedupe_suffix:
        dedupe_key = f"{dedupe_key}:{dedupe_suffix}"
    with repo._session_factory() as session:
        repo._attach_actor(session)
        existing = (
            session.query(repo.KnowledgeOutboxRecord)
            .filter(repo.KnowledgeOutboxRecord.dedupe_key == dedupe_key)
            .one_or_none()
        )
        if existing is not None:
            return existing
        row = repo.KnowledgeOutboxRecord(
            id=str(uuid4()),
            topic=topic,
            dedupe_key=dedupe_key,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            payload_json=repo._json_dump(payload),
            request_context_json=repo._json_dump(request_context),
            status="pending",
            attempts=0,
            available_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def soft_delete_source(repo, *, source_id: str, user_id: int, organization_id: int | None
):
    """Soft-delete a source and mark every owned item for reprojection delete."""
    org_id = repo._organization_id(organization_id)
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        source = (
            session.query(repo.KnowledgeSourceRecord)
            .filter(
                repo.KnowledgeSourceRecord.id == source_id,
                repo.KnowledgeSourceRecord.user_id == user_id,
                repo.KnowledgeSourceRecord.organization_id == org_id,
            )
            .one_or_none()
        )
        if source is None:
            return None, []
        source.version += 1
        source.status = "deleted"
        source.deleted_at = now
        source.updated_at = now
        items = (
            session.query(repo.KnowledgeItemRecord)
            .filter(
                repo.KnowledgeItemRecord.source_id == source_id,
                repo.KnowledgeItemRecord.user_id == user_id,
                repo.KnowledgeItemRecord.organization_id == org_id,
            )
            .all()
        )
        for item in items:
            item.version += 1
            item.deleted_at = now
            item.vector_status = "pending"
            item.kg_status = "pending"
            item.updated_at = now
        item_snapshots = [(item.id, item.version) for item in items]
        deleted_source_id = source.id
        session.commit()
        return deleted_source_id, item_snapshots


def set_item_embedding(repo,
    *,
    item_id: str,
    vector: list[float],
    embedding_model_id: str,
    embedding_model_version: str,
):
    """Persist a computed embedding vector back into canonical item storage."""
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeItemRecord, item_id)
        if row is None:
            raise KeyError(f"Knowledge item not found: {item_id}")
        row.embedding_vector_json = json.dumps(vector)
        row.embedding_dim = len(vector)
        row.embedding_model_id = embedding_model_id
        row.embedding_model_version = embedding_model_version
        row.embedding_updated_at = now
        row.vector_status = "ready"
        row.updated_at = now
        session.commit()
        session.refresh(row)
        return row


def upsert_item_classification(
    repo,
    *,
    item_id: str,
    user_id: int,
    organization_id: int | None,
    model_registry_id: int,
    model_version: str | None,
    label: str,
    score: float | None,
    scores: dict,
):
    """Create or update the derived classification for one item/model pair."""
    org_id = repo._organization_id(organization_id)
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        row = (
            session.query(repo.KnowledgeItemClassificationRecord)
            .filter(
                repo.KnowledgeItemClassificationRecord.item_id == item_id,
                repo.KnowledgeItemClassificationRecord.model_registry_id
                == model_registry_id,
            )
            .one_or_none()
        )
        if row is None:
            row = repo.KnowledgeItemClassificationRecord(
                id=str(uuid4()),
                item_id=item_id,
                user_id=user_id,
                organization_id=org_id,
                model_registry_id=model_registry_id,
                model_version=model_version,
                label=label,
                score=score,
                scores_json=repo._json_dump(scores),
                status="synced",
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.user_id = user_id
            row.organization_id = org_id
            row.model_version = model_version
            row.label = label
            row.score = score
            row.scores_json = repo._json_dump(scores)
            row.status = "synced"
            row.updated_at = now
        session.commit()
        session.refresh(row)
        return row


def delete_item_classifications(repo, *, item_id: str) -> int:
    """Delete derived classifications for one knowledge item."""
    with repo._session_factory() as session:
        repo._attach_actor(session)
        deleted = (
            session.query(repo.KnowledgeItemClassificationRecord)
            .filter(repo.KnowledgeItemClassificationRecord.item_id == item_id)
            .delete(synchronize_session=False)
        )
        session.commit()
        return deleted


def mark_item_status(repo,
    *,
    item_id: str,
    vector_status: str | None = None,
    kg_status: str | None = None,
):
    """Update vector and/or KG synchronization status for an item."""
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = session.get(repo.KnowledgeItemRecord, item_id)
        if row is None:
            return
        if vector_status is not None:
            row.vector_status = vector_status
        if kg_status is not None:
            row.kg_status = kg_status
        row.updated_at = now
        session.commit()


def upsert_projection_state(repo,
    *,
    aggregate_type: str,
    aggregate_id: str,
    projection: str,
    backend: str,
    backend_key: str | None,
    synced_version: int,
    status: str,
    last_error: str | None = None,
):
    """Create or update the projection-state row for an aggregate."""
    now = repo.utc_now_naive()
    with repo._session_factory() as session:
        repo._attach_actor(session)
        row = (
            session.query(repo.KnowledgeProjectionStateRecord)
            .filter(
                repo.KnowledgeProjectionStateRecord.aggregate_type == aggregate_type,
                repo.KnowledgeProjectionStateRecord.aggregate_id == aggregate_id,
                repo.KnowledgeProjectionStateRecord.projection == projection,
                repo.KnowledgeProjectionStateRecord.backend == backend,
            )
            .one_or_none()
        )
        if row is None:
            row = repo.KnowledgeProjectionStateRecord(
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                projection=projection,
                backend=backend,
                backend_key=backend_key,
                synced_version=synced_version,
                status=status,
                last_error=last_error,
                synced_at=now if status == "synced" else None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        else:
            row.backend_key = backend_key
            row.synced_version = synced_version
            row.status = status
            row.last_error = last_error
            row.synced_at = now if status == "synced" else None
            row.updated_at = now
        session.commit()
