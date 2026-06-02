from __future__ import annotations

import asyncio
import threading
import uuid
from typing import Any

from democrai.core.application.access_policy import AccessDecision
from democrai.core.application.access_policy import AccessPolicyService
from democrai.core.application.access_policy import AccessRequest
from democrai.core.application.access_policy import AccessScope
from democrai.core.application.access_policy import ResourceType
from democrai.core.application.auth.roles import is_super_role
from democrai.core.application.auth.service import get_user_access_profile
from democrai.core.application.services.external_access_resume import (
    decrypt_resume_context,
)
from democrai.core.application.services.external_access_resume import (
    encrypt_resume_context,
)
from democrai.core.infrastructure.database import access_policy as access_policy_store
from democrai.core.platform.utils.debug import debug_media_flow
from democrai.core.platform.utils.debug import debug_os_sandbox_flow
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.runtime.foundation.app import app_ctx, module_name_from_action


EXTERNAL_ACCESS_APPROVE_PERMISSION = "auth.approve_url"
EXTERNAL_RESOURCE_NETWORK = ResourceType.NETWORK.value
EXTERNAL_RESOURCE_FILESYSTEM = ResourceType.FILESYSTEM.value
EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY = ResourceType.SYSTEM_DEPENDENCY.value
_CACHE_LOCK = threading.Lock()
_NEGATIVE_CACHE_MAX = 4096
EXTERNAL_ACCESS_CACHE_STREAM_ID = "core.external_access.cache.events"
EXTERNAL_ACCESS_CACHE_EVENT_NAME = "external_access.cache.changed"
_PROCESSED_CACHE_EVENT_IDS: set[str] = set()
_PROCESSED_CACHE_EVENT_IDS_ORDER: list[str] = []
_MAX_PROCESSED_CACHE_EVENT_IDS = 2048


class ExternalAccessApprovalRequired(PermissionError):
    def __init__(
        self,
        *,
        subject_type: str,
        subject_name: str,
        resource_type: str,
        operation: str,
        target: str,
        message: str,
        code: str = "",
    ) -> None:
        super().__init__(message)
        self.subject_type = subject_type
        self.subject_name = subject_name
        self.resource_type = resource_type
        self.operation = operation
        self.target = target
        self.message = message
        self.code = code


def _service() -> AccessPolicyService:
    return AccessPolicyService(access_policy_store)


def _runtime_node_id() -> str:
    ctx = app_ctx()
    configured = ctx.node_id
    if configured:
        return configured
    cfg = ctx.config
    if cfg is not None:
        configured = cfg.get("network.node_id", "")
        if configured:
            ctx.node_id = configured
            return configured
    ctx.node_id = SERVER_NAME
    return SERVER_NAME


def _remember_cache_event_id(event_id: str) -> None:
    if not event_id or event_id in _PROCESSED_CACHE_EVENT_IDS:
        return
    _PROCESSED_CACHE_EVENT_IDS.add(event_id)
    _PROCESSED_CACHE_EVENT_IDS_ORDER.append(event_id)
    if len(_PROCESSED_CACHE_EVENT_IDS_ORDER) <= _MAX_PROCESSED_CACHE_EVENT_IDS:
        return
    stale = _PROCESSED_CACHE_EVENT_IDS_ORDER.pop(0)
    _PROCESSED_CACHE_EVENT_IDS.discard(stale)


def _approval_cache() -> dict[str, Any]:
    ctx = app_ctx()
    cache = getattr(ctx, "external_access_cache", None)
    if isinstance(cache, dict):
        return cache
    with _CACHE_LOCK:
        cache = getattr(ctx, "external_access_cache", None)
        if isinstance(cache, dict):
            return cache
        created = {
            "approvals": set(),
            "denied": set(),
            "negative": {},
        }
        for row in access_policy_store.list_access_approvals():
            created["approvals"].add(
                (
                    row.get("subject_type"),
                    row.get("subject_name"),
                    row.get("resource_type"),
                    row.get("operation"),
                    row.get("normalized_target"),
                    row.get("scope"),
                    row.get("session_key") or None,
                )
            )
        for row in access_policy_store.list_denied_access_requests():
            created["denied"].add(
                (
                    row.get("subject_type"),
                    row.get("subject_name"),
                    row.get("resource_type"),
                    row.get("operation"),
                    row.get("normalized_target"),
                )
            )
        ctx.external_access_cache = created
        return created


