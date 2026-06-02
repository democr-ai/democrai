from __future__ import annotations

import asyncio

from democrai.core.application.ai.engine.orchestrator.config import (
    orchestrator_registry_reconcile_seconds,
)
from democrai.core.runtime.foundation.app import app_ctx


async def reconcile_registries_until_stopped(stop_event: asyncio.Event) -> None:
    interval = orchestrator_registry_reconcile_seconds(app_ctx().config)
    logger = getattr(app_ctx(), "logger", None)
    while not stop_event.is_set():
        try:
            from democrai.core.application.ai.engine.manifests import (
                sync_engine_manifests_to_registry,
            )

            sync_engine_manifests_to_registry()
        except Exception as exc:
            if logger is not None:
                logger.warning(f"[EngineOrchestrator] registry reconcile failed: {exc}")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            continue
