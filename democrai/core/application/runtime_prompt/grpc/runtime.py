from __future__ import annotations

import asyncio
import time
from typing import Any

from democrai.core.application.runtime_prompt.grpc.config import (
    cleanup_runtime_prompt_socket,
    runtime_prompt_start_timeout_seconds,
    runtime_prompt_target,
)


def start_runtime_prompt_grpc_server(ctx: Any) -> None:
    if getattr(ctx, "setup_mode", False):
        return
    network = getattr(ctx, "network", None)
    loop = getattr(network, "_loop", None)
    if loop is None:
        raise RuntimeError("runtime_prompt_network_loop_required")
    existing = getattr(ctx, "runtime_prompt_grpc_future", None)
    if existing is not None and not existing.done():
        return

    async def _serve() -> None:
        from democrai.core.application.runtime_prompt.grpc.server import (
            serve_until_stopped,
        )

        await serve_until_stopped()

    future = asyncio.run_coroutine_threadsafe(_serve(), loop)
    ctx.runtime_prompt_grpc_future = future
    config = getattr(ctx, "config", None)
    deadline = time.monotonic() + runtime_prompt_start_timeout_seconds(config)
    while getattr(ctx, "runtime_prompt_grpc_server", None) is None:
        if future.done():
            future.result()
        if time.monotonic() >= deadline:
            future.cancel()
            ctx.runtime_prompt_grpc_future = None
            cleanup_runtime_prompt_socket(config)
            raise RuntimeError("runtime_prompt_grpc_start_timeout")
        time.sleep(0.05)

    logger = getattr(ctx, "logger", None)
    if logger is not None:
        target = runtime_prompt_target(getattr(ctx, "config", None))
        logger.info(
            f"[Bootstrap] Runtime prompt gRPC server ready target={target}"
        )
