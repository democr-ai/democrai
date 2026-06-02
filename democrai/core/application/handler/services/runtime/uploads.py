from __future__ import annotations

from fastapi import HTTPException

from democrai.core.application.auth.service import is_valid_module_name
from democrai.core.application.handler.services.runtime.cache import (
    safe_upload_name,
)
from democrai.core.application.services.media_uploads import store_uploaded_media
from democrai.core.infrastructure.database.media_uploads import get_media_upload_by_file_id
from democrai.core.platform.utils.mime_detection import detect_mime_type
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx


def _media_upload_payload(row) -> dict[str, object]:
    return {
        "id": row.id,
        "file_id": row.file_id,
        "module_name": row.module_name,
        "storage_path": row.storage_path,
        "original_filename": row.original_filename,
        "stored_filename": row.stored_filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "scope_type": row.scope_type,
        "owner_user_id": row.owner_user_id,
        "organization_id": row.organization_id,
        "uploaded_by": row.uploaded_by,
        "uploader_access_level": row.uploader_access_level,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


async def upload_media_asset(*, module_name: str, file, ingest: bool = True):
    current = req_ctx()
    if not is_valid_module_name(module_name):
        raise HTTPException(status_code=400, detail="Invalid module name")
    is_setup_mode = app_ctx().setup_mode
    if current.user is None and not is_setup_mode:
        raise HTTPException(status_code=401, detail="Authentication required")
    user_id = current.user
    if user_id is None:
        user_id = 0
    filename = safe_upload_name(file.filename or "upload.bin")
    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        detected = detect_mime_type(
            data=payload,
            filename=filename,
            declared_content_type=getattr(file, "content_type", None),
        )
        uploaded = store_uploaded_media(
            module_name=module_name,
            original_filename=filename,
            payload=payload,
            content_type=detected.mime_type,
            user_id=user_id,
            organization_id=current.organization_id,
            access_level=current.access_level,
            uploaded_by=user_id,
            ingest=ingest,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Media upload failed: {exc}") from exc
    if is_setup_mode:
        return {
            "module_name": module_name,
            "file_id": uploaded.file_id,
            "storage_path": uploaded.storage_path,
            "size_bytes": uploaded.size_bytes,
            "content_type": detected.mime_type or "application/octet-stream",
            "original_filename": filename,
            "stored_filename": uploaded.stored_filename,
            "scope_type": uploaded.scope_type,
            "sha256": uploaded.sha256,
            "extraction_request_id": None,
            "background_task_id": None,
        }
    row = get_media_upload_by_file_id(file_id=uploaded.file_id)
    if row is not None:
        payload = _media_upload_payload(row)
        payload["extraction_request_id"] = uploaded.extraction_request_id
        payload["background_task_id"] = uploaded.background_task_id
        return payload
    return {
        "module_name": module_name,
        "file_id": uploaded.file_id,
        "storage_path": uploaded.storage_path,
        "size_bytes": uploaded.size_bytes,
        "content_type": detected.mime_type or "application/octet-stream",
        "original_filename": filename,
        "extraction_request_id": uploaded.extraction_request_id,
        "background_task_id": uploaded.background_task_id,
    }
