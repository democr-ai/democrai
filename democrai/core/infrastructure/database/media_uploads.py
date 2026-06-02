from __future__ import annotations

from datetime import datetime

from democrai.core.infrastructure.database import session_scope
from democrai.core.infrastructure.database.models import MediaUpload
from democrai.core.platform.utils.identity import to_optional_int, to_required_int
from democrai.core.platform.utils.timezone import utc_now_naive


def create_media_upload(
    *,
    file_id: str,
    module_name: str,
    storage_path: str,
    original_filename: str,
    stored_filename: str,
    content_type: str | None,
    size_bytes: int,
    sha256: str,
    scope_type: str,
    owner_user_id: int,
    organization_id: int | None,
    uploaded_by: int,
    uploader_access_level: int | None,
) -> None:
    now = utc_now_naive()
    with session_scope() as session:
        session.add(
            MediaUpload(
                file_id=file_id,
                module_name=module_name,
                storage_path=storage_path,
                original_filename=original_filename,
                stored_filename=stored_filename,
                content_type=content_type,
                size_bytes=size_bytes,
                sha256=sha256,
                scope_type=scope_type,
                owner_user_id=to_required_int(owner_user_id, "owner_user_id"),
                organization_id=to_optional_int(organization_id),
                uploaded_by=to_required_int(uploaded_by, "uploaded_by"),
                uploader_access_level=uploader_access_level,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()


def get_media_upload_by_file_id(*, file_id: str) -> MediaUpload | None:
    with session_scope() as session:
        return session.query(MediaUpload).filter(MediaUpload.file_id == file_id).first()


def get_media_upload_by_storage_path(*, storage_path: str) -> MediaUpload | None:
    with session_scope() as session:
        return (
            session.query(MediaUpload)
            .filter(MediaUpload.storage_path == storage_path)
            .first()
        )


def update_media_upload_storage_path(
    *,
    old_storage_path: str,
    new_storage_path: str,
    stored_filename: str | None = None,
) -> bool:
    with session_scope() as session:
        row = (
            session.query(MediaUpload)
            .filter(MediaUpload.storage_path == old_storage_path)
            .first()
        )
        if row is None:
            return False
        row.storage_path = new_storage_path
        if stored_filename is not None:
            row.stored_filename = stored_filename
        row.updated_at = utc_now_naive()
        session.commit()
        return True


def delete_media_upload_by_storage_path(*, storage_path: str) -> bool:
    with session_scope() as session:
        row = (
            session.query(MediaUpload)
            .filter(MediaUpload.storage_path == storage_path)
            .first()
        )
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True


def list_media_uploads(
    *,
    module_name: str | None = None,
    scope_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    organization_id: int | None = None,
    owner_user_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[MediaUpload], int]:
    safe_page = max(page, 1)
    safe_page_size = max(min(page_size, 200), 1)
    offset = (safe_page - 1) * safe_page_size

    with session_scope() as session:
        query = session.query(MediaUpload)
        if module_name is not None:
            query = query.filter(MediaUpload.module_name == module_name)
        if scope_type is not None:
            query = query.filter(MediaUpload.scope_type == scope_type)
        if created_from is not None:
            query = query.filter(MediaUpload.created_at >= created_from)
        if created_to is not None:
            query = query.filter(MediaUpload.created_at <= created_to)
        if organization_id is not None:
            query = query.filter(
                MediaUpload.organization_id == to_optional_int(organization_id)
            )
        if owner_user_id is not None:
            query = query.filter(
                MediaUpload.owner_user_id
                == to_required_int(owner_user_id, "owner_user_id")
            )

        total = int(query.count())
        rows = (
            query.order_by(MediaUpload.created_at.desc())
            .offset(offset)
            .limit(safe_page_size)
            .all()
        )
        return rows, total
