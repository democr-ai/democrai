from __future__ import annotations

from uuid import uuid4

from democrai.core.infrastructure.database.access_policy import get_pending_access_requests
from democrai.core.infrastructure.network.protocol.auth import push_notifications_update
from democrai.core.platform.utils.debug import debug_media_flow
from democrai.core.runtime.foundation.app import req_ctx


def _parse_media_request(network, bus, client_id, msg, payload_key: str):
    from democrai.core.application.handler.services.runtime.media_requests import (
        parse_external_media_request,
    )

    payload = msg.get(payload_key)
    try:
        media_request = parse_external_media_request(
            payload,
            include_force_refresh=(payload_key == "mediaResolve"),
        )
    except ValueError:
        network._send_invalid_media_request(bus, client_id, msg)
        return None
    return media_request


def _send_media_error(
    bus,
    client_id,
    msg,
    *,
    message_type: str,
    payload_key: str,
    error: str,
    module_name: str,
    url: str,
    client_generation: int,
    error_code: str | None = None,
) -> None:
    from democrai.core.application.handler.services.runtime.media_requests import (
        build_external_media_error,
    )

    bus.send(
        client_id,
        {
            "type": message_type,
            "request_id": msg.get("request_id"),
            payload_key: build_external_media_error(
                error=error,
                module_name=module_name,
                url=url,
                client_generation=client_generation,
                error_code=error_code,
            ),
        },
    )


def _check_media_access(_network, _bus, _client_id, ctx, *, module_name: str, url: str):
    from democrai.core.application.handler.services.runtime.access import (
        check_external_media_access,
        network_policy_context,
    )

    with network_policy_context(
        subject_name=module_name,
        user_id=ctx.user,
        organization_id=ctx.organization_id,
        session_key=ctx.session_key,
    ):
        return check_external_media_access(
            module_name=module_name,
            url=url,
            user_id=ctx.user,
            organization_id=ctx.organization_id,
            session_key=ctx.session_key,
        )


def _push_notifications_to_super_users(network) -> None:
    """Send an updated notification count to all connected super users."""
    from democrai.core.application.auth.roles import is_super_role

    count = len(get_pending_access_requests())
    seen_users: set[int] = set()
    for _, (user_id, role, org_id, _) in list(network._authenticated_clients.items()):
        if user_id is None or org_id or not is_super_role(role):
            continue
        if user_id in seen_users:
            continue
        seen_users.add(user_id)
        conns = network.connection_registry.get_connections(user_id)
        for bus, cid in conns:
            try:
                push_notifications_update(bus, cid, count=count)
            except Exception:
                pass


async def handle_media_resolve(network, bus, client_id, msg):
    ctx = req_ctx()
    if ctx.user is None:
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return

    media_request = _parse_media_request(network, bus, client_id, msg, "mediaResolve")
    if media_request is None:
        return

    module_name = media_request.module_name
    url = media_request.url
    client_generation = media_request.client_generation
    force_refresh = media_request.force_refresh
    debug_media_flow(
        "network_flows.handle_media_resolve.start",
        request_id=msg.get("request_id"),
        module_name=module_name,
        url=url,
        user_id=ctx.user,
        organization_id=ctx.organization_id,
        session_key=ctx.session_key,
        client_generation=client_generation,
        force_refresh=force_refresh,
    )

    try:
        from democrai.core.application.handler.services.runtime.access import (
            resolve_external_media_to_cache,
        )

        access_check = _check_media_access(
            network,
            bus,
            client_id,
            ctx,
            module_name=module_name,
            url=url,
        )
        if not access_check.allowed:
            debug_media_flow(
                "network_flows.handle_media_resolve.denied",
                request_id=msg.get("request_id"),
                module_name=module_name,
                url=url,
                code=access_check.code,
                message=access_check.message,
            )
            _send_media_error(
                bus,
                client_id,
                msg,
                message_type="media_resolved",
                payload_key="mediaResolved",
                error=access_check.message,
                error_code=access_check.code,
                module_name=module_name,
                url=url,
                client_generation=client_generation,
            )
            if access_check.code == "not_enabled":
                _push_notifications_to_super_users(network)
            return

        resolved = await resolve_external_media_to_cache(
            module_name,
            url,
            force_refresh=force_refresh,
            skip_allowlist_check=True,
            user_id=ctx.user,
            organization_id=ctx.organization_id,
            session_key=ctx.session_key,
        )
        resolved_payload = dict(resolved or {})
        resolved_payload["client_generation"] = client_generation
        debug_media_flow(
            "network_flows.handle_media_resolve.resolved",
            request_id=msg.get("request_id"),
            module_name=module_name,
            url=url,
            path=resolved_payload.get("path"),
            cache_hit=resolved_payload.get("cache_hit"),
        )
        bus.send(
            client_id,
            {
                "type": "media_resolved",
                "request_id": msg.get("request_id"),
                "mediaResolved": resolved_payload,
            },
        )
    except Exception as exc:
        debug_media_flow(
            "network_flows.handle_media_resolve.error",
            request_id=msg.get("request_id"),
            module_name=module_name,
            url=url,
            error=str(exc),
        )
        _send_media_error(
            bus,
            client_id,
            msg,
            message_type="media_resolved",
            payload_key="mediaResolved",
            error=str(exc),
            module_name=module_name,
            url=url,
            client_generation=client_generation,
        )


