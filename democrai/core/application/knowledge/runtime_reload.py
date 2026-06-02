from __future__ import annotations

from typing import Any

from democrai.core.runtime.foundation.app import app_ctx


def reload_knowledge_runtime(ctx: Any | None = None) -> None:
    resolved_ctx = ctx if ctx is not None else app_ctx()
    if getattr(resolved_ctx, "setup_mode", False):
        return

    runtime = getattr(resolved_ctx, "knowledge_runtime", None)
    if runtime is not None:
        runtime.stop()

    from democrai.core.runtime.bootstrap import bootstrap_pipeline_helpers

    bootstrap_pipeline_helpers.init_knowledge(resolved_ctx)
    runtime = getattr(resolved_ctx, "knowledge_runtime", None)
    if runtime is not None:
        runtime.start()
