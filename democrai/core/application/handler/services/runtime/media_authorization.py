from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from fastapi import HTTPException

from democrai.core.application.handler.services.runtime.access import (
    check_external_media_access,
    external_media_fetch_access,
    network_policy_context,
)
from democrai.core.application.handler.services.runtime.media_targets import MediaTarget
from democrai.core.application.services.media_uploads import can_access_media_upload
from democrai.core.infrastructure.database.media_uploads import (
    get_media_upload_by_file_id,
    get_media_upload_by_storage_path,
)
from democrai.core.platform.utils.debug import debug_media_flow
from democrai.core.runtime.foundation.app import app_ctx, req_ctx


@dataclass(frozen=True)
class MediaAuthorization:
    upload_record: Any | None = None
    external_access: Any | None = None


def authorize_media_target(target: MediaTarget) -> MediaAuthorization:
    if target.kind in {"module_asset", "engine_asset", "extractor_asset"}:
        authorize_asset_target(target)
        return MediaAuthorization()
    if target.kind == "upload_file_id":
        return authorize_uploaded_media_by_file_id(target)
    if target.kind == "upload_storage_path":
        return authorize_uploaded_media_by_storage_path(target)
    if target.kind == "remote":
        return authorize_remote_media_target(target, remote_url=target.remote_url)
    raise HTTPException(status_code=400, detail="Unsupported media target")


def authorize_asset_target(target: MediaTarget) -> None:
    normalized = target.relative_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("assets/"):
        normalized = normalized[len("assets/") :].strip().lstrip("/")
    if normalized.startswith("protected/") and req_ctx().user is None:
        raise HTTPException(status_code=401, detail="Authentication required")


def authorize_uploaded_media_by_file_id(target: MediaTarget) -> MediaAuthorization:
    file_id = target.file_id
    if not file_id:
        raise HTTPException(status_code=400, detail="file_id is required")
    record = get_media_upload_by_file_id(file_id=file_id)
    return authorize_uploaded_media_record(record)


def authorize_uploaded_media_by_storage_path(target: MediaTarget) -> MediaAuthorization:
    storage_path = target.storage_path
    if not storage_path:
        raise HTTPException(status_code=400, detail="storage_path is required")
    record = get_media_upload_by_storage_path(storage_path=storage_path)
    return authorize_uploaded_media_record(record)


def authorize_uploaded_media_record(record: Any | None) -> MediaAuthorization:
    if record is None:
        raise HTTPException(status_code=404, detail="Uploaded file not found")
    current = req_ctx()
    allowed = can_access_media_upload(
        owner_user_id=record.owner_user_id,
        organization_id=record.organization_id,
        user_id=current.user or 0,
        user_access_level=current.access_level,
        user_organization_id=current.organization_id,
    )
    if not allowed:
        raise HTTPException(
            status_code=403, detail="You do not have access to this file"
        )
    return MediaAuthorization(upload_record=record)


def authorize_remote_media_target(
    target: MediaTarget,
    *,
    remote_url: str | None = None,
    session_key: str | None = None,
) -> MediaAuthorization:
    current = req_ctx()
    module_name = target.requester_module
    url = remote_url if remote_url is not None else target.remote_url
    access_check = check_external_media_access(
        module_name=module_name,
        url=url,
        user_id=current.user,
        organization_id=current.organization_id,
        session_key=session_key if session_key is not None else current.session_key,
    )
    if not getattr(access_check, "allowed", False):
        code = getattr(access_check, "code", "") or ""
        if code == "not_enabled":
            notify_pending_access_to_super_users()
        debug_media_flow(
            "media_authorization.remote.denied",
            module_name=module_name,
            url=url,
            code=code,
            message=getattr(access_check, "message", "") or "",
        )
        return MediaAuthorization(external_access=access_check)
    debug_media_flow(
        "media_authorization.remote.allowed",
        module_name=module_name,
        url=url,
        code=getattr(access_check, "code", ""),
    )
    return MediaAuthorization(external_access=access_check)


@contextmanager
def authorize_remote_media_request(
    target: MediaTarget, *, remote_url: str, session_key: str | None
) -> Iterator[MediaAuthorization]:
    current = req_ctx()
    module_name = target.requester_module
    with network_policy_context(
        subject_name=module_name,
        access=external_media_fetch_access(
            module_name=module_name,
            url=remote_url,
        ),
        user_id=current.user,
        organization_id=current.organization_id,
        session_key=session_key,
    ):
        yield authorize_remote_media_target(
            target,
            remote_url=remote_url,
            session_key=session_key,
        )


def notify_pending_access_to_super_users() -> None:
    from democrai.core.application.auth.roles import is_super_role
    from democrai.core.infrastructure.database.access_policy import get_pending_access_requests
    from democrai.core.infrastructure.network.protocol.auth import push_notifications_update

    network = getattr(app_ctx(), "network", None)
    registry = getattr(app_ctx(), "connection_registry", None)
    if network is None or registry is None:
        return

    count = len(get_pending_access_requests())
    seen_users: set[int] = set()
    for _, (user_id, role, organization_id, _) in list(
        getattr(network, "_authenticated_clients", {}).items()
    ):
        if (
            user_id is None
            or organization_id
            or not is_super_role(role)
            or user_id in seen_users
        ):
            continue
        seen_users.add(user_id)
        for bus, client_id in registry.get_connections(user_id):
            try:
                push_notifications_update(bus, client_id, count=count)
            except Exception:
                continue
