from __future__ import annotations

import asyncio
import time
import uuid

from democrai.core.application.request_cycle import infer_request_kind
from democrai.core.infrastructure.network.protocol.routing import (
    DEFAULT_PROTOCOL_HANDLER_METHOD,
    PROTOCOL_HANDLER_METHODS,
)
from democrai.core.runtime.observability.request_flow import (
    finish_request_flow,
    start_request_flow,
    trace_request_step,
)
from democrai.core.runtime.foundation.app import reset_req_ctx, set_req_ctx


def configure_bus_callbacks(network) -> None:
    for bus in network.buses:
        if hasattr(bus, "on_message"):
            bus.on_message = lambda cid, msg, b=bus: network._on_bus_message(
                b, cid, msg
            )
        if hasattr(bus, "on_disconnect"):
            bus.on_disconnect = lambda cid, b=bus: network._on_bus_disconnect(b, cid)


def on_bus_message(network, bus, client_id, msg) -> None:
    from democrai.core.infrastructure.network.runtime import network as network_mod

    if network._loop and network._loop.is_running():
        callback_started_at = time.perf_counter()
        handoff_started_at = msg.get("_ws_handoff_started_at")
        if isinstance(handoff_started_at, (int, float)):
            msg["_transport_ws_to_callback_ms"] = (
                callback_started_at - float(handoff_started_at)
            ) * 1000.0
        with network._pending_network_messages_lock:
            network._pending_network_messages += 1
            pending_at_schedule = network._pending_network_messages
        msg["_network_pending_at_schedule"] = pending_at_schedule
        msg["_network.callback_before_schedule"] = (
            time.perf_counter() - callback_started_at
        ) * 1000.0
        schedule_started_at = time.perf_counter()
        msg["_network_schedule_started_at"] = schedule_started_at
        asyncio.run_coroutine_threadsafe(
            network._process_message(bus, client_id, msg), network._loop
        )
        msg["_network_schedule_call_ms"] = (
            time.perf_counter() - schedule_started_at
        ) * 1000.0
    else:
        network_mod.app_ctx().logger.error(
            "[Network] Cannot process message: Loop not running."
        )


async def process_message(network, bus, client_id, msg):
    from democrai.core.infrastructure.network.runtime import network as network_mod

    if "request_id" not in msg:
        msg["request_id"] = str(uuid.uuid4())
    request_kind = infer_request_kind(msg)
    message_type = msg.get("type") or request_kind
    action_payload = msg.get("userAction") or msg.get("bindingAction") or {}
    action_name = (
        action_payload.get("name") if isinstance(action_payload, dict) else None
    )
    module_name = None
    if isinstance(action_name, str) and "." in action_name:
        module_name = action_name.partition(".")[0]
    start_request_flow(
        msg["request_id"],
        request_kind,
        message_type=message_type,
        action_name=action_name,
        module_name=module_name,
    )
    profiler, profile_token, owns_profile = network_mod.ensure_request_profile(
        msg["request_id"], request_kind
    )
    decode_ms = msg.pop("_ws_decode_ms", None)
    handoff_started_at = msg.pop("_ws_handoff_started_at", None)
    ws_to_callback_ms = msg.pop("_transport_ws_to_callback_ms", None)
    callback_before_schedule_ms = msg.pop("_network.callback_before_schedule", None)
    schedule_started_at = msg.pop("_network_schedule_started_at", None)
    schedule_call_ms = msg.pop("_network_schedule_call_ms", None)
    if isinstance(decode_ms, (int, float)):
        profiler.add_ms("transport.ws.decode", float(decode_ms))
    if isinstance(ws_to_callback_ms, (int, float)):
        profiler.add_ms("transport.ws.to_callback", float(ws_to_callback_ms))
    if isinstance(callback_before_schedule_ms, (int, float)):
        profiler.add_ms(
            "transport.network.callback_before_schedule",
            float(callback_before_schedule_ms),
        )
    if isinstance(schedule_call_ms, (int, float)):
        profiler.add_ms("transport.network.schedule_call", float(schedule_call_ms))
    if isinstance(schedule_started_at, (int, float)):
        profiler.add_ms(
            "transport.network.schedule_wait",
            (time.perf_counter() - float(schedule_started_at)) * 1000.0,
        )
    if isinstance(handoff_started_at, (int, float)):
        profiler.add_ms(
            "transport.network.handoff_wait",
            (time.perf_counter() - float(handoff_started_at)) * 1000.0,
        )
    pending_at_schedule = msg.pop("_network_pending_at_schedule", None)
    if isinstance(pending_at_schedule, int):
        profiler.add_metric(
            "transport.network.pending_at_schedule", pending_at_schedule
        )
    with network._pending_network_messages_lock:
        pending_before_start = network._pending_network_messages
        network._pending_network_messages = max(
            0, network._pending_network_messages - 1
        )
        pending_after_start = network._pending_network_messages
    profiler.add_metric("transport.network.pending_before_start", pending_before_start)
    profiler.add_metric("transport.network.pending_after_start", pending_after_start)
    ctx = network._build_context(bus, client_id, msg)
    req_ctx_token = set_req_ctx(ctx)
    try:
        if getattr(ctx, "auth_error", None) == "token_expired":
            await _send_token_expired_response(network, bus, client_id, msg, ctx)
            finish_request_flow(msg["request_id"], outcome="ok")
            return
        trace_request_step(
            msg["request_id"],
            "protocol.dispatch",
            message_type=message_type,
            client_id=str(client_id),
        )
        with profiler.span("transport.dispatch"):
            await network.dispatcher.dispatch(bus, client_id, msg)
        finish_request_flow(msg["request_id"], outcome="ok")
    except Exception as exc:
        finish_request_flow(msg["request_id"], outcome="error", error=str(exc))
        raise
    finally:
        reset_req_ctx(req_ctx_token)
        if owns_profile:
            profiler.finish()
            if profile_token is not None:
                network_mod.stop_request_profile(profile_token)


async def _send_token_expired_response(network, bus, client_id, msg, ctx) -> None:
    from democrai.core.application.home import resolve_guest_page_path
    from democrai.core.application.routing.router_resolution import is_public_path
    from democrai.core.application.session.service import SessionService
    from democrai.core.application.session_keys import SessionKey

    guest_path = resolve_guest_page_path()
    response = {
        "request_id": msg["request_id"],
        "jwt": "",
        "eventNotification": {
            "kind": "toast",
            "variant": "warning",
            "title": "Session expired",
            "text": "Login again.",
        },
    }
    current_path = msg.get("current_path")
    if not isinstance(current_path, str) or not is_public_path(current_path):
        response["current_path"] = guest_path
    bus.send(client_id, response)
    session = network.core.get_session(None, None, session_key=ctx.session_key)
    session[SessionKey.CURRENT_PATH] = (
        response.get("current_path") or current_path or guest_path
    )
    session[SessionKey.USER] = SessionService.build_guest_session_user()
    render_messages = await network.core.render(session, force_shell=True)
    for render_message in render_messages:
        if isinstance(render_message, dict) and "request_id" not in render_message:
            render_message["request_id"] = msg["request_id"]
        bus.send(client_id, render_message)
    await network._cleanup_client(bus, client_id)


def init_dispatcher(network):
    for message_type, method_name in PROTOCOL_HANDLER_METHODS:
        network.dispatcher.register(message_type, getattr(network, method_name))
    network.dispatcher.set_default_handler(
        getattr(network, DEFAULT_PROTOCOL_HANDLER_METHOD)
    )
