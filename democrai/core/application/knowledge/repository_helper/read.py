"""Read-side repository operations for the knowledge canonical store."""

from __future__ import annotations

from sqlalchemy import or_
from democrai.core.application.knowledge.repository_helper.metadata_filters import (
    metadata_filter_expressions,
)
from democrai.core.application.knowledge.records import (
    KnowledgeEntityRecord,
    KnowledgeItemRecord,
    KnowledgeRelationRecord,
    KnowledgeSourceRecord,
)


_SOURCE_METADATA_FILTER_KEYS = {"module_name"}


def _split_metadata_filters(filters: dict | None) -> tuple[dict, dict]:
    item_filters = {}
    source_filters = {}
    for key, value in (filters or {}).items():
        if key in _SOURCE_METADATA_FILTER_KEYS:
            source_filters[key] = value
        else:
            item_filters[key] = value
    return item_filters, source_filters


def _apply_metadata_filters(session, query, *, item_filters: dict, source_filters: dict):
    for expression in metadata_filter_expressions(
        session,
        KnowledgeItemRecord.metadata_json,
        item_filters,
    ):
        query = query.filter(expression)
    if source_filters:
        query = query.join(
            KnowledgeSourceRecord,
            KnowledgeSourceRecord.id == KnowledgeItemRecord.source_id,
        ).filter(KnowledgeSourceRecord.deleted_at.is_(None))
        for expression in metadata_filter_expressions(
            session,
            KnowledgeSourceRecord.metadata_json,
            source_filters,
        ):
            query = query.filter(expression)
    return query


def get_item(repo, item_id: str):
    """Return one knowledge item row by identifier."""
    with repo._session_factory() as session:
        return session.get(KnowledgeItemRecord, item_id)


def get_source(repo, source_id: str):
    """Return one source row by identifier."""
    with repo._session_factory() as session:
        return session.get(KnowledgeSourceRecord, source_id)


def get_source_for_owner(repo, *, source_id: str, user_id: int, organization_id: int | None):
    """Return a source only when it belongs to the given owner scope."""
    with repo._session_factory() as session:
        return (
            session.query(KnowledgeSourceRecord)
            .filter(
                KnowledgeSourceRecord.id == source_id,
                repo._owner_filter(
                    KnowledgeSourceRecord,
                    user_id=user_id,
                    organization_id=organization_id,
                ),
            )
            .one_or_none()
        )


def list_sources(
    repo,
    *,
    include_deleted: bool = False,
    source_id: str | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
    source_type: str | None = None,
    limit: int | None = None,
):
    """List sources with optional owner/type filters."""
    with repo._session_factory() as session:
        query = session.query(KnowledgeSourceRecord)
        if source_id is not None:
            query = query.filter(KnowledgeSourceRecord.id == source_id)
        if user_id is not None:
            query = query.filter(KnowledgeSourceRecord.user_id == user_id)
        if organization_id is not None:
            query = query.filter(
                KnowledgeSourceRecord.organization_id
                == repo._organization_id(organization_id)
            )
        if source_type is not None:
            query = query.filter(KnowledgeSourceRecord.source_type == source_type)
        if not include_deleted:
            query = query.filter(KnowledgeSourceRecord.deleted_at.is_(None))
        query = query.order_by(KnowledgeSourceRecord.updated_at.desc())
        if limit is not None:
            query = query.limit(max(1, limit))
        return query.all()


def list_entities(repo, item_id: str):
    """Return every stored entity for an item ordered by canonical name."""
    with repo._session_factory() as session:
        return (
            session.query(KnowledgeEntityRecord)
            .filter(KnowledgeEntityRecord.item_id == item_id)
            .order_by(KnowledgeEntityRecord.canonical_name.asc())
            .all()
        )


def list_relations(repo, item_id: str):
    """Return every stored relation for an item ordered by type."""
    with repo._session_factory() as session:
        return (
            session.query(KnowledgeRelationRecord)
            .filter(KnowledgeRelationRecord.item_id == item_id)
            .order_by(KnowledgeRelationRecord.relation_type.asc())
            .all()
        )


def list_items_for_source(repo, *, source_id: str, include_deleted: bool = False):
    """Return every item belonging to a source."""
    with repo._session_factory() as session:
        query = session.query(KnowledgeItemRecord).filter(
            KnowledgeItemRecord.source_id == source_id
        )
        if not include_deleted:
            query = query.filter(KnowledgeItemRecord.deleted_at.is_(None))
        return query.order_by(KnowledgeItemRecord.created_at.asc()).all()


