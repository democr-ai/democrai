from __future__ import annotations

from democrai.core.runtime.foundation.app import req_ctx


async def handle_legacy_launch(network, bus, client_id, msg):
    ctx = req_ctx()
    if not network._is_legacy_message_allowed_for_context(msg, ctx):
        network._send_auth_error(bus, client_id, msg, "authentication_required")
        return
    stream_id = network._authorize_and_bind_stream(
        bus, client_id, msg, ctx, reject_on_unauthenticated=False
    )
    if stream_id is None and "stream_id" in msg:
        return
    ctx.stream_id = stream_id or ctx.stream_id
    await network._launch_request(bus, client_id, msg, ctx)
