"""Read-time links between uploaded media and AI pipeline context."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION
from democrai.core.application.auth.roles import ROLE_LEVEL_SUPER
from democrai.core.infrastructure.database.models import MediaUpload
from democrai.core.platform.utils.timezone import utc_now_naive


def _request_identity() -> tuple[int, int | None, int | None]:
    try:
        from democrai.core.runtime.foundation.app import req_ctx

        current = req_ctx()
    except LookupError as exc:
        raise RuntimeError("knowledge_chat_upload_context_missing_request_context") from exc
    user_id = current.user
    if user_id is None:
        raise RuntimeError("knowledge_chat_upload_context_missing_user_id")
    return (
        user_id,
        current.organization_id,
        current.access_level,
    )


def _media_upload_query(session, *, file_id: str, storage_path: str):
    query = session.query(MediaUpload)
    if file_id:
        return query.filter(MediaUpload.file_id == file_id).first()
    if storage_path:
        return query.filter(MediaUpload.storage_path == storage_path).first()
    return None


def _can_access_media_upload(
    *,
    owner_user_id: int,
    organization_id: int | None,
    user_id: int,
    user_access_level: int | None,
    user_organization_id: int | None,
) -> bool:
    resolved_access_level = user_access_level if user_access_level is not None else 99
    if resolved_access_level == ROLE_LEVEL_SUPER:
        return True
    if resolved_access_level == ROLE_LEVEL_ORGANIZATION:
        return bool(
            organization_id is not None
            and organization_id == user_organization_id
        )
    return owner_user_id == user_id


def _upsert_insert_for_dialect(table, dialect_name: str):
    if dialect_name == "postgresql":
        return pg_insert(table)
    if dialect_name == "sqlite":
        return sqlite_insert(table)
    raise RuntimeError(f"knowledge_chat_upload_context_upsert_unsupported:{dialect_name}")


def _normalized_values(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(
            dict.fromkeys(
                item.strip()
                for item in value
                if item.strip()
            )
        )
    rendered = value.strip()
    return [rendered] if rendered else []


def link_chat_upload_context(
    repo,
    *,
    file_id: str | None = None,
    storage_path: str | None = None,
    pipeline_id: str | None = None,
    context: dict | None = None,
):
    """Register the current AI pipeline context for an uploaded media file."""
    normalized_file_id = file_id.strip() if file_id is not None else ""
    normalized_storage_path = storage_path.strip() if storage_path is not None else ""
    normalized_pipeline_id = pipeline_id.strip() if pipeline_id is not None else ""
    if not normalized_file_id and not normalized_storage_path:
        raise ValueError("knowledge_chat_upload_context_upload_reference_required")
    if not normalized_pipeline_id:
        raise ValueError("knowledge_chat_upload_context_pipeline_id_required")
    context_payload = context.copy() if context is not None else {}
    context_payload["pipeline_id"] = normalized_pipeline_id

    user_id, organization_id, access_level = _request_identity()
    org_id = repo._organization_id(organization_id)
    now = utc_now_naive()
    with repo._session_factory() as session:
        media_upload = _media_upload_query(
            session,
            file_id=normalized_file_id,
            storage_path=normalized_storage_path,
        )
        if media_upload is None:
            return None
        allowed = _can_access_media_upload(
            owner_user_id=media_upload.owner_user_id,
            organization_id=media_upload.organization_id,
            user_id=user_id,
            user_access_level=access_level,
            user_organization_id=organization_id,
        )
        if not allowed:
            raise PermissionError("knowledge_chat_upload_context_forbidden")

        resolved_file_id = media_upload.file_id
        repo._attach_actor(session, user_id=user_id, organization_id=org_id)
        table = repo.KnowledgeChatUploadContextRecord.__table__
        dialect_name = session.get_bind().dialect.name
        insert_stmt = _upsert_insert_for_dialect(table, dialect_name).values(
            id=str(uuid4()),
            file_id=resolved_file_id,
            user_id=user_id,
            organization_id=org_id,
            owner_access_level=access_level if access_level is not None else 3,
            pipeline_id=normalized_pipeline_id,
            context=repo._json_dump(context_payload),
            created_at=now,
            updated_at=now,
        )
        update_values = {
            "owner_access_level": insert_stmt.excluded.owner_access_level,
            "context": insert_stmt.excluded["context"],
            "updated_at": insert_stmt.excluded.updated_at,
        }
        if org_id is None:
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["file_id", "user_id", "pipeline_id"],
                index_where=table.c.organization_id.is_(None),
                set_=update_values,
            )
        else:
            upsert_stmt = insert_stmt.on_conflict_do_update(
                index_elements=["file_id", "user_id", "organization_id", "pipeline_id"],
                index_where=table.c.organization_id.is_not(None),
                set_=update_values,
            )
        session.execute(upsert_stmt)
        session.commit()
        return (
            session.query(repo.KnowledgeChatUploadContextRecord)
            .filter(
                repo.KnowledgeChatUploadContextRecord.file_id == resolved_file_id,
                repo.KnowledgeChatUploadContextRecord.user_id == user_id,
                repo.KnowledgeChatUploadContextRecord.organization_id == org_id,
                repo.KnowledgeChatUploadContextRecord.pipeline_id == normalized_pipeline_id,
            )
            .one_or_none()
        )


def list_chat_upload_contexts(
    repo,
    *,
    user_id: int,
    organization_id: int | None,
    access_level: int,
    file_ids: list[str] | tuple[str, ...] | None = None,
    file_id: str | None = None,
    pipeline_id: str | None = None,
    limit: int | None = None,
):
    """List chat upload contexts, using one batched query for many file ids."""
    normalized_file_ids = [
        value.strip()
        for value in tuple(file_ids or ())
        if value.strip()
    ]
    if file_id:
        normalized_file_ids.append(file_id.strip())
    normalized_file_ids = list(dict.fromkeys(normalized_file_ids))
    normalized_pipeline_ids = _normalized_values(pipeline_id)
    with repo._session_factory() as session:
        query = session.query(repo.KnowledgeChatUploadContextRecord)
        query = query.filter(
            repo.KnowledgeChatUploadContextRecord.user_id == user_id,
            repo.KnowledgeChatUploadContextRecord.organization_id
            == repo._organization_id(organization_id),
        )
        if normalized_file_ids:
            query = query.filter(
                repo.KnowledgeChatUploadContextRecord.file_id.in_(normalized_file_ids)
            )
        if normalized_pipeline_ids:
            query = query.filter(
                repo.KnowledgeChatUploadContextRecord.pipeline_id.in_(
                    normalized_pipeline_ids
                )
            )
        query = query.order_by(repo.KnowledgeChatUploadContextRecord.updated_at.desc())
        if limit is not None:
            query = query.limit(max(1, limit))
        return query.all()
