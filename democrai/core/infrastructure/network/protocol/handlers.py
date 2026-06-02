from __future__ import annotations

import asyncio
import time
import uuid

from democrai.core.application.session import generate_session_key
from democrai.core.runtime.foundation.app import (
    RequestContext,
    app_ctx,
    module_name_from_action,
    req_ctx,
)
from democrai.core.runtime.observability.request_flow import trace_request_step


def send_auth_error(network, bus, client_id, msg, error: str) -> None:
    bus.send(
        client_id,
        {"type": "error", "error": error, "request_id": msg.get("request_id")},
    )


def send_invalid_media_request(network, bus, client_id, msg) -> None:
    bus.send(
        client_id,
        {
            "type": "error",
            "error": "invalid_media_request",
            "request_id": msg.get("request_id"),
        },
    )


def is_action_allowed_for_context(msg, ctx) -> bool:
    action = msg.get("userAction")
    binding_action = msg.get("bindingAction")
    return (
        ctx.user is not None
        or isinstance(action, dict)
        or isinstance(binding_action, dict)
    )


def is_legacy_message_allowed_for_context(network, msg, ctx) -> bool:
    if ctx.user:
        return True
    msg_type = msg.get("type")
    if isinstance(msg_type, str) and msg_type in network._GUEST_ALLOWED_MESSAGE_TYPES:
        return True
    return False #not msg


def default_stream_id(client_id) -> str:
    return f"stream_{client_id}"


def bind_stream_to_owner(network, stream_id: str, *, bus, client_id) -> None:
    network._stream_owners[stream_id] = (id(bus), client_id)


def stream_owner_matches(network, stream_id: str, *, bus, client_id) -> bool:
    owner = network._stream_owners.get(stream_id)
    return owner == (id(bus), client_id)


def resolve_bus_by_id(network, bus_id: int):
    for bus in network.buses:
        if id(bus) == bus_id:
            return bus
    return None


async def ask_client(
    network,
    stream_id: str,
    query: dict,
    *,
    timeout: float = 5.0,
):
    resolved_stream_id = str(stream_id or "").strip()
    if not resolved_stream_id:
        raise ValueError("stream_id is required")
    if not isinstance(query, dict):
        raise ValueError("client query must be a dict")

    owner = network._stream_owners.get(resolved_stream_id)
    if owner is None:
        raise RuntimeError(f"stream is not bound to a live client: {resolved_stream_id}")

    owner_bus_id, owner_client_id = owner
    owner_bus = resolve_bus_by_id(network, owner_bus_id)
    if owner_bus is None:
        raise RuntimeError(f"client bus is not available for stream: {resolved_stream_id}")

    kind = str(query.get("kind") or "").strip()
    surface_id = str(query.get("surfaceId") or query.get("surface_id") or "").strip()
    component_id = str(
        query.get("componentId") or query.get("component_id") or ""
    ).strip()
    path = str(query.get("path") or "").strip()
    loop = asyncio.get_running_loop()
    request_id = uuid.uuid4().hex
    future = loop.create_future()
    network._pending_client_queries[request_id] = {
        "future": future,
        "owner": owner,
        "stream_id": resolved_stream_id,
    }

    payload = dict(query)
    payload["requestId"] = request_id
    started_at = time.perf_counter()
    trace_request_step(
        request_id,
        "client_query.sent",
        kind=kind,
        stream_id=resolved_stream_id,
        surface_id=surface_id,
        component_id=component_id,
        path=path,
        timeout=timeout,
    )
    try:
        owner_bus.send(owner_client_id, {"clientQuery": payload})
        result = await asyncio.wait_for(future, timeout=timeout)
    except Exception as exc:
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        trace_request_step(
            request_id,
            "client_query.failed",
            kind=kind,
            duration_ms=round(duration_ms, 2),
            error_type=type(exc).__name__,
            reason=str(exc),
        )
        raise
    finally:
        network._pending_client_queries.pop(request_id, None)

    if not isinstance(result, dict):
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        trace_request_step(
            request_id,
            "client_query.failed",
            kind=kind,
            duration_ms=round(duration_ms, 2),
            error_type="RuntimeError",
            reason="invalid client query result",
        )
        raise RuntimeError("invalid client query result")
    if not result.get("ok", False):
        error = str(result.get("error") or "client_query_failed")
        duration_ms = (time.perf_counter() - started_at) * 1000.0
        trace_request_step(
            request_id,
            "client_query.failed",
            kind=kind,
            duration_ms=round(duration_ms, 2),
            error_type="RuntimeError",
            reason=error,
        )
        raise RuntimeError(error)
    duration_ms = (time.perf_counter() - started_at) * 1000.0
    trace_request_step(
        request_id,
        "client_query.completed",
        kind=kind,
        duration_ms=round(duration_ms, 2),
        ok=True,
    )
    return result.get("value")


