from __future__ import annotations

from fastapi import HTTPException

from democrai.core.application.auth.action import allows_public_upload
from democrai.core.application.auth.action import is_public_action
from democrai.core.application.auth.action import is_setup_only_action
from democrai.core.application.auth.service import get_user_permissions
from democrai.core.application.auth.service import is_valid_module_name
from democrai.core.application.handler.action_resolution import (
    check_action_permissions,
    resolve_core_action,
    resolve_legacy_action,
    resolve_module_name,
    resolve_registry_action,
)
from democrai.core.application.handler.dispatcher import _get_core_default_actions
from democrai.core.application.handler.services.runtime.cache import (
    safe_upload_name,
)
from democrai.core.application.services.media_uploads import store_uploaded_media
from democrai.core.infrastructure.database.media_uploads import get_media_upload_by_file_id
from democrai.core.platform.utils.mime_detection import detect_mime_type
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx
from democrai.sdk.client import SDK as ModuleSDK


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


def _core_upload_sdk(session: dict) -> ModuleSDK:
    return ModuleSDK(
        "",
        "core",
        current_path=session.get("current_path", ""),
        session=session,
    )


def _authorize_upload_action(action_name: str | None) -> None:
    normalized_action = str(action_name or "").strip()
    current = req_ctx()
    is_setup_mode = bool(getattr(app_ctx(), "setup_mode", False))
    if not normalized_action:
        if current.user is None and not is_setup_mode:
            raise HTTPException(status_code=401, detail="Authentication required")
        return

    session: dict = {}
    sdk = _core_upload_sdk(session)
    resolved = resolve_core_action(
        normalized_action,
        _get_core_default_actions(),
        sdk,
    )
    if resolved is None:
        resolved = resolve_registry_action(normalized_action, session, sdk)
    if resolved is None:
        resolved = resolve_legacy_action(normalized_action, session)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Unknown action")

    if is_setup_only_action(resolved.handler):
        if not is_setup_mode:
            raise HTTPException(status_code=403, detail="Setup mode required")
        denied = check_action_permissions(normalized_action, resolved.handler, [])
        if denied is None:
            return
        raise HTTPException(
            status_code=403,
            detail=str(denied.get("error") or "permission_denied"),
        )

    if current.user is None:
        if is_public_action(resolved.handler):
            if not allows_public_upload(resolved.handler):
                raise HTTPException(status_code=403, detail="Public upload not allowed")
            denied = check_action_permissions(normalized_action, resolved.handler, [])
            if denied is None:
                return
            raise HTTPException(
                status_code=403,
                detail=str(denied.get("error") or "permission_denied"),
            )
        raise HTTPException(status_code=401, detail="Authentication required")

    module_name = resolve_module_name(normalized_action)
    if module_name is None:
        sdk_module = getattr(resolved.sdk, "module_name", None)
        if sdk_module and sdk_module != "core":
            module_name = sdk_module
    if module_name is not None and module_name != "core":
        from democrai.core.application.auth.module_access import is_module_locked_for_user

        if is_module_locked_for_user(
            module_name,
            user_id=current.user,
            organization_id=current.organization_id,
            role=current.role,
        ):
            raise HTTPException(status_code=403, detail="Module locked")

    denied = check_action_permissions(
        normalized_action,
        resolved.handler,
        get_user_permissions(current.user),
    )
    if denied is not None:
        raise HTTPException(
            status_code=403,
            detail=str(denied.get("error") or "permission_denied"),
        )


async def upload_media_asset(
    *,
    module_name: str,
    file,
    ingest: bool = True,
    action_name: str | None = None,
):
    current = req_ctx()
    if not is_valid_module_name(module_name):
        raise HTTPException(status_code=400, detail="Invalid module name")
    is_setup_mode = app_ctx().setup_mode
    _authorize_upload_action(action_name)
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
