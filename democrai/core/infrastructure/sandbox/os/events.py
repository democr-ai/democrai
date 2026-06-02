from __future__ import annotations

import asyncio
import uuid
from typing import Any

from democrai.core.platform.events import emit_module_event
from democrai.core.platform.utils.debug import debug_os_sandbox_flow
from democrai.core.infrastructure.sandbox.process_guard import process_guard_bypass_context
from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.registry import module_event_registry

from .helper import apply_application_network_allowlist_with_helper
from .state import (
    is_application_network_allowlist_active,
    refresh_application_network_allowlist,
)


APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT = (
    "democrai.core.sandbox.os.allowlist.refresh_requested"
)
APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_ID = (
    "democrai.core.sandbox.os.allowlist.refresh.events"
)
APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_EVENT = (
    "sandbox.os.allowlist.refresh.requested"
)

_REGISTERED = False
_CONSUMER_STARTED = False
_PROCESSED_EVENT_IDS: set[str] = set()
_PROCESSED_EVENT_IDS_ORDER: list[str] = []
_MAX_PROCESSED_EVENT_IDS = 2048


def _remember_processed_event_id(event_id: str) -> None:
    normalized = str(event_id or "").strip()
    if not normalized or normalized in _PROCESSED_EVENT_IDS:
        return
    _PROCESSED_EVENT_IDS.add(normalized)
    _PROCESSED_EVENT_IDS_ORDER.append(normalized)
    if len(_PROCESSED_EVENT_IDS_ORDER) <= _MAX_PROCESSED_EVENT_IDS:
        return
    stale = _PROCESSED_EVENT_IDS_ORDER.pop(0)
    _PROCESSED_EVENT_IDS.discard(stale)


def _runtime_node_id() -> str:
    ctx = app_ctx()
    configured = str(getattr(ctx, "node_id", "") or "").strip()
    if configured:
        return configured
    cfg = getattr(ctx, "config", None)
    if cfg is not None:
        configured = str(cfg.get("network.node_id", "") or "").strip()
        if configured:
            ctx.node_id = configured
            return configured
    ctx.node_id = SERVER_NAME
    return SERVER_NAME


def _build_allowlist_refresh_requested_event(
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_name": APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_EVENT,
        "source_node_id": _runtime_node_id(),
        "payload": dict(payload or {}),
    }


def _engine_orchestrator_pid() -> int | None:
    process = getattr(app_ctx(), "engine_orchestrator_process", None)
    pid = getattr(process, "pid", None)
    if pid is None:
        return None
    try:
        return int(pid)
    except Exception:
        return None


async def _refresh_application_network_allowlist_listener(
    payload: dict[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    debug_os_sandbox_flow("event.listener_invoked", payload=payload or {})
    allowlist = refresh_application_network_allowlist()
    applied = False
    if is_application_network_allowlist_active():
        debug_os_sandbox_flow(
            "event.listener_apply_requested",
            endpoint_count=len(allowlist.endpoints),
        )
        engine_orchestrator_pid = _engine_orchestrator_pid()

        def _apply() -> None:
            with process_guard_bypass_context():
                apply_application_network_allowlist_with_helper(allowlist)
                if engine_orchestrator_pid is not None:
                    apply_application_network_allowlist_with_helper(
                        allowlist,
                        pid=engine_orchestrator_pid,
                    )

        await asyncio.to_thread(_apply)
        applied = True
    debug_os_sandbox_flow(
        "event.listener_completed",
        endpoint_count=len(allowlist.endpoints),
        applied=applied,
    )
    return {
        "endpoint_count": len(allowlist.endpoints),
        "applied": applied,
    }


def register_os_sandbox_event_listeners() -> None:
    global _REGISTERED
    if _REGISTERED:
        debug_os_sandbox_flow("event.listener_registration_skipped")
        return
    module_event_registry.declare(
        APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT,
        module_name="core",
        params=("reason", "resource_type", "module_name", "target", "mode"),
        optional=True,
        description="Refresh and optionally re-apply the OS network allowlist.",
    )
    module_event_registry.register(
        APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT,
        _refresh_application_network_allowlist_listener,
        priority=100,
        module_name="core",
    )
    _REGISTERED = True
    debug_os_sandbox_flow(
        "event.listener_registered",
        event_name=APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT,
    )


async def process_application_network_allowlist_refresh_event(
    payload: dict[str, Any] | None = None,
    *,
    session: dict | None = None,
) -> list[Any]:
    event_payload = dict(payload or {})
    event_id = str(event_payload.get("event_id") or "").strip()
    if event_id:
        if event_id in _PROCESSED_EVENT_IDS:
            debug_os_sandbox_flow("event.stream_skip_duplicate", event_id=event_id)
            return []
        _remember_processed_event_id(event_id)
    # event_id is transport metadata used for deduplication only.
    # Do not pass it to the module-event payload validation/contract.
    dispatched_payload = dict(event_payload)
    dispatched_payload.pop("event_id", None)

    debug_os_sandbox_flow(
        "event.process",
        event_name=APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT,
        payload=dispatched_payload,
    )
    return await emit_module_event(
        APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT,
        payload=dispatched_payload,
        session=session or {},
    )


async def _consume_application_network_allowlist_refresh_stream() -> None:
    network = getattr(app_ctx(), "network", None)
    if network is None:
        return
    queue = network.stream_manager.subscribe(
        APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_ID
    )
    try:
        while True:
            event = await queue.get()
            if not isinstance(event, dict):
                continue
            if (
                str(event.get("event_name") or "").strip()
                != APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_EVENT
            ):
                continue
            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}
            event_id = str(event.get("event_id") or "").strip()
            if event_id:
                payload = dict(payload)
                payload["event_id"] = event_id
            await process_application_network_allowlist_refresh_event(payload)
    except asyncio.CancelledError:
        pass
    finally:
        network.stream_manager.unsubscribe(
            APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_ID,
            queue,
        )


def start_application_network_allowlist_refresh_consumer() -> None:
    global _CONSUMER_STARTED
    if _CONSUMER_STARTED:
        return
    ctx = app_ctx()
    network = getattr(ctx, "network", None)
    if network is None or getattr(network, "_loop", None) is None:
        return
    asyncio.run_coroutine_threadsafe(
        _consume_application_network_allowlist_refresh_stream(),
        network._loop,
    )
    _CONSUMER_STARTED = True
    debug_os_sandbox_flow("event.stream_consumer_started")


async def emit_application_network_allowlist_refresh_event(
    *,
    payload: dict[str, Any] | None = None,
    session: dict | None = None,
) -> list[Any]:
    event_payload = dict(payload or {})
    debug_os_sandbox_flow(
        "event.emit",
        event_name=APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT,
        payload=event_payload,
    )
    network = getattr(app_ctx(), "network", None)
    if network is None:
        return await process_application_network_allowlist_refresh_event(
            event_payload,
            session=session or {},
        )

    event = _build_allowlist_refresh_requested_event(payload=event_payload)
    event_id = str(event.get("event_id") or "").strip()
    if event_id:
        event_payload["event_id"] = event_id
    await network.stream_manager.broadcast(
        APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_ID,
        event,
    )
    debug_os_sandbox_flow(
        "event.stream_published",
        event_id=event_id,
        source_node_id=event.get("source_node_id"),
    )
    return []