def reject_client_queries_for_owner(network, owner: tuple[int, object]) -> None:
    for request_id, pending in list(network._pending_client_queries.items()):
        if pending.get("owner") != owner:
            continue
        future = pending.get("future")
        network._pending_client_queries.pop(request_id, None)
        if future is not None and not future.done():
            future.set_exception(RuntimeError("client disconnected"))


def register_authenticated_client(
    network, bus, client_id, *, user: int, role, organization_id, access_level
) -> None:
    network._authenticated_clients[(id(bus), client_id)] = (
        user,
        role,
        organization_id,
        access_level,
    )


def register_client_session_key(network, bus, client_id, session_key: str) -> None:
    if session_key:
        network._client_session_keys[(id(bus), client_id)] = session_key


def _auth_tuple(auth):
    if isinstance(auth, tuple):
        user, role, organization_id, access_level = auth
        return user, role, organization_id, access_level, None
    return (
        auth.user,
        auth.role,
        auth.organization_id,
        auth.access_level,
        auth.error,
    )


def build_context(network, bus, client_id, msg):
    rid = msg.get("request_id")
    user, role, organization_id, access_level, auth_error = _auth_tuple(
        network._extract_auth(msg)
    )
    if user is not None:
        network.register_authenticated_client(
            bus,
            client_id,
            user=user,
            role=role,
            organization_id=organization_id,
            access_level=access_level,
        )
    try:
        action_name = msg["userAction"]["name"]
    except Exception:
        action_name = None
    conn_key = (id(bus), client_id)
    session_key = network._client_session_keys.get(conn_key)
    if not session_key:
        session_key = generate_session_key()
        network._client_session_keys[conn_key] = session_key
    ctx = RequestContext(
        app=app_ctx(),
        request_id=rid,
        user=user,
        role=role,
        organization_id=organization_id,
        access_level=access_level,
        channel="bus",
        session_key=session_key,
        client_ip=None,
        action_name=action_name,
        module_name=module_name_from_action(action_name),
    )
    if auth_error:
        ctx.auth_error = auth_error
    if user is not None:
        is_new_conn = not network.connection_registry.is_online(user, organization_id)
        network.connection_registry.register(user, bus, client_id, organization_id)

        def _send_fn(message):
            bus.send(client_id, message)

        network._notification_queue.flush(user, _send_fn, organization_id)

        if is_new_conn:
            _push_initial_notifications_to_super_users(
                network, role=role, organization_id=organization_id
            )
    trace_request_step(
        rid or "",
        "context.built",
        user=user,
        organization_id=organization_id,
        action_name=action_name,
        channel="bus",
        session_key=session_key,
    )
    return ctx


