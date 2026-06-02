from __future__ import annotations

from democrai.core.application.request_cycle import infer_request_kind
from democrai.core.infrastructure.network.flows.stream_bindings import (
    register_stream_bindings_from_message,
)
from democrai.core.platform.utils.debug import debug_auth_flow as _debug_auth_flow
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.observability.profiling import ensure_request_profile
from democrai.core.runtime.observability.request_flow import trace_request_step


async def launch_request(network, bus, client_id, msg, ctx):
    profiler, _, _ = ensure_request_profile(
        ctx.request_id,
        infer_request_kind(msg),
    )
    try:
        trace_request_step(
            ctx.request_id,
            "request.launch",
            message_type=msg.get("type") or infer_request_kind(msg),
            action_name=ctx.action_name,
            user=ctx.user,
            organization_id=ctx.organization_id,
        )
        resps = await network.core.handle(msg)
        clear_auth_after_response = response_clears_auth(resps)
        if resps:
            for response in resps:
                if isinstance(response, dict) and "request_id" not in response:
                    response["request_id"] = ctx.request_id
                if isinstance(response, dict):
                    register_stream_bindings_from_message(
                        network,
                        bus,
                        client_id,
                        response,
                    )
                    _debug_auth_flow(
                        "network.send_response",
                        request_id=ctx.request_id,
                        response_keys=list(response.keys()),
                        has_jwt=("jwt" in response),
                        jwt_len=len(str(response.get("jwt") or "")),
                    )
                with profiler.span("transport.bus.send"):
                    bus.send(client_id, response)
        else:
            with profiler.span("transport.bus.send"):
                bus.send(
                    client_id,
                    {"type": "request_ack", "request_id": ctx.request_id},
                )
        trace_request_step(
            ctx.request_id,
            "response.sent",
            response_count=len(resps or []),
            clear_auth=clear_auth_after_response,
        )
        if clear_auth_after_response:
            await network._cleanup_client(bus, client_id)
    except Exception as exc:
        trace_request_step(
            ctx.request_id,
            "response.error",
            error=str(exc),
        )
        import traceback

        app_ctx().logger.error(f"[Network] Task error: {exc}\n{traceback.format_exc()}")
        with profiler.span("transport.bus.send"):
            bus.send(
                client_id,
                {"type": "error", "error": "An unexpected error occurred.", "request_id": ctx.request_id},
            )


def response_clears_auth(responses) -> bool:
    if not isinstance(responses, list):
        return False
    for response in responses:
        if not isinstance(response, dict):
            continue
        if response.get("jwt") == "":
            return True
    return False