def _reset_approval_cache() -> None:
    with _CACHE_LOCK:
        try:
            delattr(app_ctx(), "external_access_cache")
        except AttributeError:
            pass


def _approval_key(request: AccessRequest, scope: AccessScope) -> tuple:
    return (
        request.subject.subject_type,
        request.subject.subject_name,
        request.resource.resource_type.value,
        request.resource.operation.value,
        request.resource.normalized_target,
        scope.scope_type,
        scope.session_key,
    )


def _denied_key(request: AccessRequest) -> tuple:
    return (
        request.subject.subject_type,
        request.subject.subject_name,
        request.resource.resource_type.value,
        request.resource.operation.value,
        request.resource.normalized_target,
    )


def _negative_key(request: AccessRequest) -> tuple:
    return (
        request.subject.subject_type,
        request.subject.subject_name,
        request.resource.resource_type.value,
        request.resource.operation.value,
        request.resource.normalized_target,
        request.origin.session_key,
    )


def _cached_decision(request: AccessRequest) -> AccessDecision | None:
    cache = _approval_cache()
    if _approval_key(request, AccessScope.permanent()) in cache["approvals"]:
        return AccessDecision.allow(
            "permanent_approval",
            "Access enabled by permanent approval.",
        )
    if request.origin.session_key:
        if (
            _approval_key(
                request,
                AccessScope.session(request.origin.session_key),
            )
            in cache["approvals"]
        ):
            return AccessDecision.allow(
                "session_approval",
                "Access enabled for current session.",
            )
    if _denied_key(request) in cache["denied"]:
        return AccessDecision.deny("denied", "Access denied.")
    cached_negative = cache["negative"].get(_negative_key(request))
    if cached_negative == "not_enabled":
        return AccessDecision.require_approval(
            "not_enabled",
            "Access requires approval.",
        )
    return None


def _cache_decision(
    request: AccessRequest,
    decision: AccessDecision,
    *,
    register_request: bool,
) -> None:
    cache = _approval_cache()
    if decision.allowed:
        scope = (
            AccessScope.session(request.origin.session_key)
            if decision.code == "session_approval" and request.origin.session_key
            else AccessScope.permanent()
        )
        cache["approvals"].add(_approval_key(request, scope))
        return
    if decision.code == "denied":
        cache["denied"].add(_denied_key(request))
        return
    if register_request:
        return
    negative = cache["negative"]
    key = _negative_key(request)
    if key not in negative and len(negative) >= _NEGATIVE_CACHE_MAX:
        try:
            negative.pop(next(iter(negative)))
        except Exception:
            negative.clear()
    decision_code = decision.code.strip()
    negative[key] = decision_code if decision_code else "not_enabled"


def _cache_approval(request: AccessRequest, scope: AccessScope) -> None:
    _approval_cache()["approvals"].add(_approval_key(request, scope))


def _cache_denial(request: AccessRequest) -> None:
    cache = _approval_cache()
    cache["denied"].add(_denied_key(request))
    cache["negative"].pop(_negative_key(request), None)


def _cache_event_payload(
    *,
    operation: str,
    request: AccessRequest,
    scope: AccessScope | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_name": EXTERNAL_ACCESS_CACHE_EVENT_NAME,
        "source_node_id": _runtime_node_id(),
        "operation": operation,
        "subject_type": request.subject.subject_type,
        "subject_name": request.subject.subject_name,
        "resource_type": request.resource.resource_type.value,
        "resource_operation": request.resource.operation.value,
        "normalized_target": request.resource.normalized_target,
        "scope": scope.scope_type if scope is not None else None,
        "session_key": scope.session_key if scope is not None else None,
    }


async def publish_external_access_cache_changed(
    payload: dict[str, Any],
) -> None:
    network = app_ctx().network
    if network is None:
        return
    await network.stream_manager.broadcast(EXTERNAL_ACCESS_CACHE_STREAM_ID, payload)


