from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from democrai.core.application.auth.service import validate_module_name
from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION, ROLE_LEVEL_SUPER
from democrai.core.infrastructure.database.media_uploads import create_media_upload
from democrai.core.infrastructure.database.media_uploads import get_media_upload_by_file_id
from democrai.core.application.knowledge.task_progress import (
    create_extraction_task,
    fail_extraction_task,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import current_request_context_payload
from democrai.core.runtime.foundation.paths import fs_open, fs_path

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class MediaUploadResult:
    file_id: str
    storage_path: str
    stored_filename: str
    sha256: str
    size_bytes: int
    scope_type: str
    extraction_request_id: str | None = None
    background_task_id: str | None = None


def _safe_segment(value: str, default: str) -> str:
    raw = value.strip() if isinstance(value, str) else ""
    if not raw:
        return default
    sanitized = _FILENAME_SAFE_RE.sub("_", raw)
    return sanitized.strip("._-") or default


def sanitize_upload_filename(filename: str) -> str:
    base = os.path.basename(filename.strip() if isinstance(filename, str) else "")
    if not base:
        return "file.bin"
    if "." in base:
        stem, ext = os.path.splitext(base)
        safe_stem = _safe_segment(stem, "file")
        safe_ext = _safe_segment(ext.lstrip("."), "")
        if safe_ext:
            return f"{safe_stem[:120]}.{safe_ext[:20]}"
        return safe_stem[:120]
    return _safe_segment(base, "file")[:120]


def _resolve_scope_type(*, access_level: int | None, organization_id: int | None) -> str:
    resolved_access_level = access_level if access_level is not None else 99
    if int(resolved_access_level) == ROLE_LEVEL_SUPER:
        return "super"
    if int(resolved_access_level) == ROLE_LEVEL_ORGANIZATION and organization_id is not None:
        return "organization"
    return "user"


def build_media_upload_path(
    *,
    module_name: str,
    user_id: int,
    organization_id: int | None,
    access_level: int | None,
    original_filename: str,
    file_id: str,
    now: datetime | None = None,
) -> tuple[str, str, str]:
    normalized_module = validate_module_name(module_name)
    owner_user_id = _safe_segment(str(user_id), "guest")
    safe_name = sanitize_upload_filename(original_filename)
    stored_filename = f"{file_id}_{safe_name}"

    ts = now or utc_now_naive()
    scope_type = _resolve_scope_type(
        access_level=access_level,
        organization_id=organization_id,
    )
    parts = ["media", normalized_module]
    if organization_id is not None:
        parts.append(f"org_{_safe_segment(str(organization_id), 'unknown')}")
    parts.append(f"uid_{owner_user_id}")
    parts.extend(
        [
            f"{ts.year:04d}",
            f"{ts.month:02d}",
            f"{ts.day:02d}",
            stored_filename,
        ]
    )
    return "/".join(parts), stored_filename, scope_type


def _media_request_context(module_name: str, origin: str) -> dict:
    context = current_request_context_payload(origin)
    if not context:
        return {"module_name": module_name}
    if not str(context.get("module_name") or "").strip() or context.get("module_name") == "core":
        context["module_name"] = module_name
    if not str(context.get("action_name") or "").strip():
        context["action_name"] = f"{module_name}.media_upload"
    return context


def store_uploaded_media(
    *,
    module_name: str,
    original_filename: str,
    payload: bytes,
    content_type: str | None,
    user_id: int,
    organization_id: int | None,
    access_level: int | None,
    uploaded_by: int | None = None,
    ingest: bool = False,
    is_public: bool = False,
) -> MediaUploadResult:
    ctx = app_ctx()
    if getattr(ctx, "media", None) is None:
        raise RuntimeError("Media storage unavailable")
    data = bytes(payload or b"")
    if not data:
        raise ValueError("Empty payload")

    generated_file_id = uuid4().hex
    if bool(getattr(ctx, "setup_mode", False)):
        normalized_module = validate_module_name(module_name)
        safe_name = sanitize_upload_filename(original_filename)
        stored_filename = f"{generated_file_id}_{safe_name}"
        temp_root = os.path.join(
            tempfile.gettempdir(),
            "democrai_setup_uploads",
            normalized_module,
        )
        os.makedirs(fs_path(temp_root), exist_ok=True)
        persisted_path = os.path.join(temp_root, stored_filename)
        with fs_open(persisted_path, "wb") as fh:
            fh.write(data)
        digest = hashlib.sha256(data).hexdigest()
        return MediaUploadResult(
            file_id=generated_file_id,
            storage_path=str(persisted_path),
            stored_filename=stored_filename,
            sha256=digest,
            size_bytes=len(data),
            scope_type="setup",
        )

    storage_path, stored_filename, scope_type = build_media_upload_path(
        module_name=module_name,
        user_id=user_id,
        organization_id=organization_id,
        access_level=access_level,
        original_filename=original_filename,
        file_id=generated_file_id,
    )
    persisted_path = ctx.media.save(storage_path, data)
    digest = hashlib.sha256(data).hexdigest()
    normalized_module = validate_module_name(module_name)
    normalized_content_type = content_type.strip() if isinstance(content_type, str) else None
    if not normalized_content_type:
        normalized_content_type = None
    create_media_upload(
        file_id=generated_file_id,
        module_name=normalized_module,
        storage_path=str(persisted_path),
        original_filename=sanitize_upload_filename(original_filename),
        stored_filename=stored_filename,
        content_type=normalized_content_type,
        size_bytes=len(data),
        sha256=digest,
        scope_type=scope_type,
        owner_user_id=user_id,
        organization_id=organization_id,
        uploaded_by=uploaded_by if uploaded_by is not None else user_id,
        uploader_access_level=access_level,
    )
    extraction_request_id = None
    background_task_id = None
    if ingest:
        row = get_media_upload_by_file_id(file_id=generated_file_id)
        extraction_request_id = str(uuid4())
        background_task_id = create_extraction_task(
            request_id=extraction_request_id,
            filename=sanitize_upload_filename(original_filename),
            user_id=user_id,
            organization_id=organization_id,
        )
        try:
            owner_access_level = access_level if isinstance(access_level, int) else 3
            extraction_request_id = enqueue_media_extraction(
                request_id=extraction_request_id,
                media_upload_id=row.id if row is not None else None,
                module_name=normalized_module,
                storage_path=str(persisted_path),
                original_filename=sanitize_upload_filename(original_filename),
                mime_type=normalized_content_type,
                user_id=user_id,
                organization_id=organization_id,
                owner_access_level=owner_access_level,
                source_context={
                    "kind": "media_upload",
                    "module_name": normalized_module,
                    "file_id": generated_file_id,
                    "scope_type": scope_type,
                },
                metadata={
                    "module_name": normalized_module,
                    "sha256": digest,
                    "size_bytes": len(data),
                    "background_task_id": background_task_id,
                },
                is_public=bool(is_public),
                ingest_enabled=True,
            )
        except Exception as exc:
            if background_task_id is not None:
                fail_extraction_task(background_task_id, error=str(exc))
            raise
    return MediaUploadResult(
        file_id=generated_file_id,
        storage_path=str(persisted_path),
        stored_filename=stored_filename,
        sha256=digest,
        size_bytes=len(data),
        scope_type=scope_type,
        extraction_request_id=extraction_request_id,
        background_task_id=background_task_id,
    )


def enqueue_media_extraction(
    *,
    request_id: str | None = None,
    module_name: str,
    storage_path: str,
    original_filename: str,
    user_id: int,
    organization_id: int | None,
    owner_access_level: int,
    media_upload_id: int | None = None,
    mime_type: str | None = None,
    source_context: dict | None = None,
    metadata: dict | None = None,
    is_public: bool = False,
    ingest_enabled: bool = True,
    priority: int = 0,
) -> str:
    """Create a durable extraction request for an existing media object."""
    ctx = app_ctx()
    knowledge_service = getattr(ctx, "knowledge_service", None)
    repository = getattr(knowledge_service, "repository", None)
    if repository is None:
        db = getattr(ctx, "db", None)
        if db is None:
            raise RuntimeError("knowledge_repository_unavailable")
        from democrai.core.application.knowledge.repository import KnowledgeRepository

        repository = KnowledgeRepository(db.get_session)
    normalized_storage_path = storage_path.strip() if isinstance(storage_path, str) else ""
    normalized_mime_type = mime_type.strip() if isinstance(mime_type, str) else None
    if not normalized_mime_type:
        normalized_mime_type = None
    resolved_source_context = {} if source_context is None else dict(source_context)
    resolved_metadata = {} if metadata is None else dict(metadata)
    resolved_priority = 0 if priority is None else int(priority)
    normalized_module = validate_module_name(module_name)
    row = repository.enqueue_extraction_request(
        request_id=request_id,
        media_upload_id=media_upload_id,
        user_id=user_id,
        organization_id=organization_id,
        owner_access_level=owner_access_level,
        module_name=normalized_module,
        storage_path=normalized_storage_path,
        original_filename=sanitize_upload_filename(original_filename),
        mime_type=normalized_mime_type,
        source_context=resolved_source_context,
        metadata=resolved_metadata,
        request_context=_media_request_context(
            normalized_module,
            "media_upload.enqueue_extraction"
        ),
        is_public=bool(is_public),
        ingest_enabled=bool(ingest_enabled),
        priority=resolved_priority,
    )
    return str(row.id)


def can_access_media_upload(
    *,
    owner_user_id: int,
    organization_id: int | None,
    user_id: int,
    user_access_level: int | None,
    user_organization_id: int | None,
) -> bool:
    if int(user_access_level or 99) == ROLE_LEVEL_SUPER:
        return True
    if int(user_access_level or 99) == ROLE_LEVEL_ORGANIZATION:
        return bool(
            organization_id is not None
            and organization_id == user_organization_id
        )
    return owner_user_id == user_id