def authorize_and_bind_stream(
    network, bus, client_id, msg, ctx, *, reject_on_unauthenticated: bool
):
    requested_stream_id = msg.get("stream_id")
    if requested_stream_id is None:
        stream_id = network._default_stream_id(client_id)
        msg["stream_id"] = stream_id
        network._bind_stream_to_owner(stream_id, bus=bus, client_id=client_id)
        network._ensure_stream_piped(bus, client_id, stream_id)
        return stream_id

    if ctx.user is None and reject_on_unauthenticated:
        app_ctx().logger.warning(
            f"[Network] Unauthenticated client '{client_id}' tried restricted stream access"
        )
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return None

    if not isinstance(requested_stream_id, str) or not requested_stream_id.strip():
        app_ctx().logger.warning(
            f"[Network] Client '{client_id}' provided an invalid stream id"
        )
        network._send_auth_error(bus, client_id, msg, "invalid_stream_id")
        return None

    stream_id = requested_stream_id.strip()
    if stream_id not in network._stream_owners:
        app_ctx().logger.warning(
            f"[Network] Client '{client_id}' tried to claim unissued stream '{stream_id}'"
        )
        network._send_auth_error(bus, client_id, msg, "stream_id_not_server_issued")
        return None

    if not network._stream_owner_matches(stream_id, bus=bus, client_id=client_id):
        app_ctx().logger.warning(
            f"[Network] Client '{client_id}' tried to access unauthorized stream '{stream_id}'"
        )
        network._send_auth_error(bus, client_id, msg, "unauthorized_stream")
        return None

    network._ensure_stream_piped(bus, client_id, stream_id)
    return stream_id


async def handle_action(network, bus, client_id, msg):
    ctx = req_ctx()
    if not network._is_action_allowed_for_context(msg, ctx):
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return
    stream_id = network._authorize_and_bind_stream(
        bus, client_id, msg, ctx, reject_on_unauthenticated=False
    )
    if stream_id is None and "stream_id" in msg:
        return
    ctx.stream_id = stream_id or ctx.stream_id
    await network._launch_request(bus, client_id, msg, ctx)


async def handle_task_response(network, bus, client_id, msg):
    ctx = req_ctx()
    user = ctx.user
    if user is None:
        app_ctx().logger.warning(
            "[Network] Unauthenticated client tried backgroundTaskResponse"
        )
        return

    task_resp = msg["backgroundTaskResponse"]
    task_id = task_resp.get("taskId")
    response = task_resp.get("response", {})
    if task_id:
        task = network.task_manager.get_task(task_id)
        if (
            not task
            or task.user_id != user
            or (task.organization_id or None) != (ctx.organization_id or None)
        ):
            app_ctx().logger.warning(
                f"[Network] User '{user}' tried to respond to task '{task_id}' they don't own"
            )
            return
        await network.task_manager.respond_confirmation(task_id, response)


async def handle_task_cancel(network, bus, client_id, msg):
    ctx = req_ctx()
    user = ctx.user
    if user is None:
        app_ctx().logger.warning(
            "[Network] Unauthenticated client tried backgroundTaskCancel"
        )
        return

    task_id = msg["backgroundTaskCancel"].get("taskId")
    if task_id:
        task = network.task_manager.get_task(task_id)
        if (
            not task
            or task.user_id != user
            or (task.organization_id or None) != (ctx.organization_id or None)
        ):
            app_ctx().logger.warning(
                f"[Network] User '{user}' tried to cancel task '{task_id}' they don't own"
            )
            return
        await network.task_manager.cancel(task_id)