def search_items(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    query_text: str,
    limit: int,
    metadata_filters: dict | None = None,
):
    """Execute lexical search over visible knowledge items."""
    org_id = repo._organization_id(organization_id)
    pattern = f"%{query_text.lower()}%"
    item_filters, source_filters = _split_metadata_filters(metadata_filters)
    with repo._session_factory() as session:
        query = session.query(KnowledgeItemRecord).filter(
            KnowledgeItemRecord.deleted_at.is_(None),
            repo._visibility_filter(
                KnowledgeItemRecord,
                user_id=user_id, organization_id=org_id, access_level=access_level
            ),
            or_(
                KnowledgeItemRecord.content.ilike(pattern),
                KnowledgeItemRecord.summary.ilike(pattern),
                KnowledgeItemRecord.title.ilike(pattern),
            ),
        )
        query = _apply_metadata_filters(
            session,
            query,
            item_filters=item_filters,
            source_filters=source_filters,
        )
        return query.order_by(KnowledgeItemRecord.updated_at.desc()).limit(limit).all()


def get_items_by_ids(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    item_ids,
    metadata_filters: dict | None = None,
):
    """Return visible items matching the provided identifiers."""
    ids = list(dict.fromkeys(item_id for item_id in item_ids if item_id))
    if not ids:
        return []
    org_id = repo._organization_id(organization_id)
    item_filters, source_filters = _split_metadata_filters(metadata_filters)
    with repo._session_factory() as session:
        query = session.query(KnowledgeItemRecord).filter(
            KnowledgeItemRecord.id.in_(ids),
            KnowledgeItemRecord.deleted_at.is_(None),
            repo._visibility_filter(
                KnowledgeItemRecord,
                user_id=user_id, organization_id=org_id, access_level=access_level
            ),
        )
        query = _apply_metadata_filters(
            session,
            query,
            item_filters=item_filters,
            source_filters=source_filters,
        )
        items = query.all()
        order = {item_id: index for index, item_id in enumerate(ids)}
        return sorted(items, key=lambda item: order.get(item.id, len(order)))


def search_items_by_media_file_ids(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    query_text: str,
    media_file_ids,
    limit: int,
    metadata_filters: dict | None = None,
):
    """Return visible lexical matches constrained to media upload file ids."""
    file_ids = list(
        dict.fromkeys(
            file_id
            for file_id in tuple(media_file_ids or ())
            if file_id
        )
    )
    if not file_ids:
        return []
    org_id = repo._organization_id(organization_id)
    pattern = f"%{query_text.lower()}%"
    item_filters, source_filters = _split_metadata_filters(metadata_filters)
    with repo._session_factory() as session:
        query = session.query(KnowledgeItemRecord).filter(
            KnowledgeItemRecord.media_file_id.in_(file_ids),
            KnowledgeItemRecord.deleted_at.is_(None),
            repo._visibility_filter(
                KnowledgeItemRecord,
                user_id=user_id, organization_id=org_id, access_level=access_level
            ),
            or_(
                KnowledgeItemRecord.content.ilike(pattern),
                KnowledgeItemRecord.summary.ilike(pattern),
                KnowledgeItemRecord.title.ilike(pattern),
            ),
        )
        query = _apply_metadata_filters(
            session,
            query,
            item_filters=item_filters,
            source_filters=source_filters,
        )
        return query.order_by(KnowledgeItemRecord.updated_at.desc()).limit(limit).all()


def list_visible_source_module_names(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    metadata_filters: dict | None = None,
):
    """Return module names for sources visible to the requester."""
    org_id = repo._organization_id(organization_id)
    with repo._session_factory() as session:
        query = session.query(KnowledgeSourceRecord.metadata_json).join(
            KnowledgeItemRecord,
            KnowledgeItemRecord.source_id == KnowledgeSourceRecord.id,
        )
        query = query.filter(
            KnowledgeSourceRecord.deleted_at.is_(None),
            KnowledgeItemRecord.deleted_at.is_(None),
            repo._visibility_filter(
                KnowledgeItemRecord,
                user_id=user_id, organization_id=org_id, access_level=access_level
            ),
        )
        source_filters = {
            key: value
            for key, value in (metadata_filters or {}).items()
            if key == "module_name"
        }
        for expression in metadata_filter_expressions(
            session,
            KnowledgeSourceRecord.metadata_json,
            source_filters,
        ):
            query = query.filter(expression)
        rows = query.distinct().all()
    module_names: list[str] = []
    seen: set[str] = set()
    for (metadata_json,) in rows:
        metadata = repo._json_load(metadata_json)
        module_name = str((metadata or {}).get("module_name") or "").strip()
        if not module_name:
            continue
        if module_name in seen:
            continue
        seen.add(module_name)
        module_names.append(module_name)
    return tuple(module_names)
