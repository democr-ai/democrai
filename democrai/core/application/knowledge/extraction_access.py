from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import and_
from sqlalchemy import func
from sqlalchemy import or_

from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION
from democrai.core.application.auth.roles import ROLE_LEVEL_SUPER
from democrai.core.application.knowledge.configuration import (
    get_knowledge_runtime_config,
)
from democrai.core.application.knowledge.repository import KnowledgeRepository
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.platform.utils.identity import to_optional_int


def get_extraction_status(
    *,
    request_id: str,
    user_id: int,
    organization_id: int | None,
) -> dict[str, Any] | None:
    """Return scoped status for one extraction request."""
    if not request_id:
        raise ValueError("request_id is required")
    repo = KnowledgeRepository(SessionLocal)
    org_id = to_optional_int(organization_id)
    knowledge_config = get_knowledge_runtime_config()
    with SessionLocal() as session:
        request = (
            session.query(repo.KnowledgeExtractionRequestRecord)
            .filter(
                repo.KnowledgeExtractionRequestRecord.id == request_id,
                repo.KnowledgeExtractionRequestRecord.user_id == user_id,
                repo.KnowledgeExtractionRequestRecord.organization_id == org_id,
            )
            .first()
        )
        if request is None:
            return None
        document = (
            session.query(repo.KnowledgeExtractedItemRecord)
            .filter(
                repo.KnowledgeExtractedItemRecord.extraction_request_id == request_id,
                repo.KnowledgeExtractedItemRecord.user_id == user_id,
                repo.KnowledgeExtractedItemRecord.organization_id == org_id,
                repo.KnowledgeExtractedItemRecord.item_type == "document",
            )
            .order_by(repo.KnowledgeExtractedItemRecord.ordinal.asc())
            .first()
        )
        ingestion = (
            session.query(repo.KnowledgeIngestionRequestRecord)
            .filter(
                repo.KnowledgeIngestionRequestRecord.extraction_request_id
                == request_id,
                repo.KnowledgeIngestionRequestRecord.user_id == user_id,
                repo.KnowledgeIngestionRequestRecord.organization_id == org_id,
            )
            .order_by(repo.KnowledgeIngestionRequestRecord.created_at.desc())
            .first()
        )
        embedded_item = (
            session.query(repo.KnowledgeItemRecord)
            .filter(
                repo.KnowledgeItemRecord.user_id == user_id,
                repo.KnowledgeItemRecord.organization_id == org_id,
                repo.KnowledgeItemRecord.id.like(f"{request_id}:%"),
                repo.KnowledgeItemRecord.vector_status.in_(("ready", "synced")),
            )
            .first()
        )
        embedding_ready = (
            bool(knowledge_config.get("enabled")) and embedded_item is not None
        )
        return {
            "request_id": request.id,
            "extraction_status": request.status,
            "ready": request.status == "completed",
            "knowledge_enabled": bool(knowledge_config.get("enabled")),
            "markdown_ready": bool(
                document is not None and str(document.content_text or "").strip()
            ),
            "embedding_ready": embedding_ready,
            "document_ingestion_status": (
                document.ingestion_status if document is not None else "missing"
            ),
            "ingestion_request_status": (
                ingestion.status if ingestion is not None else "missing"
            ),
            "extractor_id": request.extractor_id,
            "mime_type": request.mime_type,
            "filename": request.original_filename,
            "last_error": request.last_error,
            "created_at": _iso_datetime(request.created_at),
            "started_at": _iso_datetime(request.started_at),
            "completed_at": _iso_datetime(request.completed_at),
        }


