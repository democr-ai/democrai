from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from democrai.core.application.ai.engine.runtime.environment import (
    resource_snapshot,
    runtime_config_signature,
    runtime_node_id,
)
from democrai.core.platform.utils.identity import to_optional_int


@dataclass
class RuntimeEventRecorder:
    event_type: str
    engine_row_id: int
    model_registry_id: int | None
    engine_id: str
    config: dict[str, Any]
    before: dict[str, Any]
    started: float

    def finish(self, *, success: bool, error: str | None = None) -> None:
        record_runtime_event(
            event_type=self.event_type,
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            engine_id=self.engine_id,
            config=self.config,
            warmup_ms=None
            if self.event_type == "reuse"
            else round((time.perf_counter() - self.started) * 1000.0, 2),
            before=self.before,
            after=resource_snapshot(),
            success=success,
            error=error,
        )


def begin_runtime_event(
    *,
    using_existing: bool,
    engine_row_id: int,
    model_registry_id: int | None = None,
    engine_id: str,
    config: dict[str, Any],
) -> RuntimeEventRecorder:
    return RuntimeEventRecorder(
        event_type="reuse" if using_existing else "warmup",
        engine_row_id=engine_row_id,
        model_registry_id=model_registry_id,
        engine_id=engine_id,
        config=config,
        before=resource_snapshot(),
        started=time.perf_counter(),
    )


def record_runtime_event(
    *,
    event_type: str,
    engine_row_id: int,
    model_registry_id: int | None = None,
    engine_id: str,
    config: dict[str, Any],
    warmup_ms: float | None,
    before: dict[str, Any],
    after: dict[str, Any],
    success: bool,
    error: str | None = None,
) -> None:
    vram_before = to_optional_int(before.get("vram_used_mb"))
    vram_after = to_optional_int(after.get("vram_used_mb"))
    ram_before = to_optional_int(before.get("ram_used_mb"))
    ram_after = to_optional_int(after.get("ram_used_mb"))
    vram_delta = (
        max(0, int(vram_after) - int(vram_before))
        if vram_before is not None and vram_after is not None
        else None
    )
    try:
        from democrai.core.application.observability.service import observability_service

        observability_service.record_ai_model_runtime(
            event_type=event_type,
            provider=engine_id,
            engine=engine_id,
            engine_row_id=engine_row_id,
            model_registry_id=model_registry_id,
            model_name=config.get("model") or config.get("model_path"),
            node_id=runtime_node_id() or None,
            config_signature=runtime_config_signature(config),
            warmup_ms=warmup_ms,
            vram_before_mb=vram_before,
            vram_after_mb=vram_after,
            vram_delta_mb=vram_delta,
            runtime_allocated_vram_mb=vram_delta,
            ram_before_mb=ram_before,
            ram_after_mb=ram_after,
            success=success,
            error=error,
        )
    except Exception:
        return