def _emit_external_access_cache_changed(payload: dict[str, Any]) -> None:
    network = app_ctx().network
    if network is None:
        return

    async def _emit() -> None:
        await publish_external_access_cache_changed(payload)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        try:
            asyncio.run(_emit())
        except Exception as exc:
            logger = app_ctx().logger
            if logger is not None:
                logger.error(f"[external_access] cache event publish failed: {exc}")
        return
    task = loop.create_task(_emit())
    task.add_done_callback(_log_external_access_cache_event_failure)


def _log_external_access_cache_event_failure(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception as exc:
        logger = app_ctx().logger
        if logger is not None:
            logger.error(f"[external_access] cache event publish failed: {exc}")


def process_external_access_cache_event(payload: dict[str, Any]) -> None:
    if payload.get("event_name") != EXTERNAL_ACCESS_CACHE_EVENT_NAME:
        return
    event_id = payload.get("event_id")
    if event_id:
        if event_id in _PROCESSED_CACHE_EVENT_IDS:
            return
        _remember_cache_event_id(event_id)
    if payload.get("source_node_id") == _runtime_node_id():
        return
    operation = payload.get("operation")
    if operation == "reload":
        _reset_approval_cache()
        return
    request = AccessRequest.create(
        subject_type=payload.get("subject_type"),
        subject_name=payload.get("subject_name"),
        resource_type=payload.get("resource_type"),
        operation=payload.get("resource_operation"),
        target=payload.get("normalized_target"),
    )
    if operation in {"approve_permanent", "approve_session"}:
        scope_type = payload.get("scope")
        session_key = payload.get("session_key")
        scope = (
            AccessScope.session(session_key)
            if scope_type == "session"
            else AccessScope.permanent()
        )
        _cache_approval(request, scope)
        return
    if operation == "deny":
        _cache_denial(request)


async def _consume_external_access_cache_stream() -> None:
    network = app_ctx().network
    if network is None:
        return
    queue = network.stream_manager.subscribe(EXTERNAL_ACCESS_CACHE_STREAM_ID)
    try:
        while True:
            payload = await queue.get()
            if isinstance(payload, dict):
                process_external_access_cache_event(payload)
    except asyncio.CancelledError:
        pass
    finally:
        network.stream_manager.unsubscribe(EXTERNAL_ACCESS_CACHE_STREAM_ID, queue)


def start_external_access_cache_consumer() -> None:
    ctx = app_ctx()
    network = ctx.network
    if network is None or getattr(network, "_loop", None) is None:
        return
    if getattr(ctx, "external_access_cache_consumer", None) is not None:
        return
    ctx.external_access_cache_consumer = asyncio.run_coroutine_threadsafe(
        _consume_external_access_cache_stream(),
        network._loop,
    )


def _runtime_subject_chain() -> list[dict[str, str]] | None:
    try:
        from democrai.core.infrastructure.sandbox import (
            process_guard as process_guard_mod,
        )

        current_state = process_guard_mod._state()
    except Exception:
        current_state = {}
    raw_chain = current_state.get("subject_chain")
    if not isinstance(raw_chain, list):
        return None
    normalized: list[dict[str, str]] = []
    for item in raw_chain:
        if not isinstance(item, dict):
            continue
        kind = item.get("kind") or item.get("subject_type")
        name = item.get("name") or item.get("subject_name")
        if not kind or not name:
            continue
        normalized.append({"kind": kind, "name": name})
    return normalized or None


def _runtime_request_context() -> tuple[int | None, int | None, str | None]:
    try:
        from democrai.core.infrastructure.network import (
            policy_guard as network_policy_mod,
        )

        user_id, organization_id, session_key = network_policy_mod._request_context()
        if user_id is not None or organization_id is not None or session_key:
            return user_id, organization_id, session_key
    except Exception:
        pass
    try:
        from democrai.core.infrastructure.sandbox import (
            process_guard as process_guard_mod,
        )

        user_id, organization_id, session_key = process_guard_mod._request_context()
        if user_id is not None or organization_id is not None or session_key:
            return user_id, organization_id, session_key
    except Exception:
        pass
    try:
        from democrai.core.runtime.foundation.app import req_ctx

        current = req_ctx()
        return current.user, current.organization_id, current.session_key
    except Exception:
        return None, None, None


def _request_os_allowlist_refresh(
    *,
    resource_type: str,
    subject_type: str,
    subject_name: str,
    target: str,
    mode: str,
) -> None:
    if resource_type != EXTERNAL_RESOURCE_NETWORK:
        return
    try:
        from democrai.core.infrastructure.sandbox.os.state import (
            is_application_network_allowlist_active,
            is_application_network_allowlist_enabled,
        )

        if not is_application_network_allowlist_enabled(app_ctx().config):
            debug_os_sandbox_flow(
                "external_access.refresh_skipped_disabled",
                resource_type=resource_type,
                subject_type=subject_type,
                subject_name=subject_name,
                target=target,
                mode=mode,
            )
            return
        if not is_application_network_allowlist_active():
            debug_os_sandbox_flow(
                "external_access.refresh_skipped_inactive",
                resource_type=resource_type,
                subject_type=subject_type,
                subject_name=subject_name,
                target=target,
                mode=mode,
            )
            return
    except Exception as exc:
        _log_allowlist_refresh_event_failure(exc)
        return
    from democrai.core.infrastructure.sandbox.os.events import (
        emit_application_network_allowlist_refresh_event,
    )

    payload = {
        "reason": "external_access_changed",
        "resource_type": resource_type,
        "subject_type": subject_type,
        "subject_name": subject_name,
        "target": target,
        "mode": mode,
    }
    debug_os_sandbox_flow("external_access.refresh_requested", **payload)

    async def _emit() -> None:
        await emit_application_network_allowlist_refresh_event(payload=payload)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        try:
            asyncio.run(_emit())
        except Exception as exc:
            _log_allowlist_refresh_event_failure(exc)
        return
    task = loop.create_task(_emit())
    task.add_done_callback(_log_allowlist_refresh_task_failure)


def _log_allowlist_refresh_task_failure(task: asyncio.Task) -> None:
    try:
        task.result()
    except Exception as exc:
        _log_allowlist_refresh_event_failure(exc)


def _log_allowlist_refresh_event_failure(exc: BaseException) -> None:
    logger = app_ctx().logger
    if logger is not None:
        logger.error(
            f"[external_access] failed_to_emit_allowlist_refresh_event: {exc}",
            "sandbox",
        )


def _record_observed_runtime_target(request: AccessRequest, *, mode: str) -> None:
    if request.resource.resource_type != ResourceType.NETWORK:
        return
    from democrai.core.infrastructure.sandbox.os.observed import (
        record_observed_runtime_target,
    )

    added = record_observed_runtime_target(
        request.resource.normalized_target,
        source=(
            f"observed:{request.subject.subject_type}:"
            f"{request.subject.subject_name}"
        ),
        purpose="runtime_allowed_target",
    )
    if not added:
        return
    _request_os_allowlist_refresh(
        resource_type=request.resource.resource_type.value,
        subject_type=request.subject.subject_type,
        subject_name=request.subject.subject_name,
        target=request.resource.normalized_target,
        mode=mode,
    )


def _build_request(
    *,
    subject_type: str,
    subject_name: str,
    resource_type: str,
    operation: str,
    target: str,
    task_id: str | None = None,
) -> AccessRequest:
    user_id, organization_id, session_key = _runtime_request_context()
    return AccessRequest.create(
        subject_type=subject_type,
        subject_name=subject_name,
        resource_type=resource_type,
        operation=operation,
        target=target,
        requested_by=user_id,
        organization_id=organization_id,
        session_key=session_key,
        task_id=task_id,
    )


def check_external_access(
    *,
    subject_type: str,
    subject_name: str,
    resource_type: str,
    operation: str,
    target: str,
    register_request: bool = True,
    resume_action: str | None = None,
    resume_context: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> AccessDecision:
    request = _build_request(
        subject_type=subject_type,
        subject_name=subject_name,
        resource_type=resource_type,
        operation=operation,
        target=target,
        task_id=task_id,
    )
    encrypted_resume_context, resume_context_hash = encrypt_resume_context(
        resume_context
    )
    cached = _cached_decision(request)
    if cached is not None and (not cached.requires_approval or not register_request):
        decision = cached
    else:
        decision = _service().check_access(
            request,
            register_request=register_request,
            subject_chain=_runtime_subject_chain(),
            resume_action=resume_action,
            resume_context=encrypted_resume_context,
            resume_context_hash=resume_context_hash,
        )
        _cache_decision(
            request,
            decision,
            register_request=register_request,
        )
    if decision.allowed:
        _record_observed_runtime_target(request, mode=decision.code)
    debug_media_flow(
        "external_access.check.result",
        subject_type=request.subject.subject_type,
        subject_name=request.subject.subject_name,
        resource_type=request.resource.resource_type.value,
        operation=request.resource.operation.value,
        target=request.resource.normalized_target,
        allowed=decision.allowed,
        requires_approval=decision.requires_approval,
        code=decision.code,
    )
    return decision


def approve_permanently(
    *,
    subject_type: str,
    subject_name: str,
    resource_type: str,
    operation: str,
    target: str,
) -> None:
    approved_by, _organization_id, _session_key = _require_external_access_admin(
        action="approve_permanently"
    )
    request = _build_request(
        subject_type=subject_type,
        subject_name=subject_name,
        resource_type=resource_type,
        operation=operation,
        target=target,
    )
    rows = _service().approve_permanently(request, approved_by=approved_by)
    scope = AccessScope.permanent()
    _cache_approval(request, scope)
    _emit_external_access_cache_changed(
        _cache_event_payload(
            operation="approve_permanent",
            request=request,
            scope=scope,
        )
    )
    _resume_rows_after_approval(rows, mode="permanent")
    _request_os_allowlist_refresh(
        resource_type=request.resource.resource_type.value,
        subject_type=request.subject.subject_type,
        subject_name=request.subject.subject_name,
        target=request.resource.normalized_target,
        mode="permanent",
    )


def approve_for_session(
    *,
    subject_type: str,
    subject_name: str,
    resource_type: str,
    operation: str,
    target: str,
    session_key: str | None = None,
) -> None:
    approved_by, _organization_id, runtime_session_key = _require_external_access_admin(
        action="approve_for_session"
    )
    request = _build_request(
        subject_type=subject_type,
        subject_name=subject_name,
        resource_type=resource_type,
        operation=operation,
        target=target,
    )
    resolved_session_key = session_key or runtime_session_key
    if resolved_session_key is None:
        raise ValueError("external_access_session_key_required")
    rows = _service().approve_for_session(
        request,
        approved_by=approved_by,
        session_key=resolved_session_key,
    )
    scope = AccessScope.session(resolved_session_key)
    _cache_approval(request, scope)
    _emit_external_access_cache_changed(
        _cache_event_payload(
            operation="approve_session",
            request=request,
            scope=scope,
        )
    )
    _resume_rows_after_approval(rows, mode="session")
    _request_os_allowlist_refresh(
        resource_type=request.resource.resource_type.value,
        subject_type=request.subject.subject_type,
        subject_name=request.subject.subject_name,
        target=request.resource.normalized_target,
        mode="session",
    )


def deny_external_access(
    *,
    subject_type: str,
    subject_name: str,
    resource_type: str,
    operation: str,
    target: str,
) -> None:
    _require_external_access_admin(action="deny")
    request = _build_request(
        subject_type=subject_type,
        subject_name=subject_name,
        resource_type=resource_type,
        operation=operation,
        target=target,
    )
    _service().deny(request)
    _cache_denial(request)
    _emit_external_access_cache_changed(
        _cache_event_payload(operation="deny", request=request)
    )
    _request_os_allowlist_refresh(
        resource_type=request.resource.resource_type.value,
        subject_type=request.subject.subject_type,
        subject_name=request.subject.subject_name,
        target=request.resource.normalized_target,
        mode="deny",
    )


def is_permanently_approved(
    *,
    subject_type: str,
    subject_name: str,
    resource_type: str,
    operation: str,
    target: str,
) -> bool:
    request = AccessRequest.create(
        subject_type=subject_type,
        subject_name=subject_name,
        resource_type=resource_type,
        operation=operation,
        target=target,
    )
    return access_policy_store.has_access_approval(
        subject=request.subject,
        resource=request.resource,
        scope=AccessScope.permanent(),
    )


def can_manage_external_access(
    *,
    user_id: int | None,
    role: str | None,
    access_level: int | None,
    organization_id: int | None,
    permissions: list[str] | None = None,
) -> bool:
    if user_id is None:
        return False
    if organization_id:
        return False
    return is_super_role(role)


def _require_external_access_admin(
    *, action: str
) -> tuple[int, int | None, str | None]:
    user_id, organization_id, session_key = _runtime_request_context()
    if user_id is None:
        raise PermissionError("external_access_admin_required")
    profile = get_user_access_profile(user_id)
    if not isinstance(profile, dict):
        raise PermissionError("external_access_admin_required")
    role = profile.get("role") or None
    access_level = profile.get("access_level")
    resolved_organization_id = (
        organization_id
        if organization_id is not None
        else profile.get("organization_id")
    )
    if not can_manage_external_access(
        user_id=user_id,
        role=role,
        access_level=access_level if isinstance(access_level, int) else None,
        organization_id=(
            resolved_organization_id
            if isinstance(resolved_organization_id, int)
            else None
        ),
    ):
        raise PermissionError("external_access_admin_required")
    debug_media_flow(
        f"external_access.{action}.authorized",
        user_id=user_id,
        organization_id=resolved_organization_id,
        role=role,
        access_level=access_level,
        session_key=session_key,
    )
    return (
        user_id,
        resolved_organization_id if isinstance(resolved_organization_id, int) else None,
        session_key,
    )


def _resume_rows_after_approval(rows: list[dict] | None, *, mode: str) -> None:
    if rows is None:
        return
    resumable = [dict(row) for row in rows if row.get("resume_action")]
    if not resumable:
        return

    async def _runner() -> None:
        for row in resumable:
            await _run_resume_action(row, mode=mode)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        asyncio.run(_runner())
        return
    task = loop.create_task(_runner())
    task.add_done_callback(_log_resume_task_failure)


def _log_resume_task_failure(task: asyncio.Task) -> None:
    try:
        task.result()
    except asyncio.CancelledError:
        app_ctx().logger.warning("[external_access] resume_task_cancelled")
    except Exception as exc:
        app_ctx().logger.error(f"[external_access] resume_task_failed error={exc}")


async def _run_resume_action(row: dict, *, mode: str) -> None:
    resume_action = row.get("resume_action")
    if not isinstance(resume_action, str):
        return
    action_name = resume_action.strip()
    if not action_name:
        return
    try:
        from democrai.core.application.auth.service import get_user_permissions
        from democrai.core.application.handler.dispatcher import ActionDispatcher
        from democrai.core.runtime.foundation.app import (
            RequestContext,
            reset_req_ctx,
            set_req_ctx,
        )
        from democrai.sdk.client import SDK

        resume_context = decrypt_resume_context(row.get("resume_context"))
        requested_by = row.get("requested_by")
        organization_id = row.get("organization_id")
        session_key = row.get("session_key") or None
        session_user = {}
        if requested_by is not None:
            session_user["id"] = requested_by
        if organization_id is not None:
            session_user["organization_id"] = organization_id
        session = {
            "session_key": session_key,
            "user": session_user,
        }
        request_context = RequestContext(
            request_id=f"external-access-resume:{row.get('id')}",
            user=requested_by,
            role=None,
            organization_id=organization_id,
            access_level=None,
            channel="system",
            session_key=session_key,
            action_name=action_name,
            module_name=module_name_from_action(action_name),
        )
        permissions = (
            get_user_permissions(int(requested_by)) if requested_by is not None else []
        )
        sdk = SDK("", "core", session=session)
        token = set_req_ctx(request_context)
        try:
            result = await ActionDispatcher().dispatch(
                action_name,
                resume_context,
                session,
                permissions,
                sdk,
            )
        finally:
            reset_req_ctx(token)
        debug_media_flow(
            "external_access.resume.completed",
            request_id=row.get("id"),
            subject_type=row.get("subject_type"),
            subject_name=row.get("subject_name"),
            resource_type=row.get("resource_type"),
            operation=row.get("operation"),
            target=row.get("normalized_target") or row.get("target"),
            resume_action=action_name,
            resume_context_hash=row.get("resume_context_hash"),
            mode=mode,
            result=result if isinstance(result, dict) else None,
        )
    except Exception as exc:
        app_ctx().logger.error(
            f"[external_access] resume_action_failed action={action_name} "
            f"request_id={row.get('id')} error={exc}"
        )
