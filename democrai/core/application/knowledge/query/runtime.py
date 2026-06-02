from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.application.knowledge.query.client import KnowledgeQueryClient
from democrai.core.application.knowledge.query.config import (
    knowledge_query_enabled,
    knowledge_query_startup_timeout_seconds,
    knowledge_query_target,
)


async def _run_knowledge_query_service(ctx: Any) -> None:
    from democrai.core.application.knowledge.query.server import serve_until_stopped

    stop_event = asyncio.Event()
    ctx.knowledge_query_stop_event = stop_event
    await serve_until_stopped(stop_event=stop_event)


def start_knowledge_query_service(ctx: Any) -> None:
    if ctx.setup_mode:
        return None
    if not knowledge_query_enabled(ctx.config):
        return None
    existing = ctx.knowledge_query_future
    if existing is not None and not existing.done():
        return None
    network = ctx.network
    loop = network._loop if network is not None else None
    if loop is None:
        raise RuntimeError("knowledge_query_network_loop_required")

    future = asyncio.run_coroutine_threadsafe(_run_knowledge_query_service(ctx), loop)
    ctx.knowledge_query_future = future
    timeout = knowledge_query_startup_timeout_seconds(ctx.config)
    target = knowledge_query_target(ctx.config)
    status = KnowledgeQueryClient(target=target).wait_ready(timeout=timeout)
    logger = ctx.logger
    if logger is not None:
        logger.info(
            f"[Bootstrap] Knowledge query service started pid={status.pid} "
            f"status_pid={status.pid} target={target}"
        )
    return None


def stop_knowledge_query_service(ctx: Any) -> None:
    stop_event = ctx.knowledge_query_stop_event
    network = ctx.network
    loop = network._loop if network is not None else None
    if stop_event is not None and loop is not None:
        loop.call_soon_threadsafe(stop_event.set)
    future = ctx.knowledge_query_future
    if future is not None:
        try:
            future.result(timeout=5)
        except Exception as exc:
            logger = ctx.logger
            if logger is not None:
                logger.error(f"[KnowledgeQuery] Service stop failed: {exc}")
    ctx.knowledge_query_stop_event = None
    ctx.knowledge_query_future = None


def start_knowledge_query_process(ctx: Any) -> None:
    start_knowledge_query_service(ctx)