def list_extraction_statuses(
    *,
    request_ids: list[str],
    user_id: int,
    organization_id: int | None,
) -> dict[str, Any]:
    """Return scoped status records for multiple extraction requests."""
    resolved_ids = [item for item in request_ids if item]
    items: list[dict[str, Any]] = []
    found_ids: set[str] = set()
    for request_id in resolved_ids:
        status = get_extraction_status(
            request_id=request_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if status is None:
            continue
        items.append(status)
        found_ids.add(request_id)
    return {
        "items": items,
        "missing_request_ids": [
            request_id for request_id in resolved_ids if request_id not in found_ids
        ],
    }


def get_extracted_document(
    *,
    request_id: str,
    user_id: int,
    organization_id: int | None,
) -> dict[str, Any] | None:
    """Return the complete extracted markdown document for one request."""
    if not request_id:
        raise ValueError("request_id is required")
    repo = KnowledgeRepository(SessionLocal)
    org_id = to_optional_int(organization_id)
    with SessionLocal() as session:
        request = (
            session.query(repo.KnowledgeExtractionRequestRecord)
            .filter(
                repo.KnowledgeExtractionRequestRecord.id == request_id,
                repo.KnowledgeExtractionRequestRecord.user_id == user_id,
                repo.KnowledgeExtractionRequestRecord.organization_id == org_id,
            )
            .first()
        )
        if request is None:
            return None
        document = (
            session.query(repo.KnowledgeExtractedItemRecord)
            .filter(
                repo.KnowledgeExtractedItemRecord.extraction_request_id == request_id,
                repo.KnowledgeExtractedItemRecord.user_id == user_id,
                repo.KnowledgeExtractedItemRecord.organization_id == org_id,
                repo.KnowledgeExtractedItemRecord.item_type == "document",
            )
            .order_by(repo.KnowledgeExtractedItemRecord.ordinal.asc())
            .first()
        )
        chunks_count = (
            session.query(repo.KnowledgeExtractedItemRecord)
            .filter(
                repo.KnowledgeExtractedItemRecord.extraction_request_id == request_id,
                repo.KnowledgeExtractedItemRecord.user_id == user_id,
                repo.KnowledgeExtractedItemRecord.organization_id == org_id,
                repo.KnowledgeExtractedItemRecord.item_type == "chunk",
            )
            .count()
        )
        return {
            "request_id": request.id,
            "extraction_status": request.status,
            "title": (
                document.title if document is not None else request.original_filename
            ),
            "mime_type": request.mime_type,
            "markdown_content": (document.content_text if document is not None else ""),
            "chunks_count": chunks_count,
            "metadata": (
                repo._json_load(document.metadata_json) if document is not None else {}
            ),
        }


_BLOCK_PREVIEW_MAX_CHARS = 160
_BLOCK_PREVIEW_MIN_CHARS = 40


def _block_preview(text: Any, limit: int) -> str:
    resolved = str(text or "").strip().replace("\n", " ")
    if len(resolved) <= limit:
        return resolved
    return resolved[:limit].rstrip() + "…"


def _index_entry(repo: Any, row: Any, kind: str, preview_limit: int) -> dict[str, Any]:
    """Index entry for a block: the cached ``summary`` when present (semantic
    map), otherwise a short ``preview`` of the content."""
    content = _extracted_item_text(repo, row, kind)
    meta = repo._json_load(row.metadata_json) if row.metadata_json else {}
    summary = str(meta.get("summary") or "") if isinstance(meta, dict) else ""
    entry: dict[str, Any] = {
        "index": int(row.ordinal),
        "title": row.title,
        "chars": len(content),
    }
    if summary:
        entry["summary"] = summary
    else:
        entry["preview"] = _block_preview(content, preview_limit)
    return entry


_READABLE_KINDS = ("chunk", "table", "formula", "image")


def _extracted_item_text(repo: Any, row: Any, kind: str) -> str:
    """Markdown/text of an extracted item: ``content_text`` for document/chunk,
    the ``text`` of the JSON payload for table/formula/image."""
    if kind in ("document", "chunk"):
        return str(row.content_text or "")
    content = repo._json_load(row.content_json) if row.content_json else {}
    if isinstance(content, dict):
        return str(content.get("text") or content.get("markdown") or "")
    return ""


def list_extracted_blocks(
    *,
    request_id: str,
    user_id: int,
    organization_id: int | None,
    max_chars: int,
    blocks: list[int] | None = None,
    kind: str = "chunk",
) -> dict[str, Any] | None:
    """Read an extracted document for analysis, budget-aware and scoped.

    Every return carries ``counts`` (item count per ``item_type`` — e.g. how
    many ``table`` items exist), so the count of something does not require
    reading anything.

    - **index** (``blocks is None``): per ``kind="chunk"``, se il ``document``
      (testo intero) sta in ``max_chars`` lo ritorna tutto (``mode="full"``),
      altrimenti l'indice dei chunk. Per gli altri ``kind`` (``table`` …),
      l'indice degli item di quel tipo: ``ordinal`` + preview corto.
    - **blocks**: ritorna il contenuto degli item ``kind`` con quegli
      ``ordinal``, in ordine, fino a ``max_chars``; gli esclusi per spazio in
      ``not_returned`` (niente troncamento silenzioso), gli inesistenti in
      ``missing``.
    """
    if not request_id:
        raise ValueError("request_id is required")
    resolved_kind = kind if kind in _READABLE_KINDS else "chunk"
    budget = max(256, int(max_chars))
    repo = KnowledgeRepository(SessionLocal)
    org_id = to_optional_int(organization_id)
    item = repo.KnowledgeExtractedItemRecord
    scope = lambda query: query.filter(  # noqa: E731
        item.extraction_request_id == request_id,
        item.user_id == user_id,
        item.organization_id == org_id,
    )
    with SessionLocal() as session:
        request = (
            session.query(repo.KnowledgeExtractionRequestRecord)
            .filter(
                repo.KnowledgeExtractionRequestRecord.id == request_id,
                repo.KnowledgeExtractionRequestRecord.user_id == user_id,
                repo.KnowledgeExtractionRequestRecord.organization_id == org_id,
            )
            .first()
        )
        if request is None:
            return None

        counts = {
            str(item_type): int(total)
            for item_type, total in scope(session.query(item.item_type, func.count()))
            .group_by(item.item_type)
            .all()
        }
        title = request.original_filename

        kind_query = (
            scope(session.query(item))
            .filter(item.item_type == resolved_kind)
            .order_by(item.ordinal.asc())
        )

        if blocks is not None:
            wanted = [int(value) for value in blocks]
            rows = kind_query.filter(item.ordinal.in_(wanted)).all()
            present = {int(row.ordinal) for row in rows}
            returned: list[dict[str, Any]] = []
            not_returned: list[int] = []
            used = 0
            for row in rows:
                content = _extracted_item_text(repo, row, resolved_kind)
                if returned and used + len(content) > budget:
                    not_returned.append(int(row.ordinal))
                    continue
                returned.append(
                    {"index": int(row.ordinal), "title": row.title, "content": content}
                )
                used += len(content)
            return {
                "request_id": request.id,
                "mode": "blocks",
                "kind": resolved_kind,
                "counts": counts,
                "returned": returned,
                "not_returned": sorted(set(not_returned)),
                "missing": sorted(value for value in wanted if value not in present),
                "budget_chars": budget,
            }

        if resolved_kind == "chunk":
            document = (
                scope(session.query(item))
                .filter(item.item_type == "document")
                .order_by(item.ordinal.asc())
                .first()
            )
            document_content = (
                str(document.content_text or "") if document is not None else ""
            )
            title = document.title if document is not None else title
            if document_content and len(document_content) <= budget:
                return {
                    "request_id": request.id,
                    "mode": "full",
                    "kind": resolved_kind,
                    "counts": counts,
                    "title": title,
                    "content": document_content,
                }

        rows = kind_query.all()
        total_blocks = len(rows)
        per_preview = _BLOCK_PREVIEW_MAX_CHARS
        if total_blocks > 0:
            per_preview = max(
                _BLOCK_PREVIEW_MIN_CHARS,
                min(_BLOCK_PREVIEW_MAX_CHARS, budget // total_blocks),
            )
        return {
            "request_id": request.id,
            "mode": "index",
            "kind": resolved_kind,
            "counts": counts,
            "title": title,
            "total_blocks": total_blocks,
            "blocks": [
                _index_entry(repo, row, resolved_kind, per_preview) for row in rows
            ],
        }


def summary_source_hash(text: str) -> str:
    """Invalidation hash for a cached summary: bound to the summarized text."""
    return hashlib.sha1((text or "").encode("utf-8")).hexdigest()


def list_extracted_items_for_summary(
    *,
    request_id: str,
    user_id: int,
    organization_id: int | None,
    item_type: str = "chunk",
) -> list[dict[str, Any]]:
    """Items of ``item_type`` in order, each with its text and cached summary.

    ``fresh`` is True when a stored summary still matches the current text
    (``summary_hash`` == hash of the text), so the caller summarizes only the
    stale ones.
    """
    if not request_id:
        raise ValueError("request_id is required")
    repo = KnowledgeRepository(SessionLocal)
    org_id = to_optional_int(organization_id)
    item = repo.KnowledgeExtractedItemRecord
    out: list[dict[str, Any]] = []
    with SessionLocal() as session:
        rows = (
            session.query(item)
            .filter(
                item.extraction_request_id == request_id,
                item.user_id == user_id,
                item.organization_id == org_id,
                item.item_type == item_type,
            )
            .order_by(item.ordinal.asc())
            .all()
        )
        for row in rows:
            content = _extracted_item_text(repo, row, item_type)
            meta = repo._json_load(row.metadata_json) or {}
            summary = str(meta.get("summary") or "")
            fresh = bool(summary) and str(
                meta.get("summary_hash") or ""
            ) == summary_source_hash(content)
            out.append(
                {
                    "id": row.id,
                    "ordinal": int(row.ordinal),
                    "title": row.title,
                    "content": content,
                    "summary": summary,
                    "fresh": fresh,
                }
            )
    return out


def store_item_summary(
    *,
    item_id: str,
    user_id: int,
    organization_id: int | None,
    summary: str,
) -> bool:
    """Persist a summary on one extracted item, in ``metadata_json``, bound to
    the hash of ``source_text`` for invalidation. Returns False if not found."""
    repo = KnowledgeRepository(SessionLocal)
    org_id = to_optional_int(organization_id)
    item = repo.KnowledgeExtractedItemRecord
    with SessionLocal() as session:
        row = (
            session.query(item)
            .filter(
                item.id == item_id,
                item.user_id == user_id,
                item.organization_id == org_id,
            )
            .first()
        )
        if row is None:
            return False
        meta = repo._json_load(row.metadata_json) or {}
        meta["summary"] = str(summary or "")
        meta["summary_hash"] = summary_source_hash(
            _extracted_item_text(repo, row, row.item_type)
        )
        row.metadata_json = repo._json_dump(meta)
        session.commit()
        return True


def search_extracted_items(
    *,
    query_text: str,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    limit: int,
    extraction_request_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Search completed extracted document items inside the caller scope."""
    resolved_query = query_text.strip()
    if not resolved_query:
        raise ValueError("query_text is required")
    request_ids = [item for item in (extraction_request_ids or []) if item]
    max_rows = max(1, min(20, limit))
    repo = KnowledgeRepository(SessionLocal)
    org_id = to_optional_int(organization_id)
    pattern = f"%{resolved_query}%"
    with SessionLocal() as session:
        item = repo.KnowledgeExtractedItemRecord
        request = repo.KnowledgeExtractionRequestRecord
        query = (
            session.query(item, request)
            .join(request, request.id == item.extraction_request_id)
            .filter(
                request.status == "completed",
                item.content_text.ilike(pattern),
            )
        )
        if request_ids:
            query = query.filter(item.extraction_request_id.in_(request_ids))
        resolved_access_level = access_level
        own_items = item.user_id == user_id
        if resolved_access_level <= ROLE_LEVEL_SUPER:
            visible_items = or_(
                own_items,
                and_(
                    item.is_public == 1,
                    request.owner_access_level > resolved_access_level,
                ),
            )
        elif resolved_access_level == ROLE_LEVEL_ORGANIZATION:
            visible_items = or_(
                own_items,
                and_(
                    request.organization_id == org_id,
                    item.is_public == 1,
                    request.owner_access_level > resolved_access_level,
                ),
            )
        else:
            visible_items = own_items
        query = query.filter(visible_items)
        rows = (
            query.order_by(request.completed_at.desc(), item.ordinal.asc())
            .limit(max_rows)
            .all()
        )
        matches = []
        for extracted, extraction_request in rows:
            metadata = repo._json_load(extracted.metadata_json)
            content = extracted.content_text or ""
            matches.append(
                {
                    "item_id": extracted.id,
                    "extraction_request_id": extracted.extraction_request_id,
                    "kind": extracted.item_type,
                    "title": extracted.title or extraction_request.original_filename,
                    "content": content,
                    "summary": content[:500],
                    "score": None,
                    "metadata": metadata,
                    "mime_type": extraction_request.mime_type,
                    "filename": extraction_request.original_filename,
                }
            )
    return {"matches": matches}


def _iso_datetime(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    if callable(isoformat):
        return str(isoformat())
    return str(value)