async def handle_media_stream_open(network, bus, client_id, msg):
    ctx = req_ctx()
    if ctx.user is None:
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return

    media_request = _parse_media_request(
        network, bus, client_id, msg, "mediaStreamOpen"
    )
    if media_request is None:
        return
    module_name = media_request.module_name
    url = media_request.url
    client_generation = media_request.client_generation
    debug_media_flow(
        "network_flows.handle_media_stream_open.start",
        request_id=msg.get("request_id"),
        module_name=module_name,
        url=url,
        user_id=ctx.user,
        organization_id=ctx.organization_id,
        session_key=ctx.session_key,
        client_generation=client_generation,
    )

    from democrai.core.application.handler.services.runtime.access import open_external_media_stream

    try:
        access_check = _check_media_access(
            network,
            bus,
            client_id,
            ctx,
            module_name=module_name,
            url=url,
        )
        if not access_check.allowed:
            debug_media_flow(
                "network_flows.handle_media_stream_open.denied",
                request_id=msg.get("request_id"),
                module_name=module_name,
                url=url,
                code=access_check.code,
                message=access_check.message,
            )
            _send_media_error(
                bus,
                client_id,
                msg,
                message_type="media_stream_error",
                payload_key="mediaStreamError",
                error=access_check.message,
                error_code=access_check.code,
                module_name=module_name,
                url=url,
                client_generation=client_generation,
            )
            if access_check.code == "not_enabled":
                _push_notifications_to_super_users(network)
            return

        client, upstream, metadata = await open_external_media_stream(
            module_name,
            url,
            skip_allowlist_check=True,
            user_id=ctx.user,
            organization_id=ctx.organization_id,
            session_key=ctx.session_key,
        )
    except Exception as exc:
        debug_media_flow(
            "network_flows.handle_media_stream_open.error",
            request_id=msg.get("request_id"),
            module_name=module_name,
            url=url,
            error=str(exc),
        )
        _send_media_error(
            bus,
            client_id,
            msg,
            message_type="media_stream_error",
            payload_key="mediaStreamError",
            error=str(exc),
            module_name=module_name,
            url=url,
            client_generation=client_generation,
        )
        return

    stream_id = f"media_stream_{uuid4().hex}"
    network._bind_stream_to_owner(stream_id, bus=bus, client_id=client_id)
    network._ensure_stream_piped(bus, client_id, stream_id)
    network._client_media_streams.setdefault((id(bus), client_id), set()).add(stream_id)

    import asyncio

    task = asyncio.create_task(
        network._pipe_media_stream(stream_id, client=client, upstream=upstream)
    )
    network._media_stream_tasks[stream_id] = task
    bus.send(
        client_id,
        {
            "type": "media_stream_opened",
            "request_id": msg.get("request_id"),
            "mediaStreamOpened": {
                "stream_id": stream_id,
                "client_generation": client_generation,
                **metadata,
            },
        },
    )
    debug_media_flow(
        "network_flows.handle_media_stream_open.opened",
        request_id=msg.get("request_id"),
        module_name=module_name,
        url=url,
        stream_id=stream_id,
        content_type=metadata.get("content_type"),
    )


async def handle_media_stream_close(network, bus, client_id, msg):
    ctx = req_ctx()
    if ctx.user is None:
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return

    payload = msg.get("mediaStreamClose")
    if not isinstance(payload, dict):
        network._send_invalid_media_request(bus, client_id, msg)
        return
    stream_id = str(payload.get("stream_id") or "").strip()
    if not stream_id:
        network._send_invalid_media_request(bus, client_id, msg)
        return
    if not network._stream_owner_matches(stream_id, bus=bus, client_id=client_id):
        network._send_auth_error(bus, client_id, msg, "unauthorized_stream")
        return
    await network._close_media_stream(bus, client_id, stream_id)


def notify_external_access_approved(network, **__) -> None:
    """Update the notification badge count for all connected super users."""
    _push_notifications_to_super_users(network)