async def handle_task_get(network, bus, client_id, msg):
    ctx = req_ctx()
    user = ctx.user
    if user is None:
        app_ctx().logger.warning(
            "[Network] Unauthenticated client tried backgroundTaskGet"
        )
        return

    task_id = msg.get("backgroundTaskGet", {}).get("taskId")
    if not task_id:
        return

    task = network.task_manager.get_task(task_id)

    if task is None:
        from democrai.core.application.tasks.models import BackgroundTaskRecord

        db = network.task_manager._get_db()
        try:
            task = db.query(BackgroundTaskRecord).filter(BackgroundTaskRecord.id == task_id).first()
        except Exception:
            task = None
        finally:
            db.close()

    if task is None:
        return

    if task.user_id != user:
        app_ctx().logger.warning(
            f"[Network] User '{user}' tried to get task '{task_id}' they don't own"
        )
        return

    if (task.organization_id or None) != (ctx.organization_id or None):
        return

    from democrai.core.platform.utils.timezone import format_app_datetime, serialize_app_datetime
    import json

    def _deserialize(value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except Exception:
                return value
        return value

    updated_at = serialize_app_datetime(task.updated_at)
    updated_at_label = format_app_datetime(task.updated_at)

    if task.status == "completed":
        message = {
            "backgroundTaskCompleted": {
                "taskId": task.id,
                "label": task.label,
                "result": _deserialize(task.result),
                "updatedAt": updated_at,
                "updatedAtLabel": updated_at_label,
            }
        }
    elif task.status in ("failed", "interrupted"):
        message = {
            "backgroundTaskError": {
                "taskId": task.id,
                "label": task.label,
                "error": task.error or "Unknown error",
                "updatedAt": updated_at,
                "updatedAtLabel": updated_at_label,
            }
        }
    else:
        message = {
            "backgroundTaskProgress": {
                "taskId": task.id,
                "progress": task.progress,
                "label": task.label,
                "checkpoint": bool(task.checkpoint),
                "updatedAt": updated_at,
                "updatedAtLabel": updated_at_label,
            }
        }

    bus.send(client_id, message)


async def handle_client_query_result(network, bus, client_id, msg):
    payload = msg.get("clientQueryResult")
    if not isinstance(payload, dict):
        return

    request_id = str(
        payload.get("requestId") or payload.get("request_id") or ""
    ).strip()
    if not request_id:
        return

    pending = network._pending_client_queries.get(request_id)
    if not pending:
        app_ctx().logger.warning(
            f"[Network] Unknown clientQueryResult request_id={request_id}"
        )
        return

    owner = pending.get("owner")
    if owner != (id(bus), client_id):
        app_ctx().logger.warning(
            f"[Network] Ignoring clientQueryResult from non-owner client request_id={request_id}"
        )
        return

    future = pending.get("future")
    if future is not None and not future.done():
        future.set_result(payload)


async def handle_stream_piping(network, bus, client_id, msg):
    ctx = req_ctx()
    network._authorize_and_bind_stream(
        bus, client_id, msg, ctx, reject_on_unauthenticated=True
    )


def _push_initial_notifications_if_super(
    network, bus, client_id, *, role, organization_id
) -> None:
    from democrai.core.application.auth.roles import is_super_role
    from democrai.core.infrastructure.database.access_policy import get_pending_access_requests
    from democrai.core.infrastructure.network.protocol.auth import push_notifications_update

    if not is_super_role(role) or organization_id:
        return
    try:
        count = len(get_pending_access_requests())
        push_notifications_update(bus, client_id, count=count)
    except Exception:
        pass


def _push_initial_notifications_to_super_users(network, *, role, organization_id) -> None:
    from democrai.core.application.auth.roles import is_super_role
    from democrai.core.infrastructure.database.access_policy import get_pending_access_requests
    from democrai.core.infrastructure.network.protocol.auth import push_notifications_update

    if not is_super_role(role) or organization_id:
        return
    try:
        count = len(get_pending_access_requests())
        seen_users: set[int] = set()
        for _, (user_id, user_role, user_organization_id, _) in list(
            network._authenticated_clients.items()
        ):
            if (
                user_id is None
                or user_organization_id
                or not is_super_role(user_role)
                or user_id in seen_users
            ):
                continue
            seen_users.add(user_id)
            for user_bus, user_client_id in network.connection_registry.get_connections(user_id):
                try:
                    push_notifications_update(user_bus, user_client_id, count=count)
                except Exception:
                    pass
    except Exception:
        pass
