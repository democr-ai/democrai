from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from datetime import timezone
from typing import Any

from democrai.core.application.ai.engine.install_events import get_runtime_node_id
from democrai.core.application.environment.definitions import verify_env_name
from democrai.core.application.environment.definitions import verify_subject
from democrai.core.application.environment.definitions import verify_subject_kind
from democrai.core.application.environment.service import apply_environment_variables
from democrai.core.runtime.foundation.app import app_ctx


ENVIRONMENT_STREAM_ID = "system.environment.events"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def build_environment_changed_event(
    *,
    operation: str,
    subject_kind: str,
    subject: str,
    name: str,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_name": "environment.variable.changed",
        "operation": operation,
        "subject_kind": verify_subject_kind(subject_kind),
        "subject": verify_subject(subject),
        "name": verify_env_name(name),
        "source_node_id": get_runtime_node_id(),
        "requested_at": _utc_now_iso(),
    }


async def publish_environment_changed(
    *,
    operation: str,
    subject_kind: str,
    subject: str,
    name: str,
) -> dict[str, Any]:
    event = build_environment_changed_event(
        operation=operation,
        subject_kind=subject_kind,
        subject=subject,
        name=name,
    )
    network = getattr(app_ctx(), "network", None)
    if network is None:
        return event
    await network.stream_manager.broadcast(ENVIRONMENT_STREAM_ID, event)
    return event


async def process_environment_event(payload: dict[str, Any]) -> None:
    if payload.get("event_name") != "environment.variable.changed":
        return
    if payload.get("source_node_id") == get_runtime_node_id():
        return
    name = verify_env_name(payload["name"])
    apply_environment_variables(name=name)


async def _consume_environment_stream() -> None:
    network = getattr(app_ctx(), "network", None)
    if network is None:
        return
    queue = network.stream_manager.subscribe(ENVIRONMENT_STREAM_ID)
    try:
        while True:
            payload = await queue.get()
            if isinstance(payload, dict):
                await process_environment_event(payload)
    except asyncio.CancelledError:
        pass
    finally:
        network.stream_manager.unsubscribe(ENVIRONMENT_STREAM_ID, queue)


def start_environment_variable_consumer() -> None:
    ctx = app_ctx()
    network = getattr(ctx, "network", None)
    if network is None or getattr(network, "_loop", None) is None:
        return
    if getattr(ctx, "environment_variable_consumer", None) is not None:
        return
    ctx.environment_variable_consumer = asyncio.run_coroutine_threadsafe(
        _consume_environment_stream(),
        network._loop,
    )
