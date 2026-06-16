from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.infrastructure.ai.engine.invocation.config import (
    EngineInvocationRuntimeConfig,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.application.ai.engine.orchestrator.node_views import (
    load_active_node_views,
)
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.infrastructure.ai.engine.response.factory import (
    resolve_engine_response_stream,
)
from democrai.core.infrastructure.ai.engine.response.stream import EngineResponseStream
from democrai.core.infrastructure.database.models import EngineInvocationQueue
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.runtime.foundation.app import app_ctx


_ORPHANED_HITL_ERROR = "engine_resource_swap_confirmation_unavailable"


class EngineQueueMaintenance:
    """Slow background loop: purges terminal queue rows past retention and
    dead-letters HITL-bound rows whose origin node is gone (nobody else may
    claim them, so without this they would stay pending forever)."""

    def __init__(
        self,
        *,
        node_id: str,
        store: EngineInvocationQueueStore | None = None,
        response_stream: EngineResponseStream | Any | None = None,
        interval_seconds: float = 60.0,
        orphan_origin_check_enabled: bool = False,
    ) -> None:
        config = app_ctx().config
        self._node_id = node_id
        self._store = store or EngineInvocationQueueStore()
        self._response_stream = resolve_engine_response_stream(response_stream)
        self._interval_seconds = max(5.0, float(interval_seconds))
        self._orphan_origin_check_enabled = bool(orphan_origin_check_enabled)
        runtime_config = EngineInvocationRuntimeConfig.load(config)
        self._retention_seconds = runtime_config.queue_retention_seconds
        self._threshold_seconds = runtime_config.node_state_active_threshold_seconds

    def _orphaned_origin_hitl_rows(self) -> list[dict[str, Any]]:
        active = {
            view.node_id
            for view in load_active_node_views(
                threshold_seconds=self._threshold_seconds
            )
        }
        with SessionLocal() as session:
            rows = (
                session.query(EngineInvocationQueue)
                .filter(EngineInvocationQueue.requires_origin_hitl.is_(True))
                .filter(EngineInvocationQueue.status.in_(("pending", "failed")))
                .all()
            )
            return [
                {
                    "id": row.id,
                    "response_stream_key": row.response_stream_key,
                }
                for row in rows
                if row.origin_node_id not in active
            ]

    async def run_once(self) -> None:
        await asyncio.to_thread(
            self._store.purge_terminal, retention_seconds=self._retention_seconds
        )
        if not self._orphan_origin_check_enabled:
            return
        orphaned = await asyncio.to_thread(self._orphaned_origin_hitl_rows)
        for row in orphaned:
            status = await asyncio.to_thread(
                self._store.fail,
                row["id"],
                error=_ORPHANED_HITL_ERROR,
                retriable=False,
                max_attempts=1,
            )
            if status != "dead_letter":
                continue
            writer = EngineResponseStreamWriter(
                self._response_stream,
                str(row["response_stream_key"]),
                node_id=self._node_id,
            )
            try:
                await writer.error(_ORPHANED_HITL_ERROR)
            except Exception:
                pass

    async def run_until_stopped(self, stop_event: asyncio.Event) -> None:
        logger = getattr(app_ctx(), "logger", None)
        try:
            while not stop_event.is_set():
                try:
                    await self.run_once()
                except Exception as exc:
                    if logger is not None:
                        logger.warning(
                            f"[Engine] queue maintenance failed: {exc}"
                        )
                try:
                    await asyncio.wait_for(
                        stop_event.wait(), timeout=self._interval_seconds
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            try:
                await self._response_stream.aclose()
            except Exception:
                pass
