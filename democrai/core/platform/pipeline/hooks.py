from __future__ import annotations

from typing import Any, Literal

from democrai.core.runtime.foundation.app import app_ctx

from .models import PipelineContext
from .registry import pipeline_hook_registry


def _apply_chain_result(hook_name: str, ctx: PipelineContext, result: Any) -> PipelineContext:
    if hook_name == "chat.post_response":
        ctx.response_text = result if isinstance(result, str) else ""
    elif hook_name == "chat.pre_llm":
        value = result.strip() if isinstance(result, str) else ""
        if value:
            ctx.extra_system_prompts.append(value)
    elif hook_name == "chat.on_memory_write" and isinstance(result, dict):
        ctx.metadata["memory_chunk"] = dict(result)
    return ctx


async def resolve_pipeline_hook(
    hook_name: str,
    ctx: PipelineContext,
    *,
    merge_strategy: Literal["accumulate", "replace", "chain"] = "accumulate",
) -> Any:
    registrations = pipeline_hook_registry.get(hook_name)
    results: list[Any] = []

    for reg in registrations:
        try:
            result = await reg.func(ctx)
        except Exception as exc:  # pragma: no cover - defensive runtime isolation
            app_ctx().logger.error(
                f"Hook '{hook_name}' from '{reg.module_name}' failed: {exc}"
            )
            continue
        if result is None:
            continue
        if merge_strategy == "accumulate":
            if isinstance(result, list):
                results.extend(result)
            else:
                results.append(result)
        elif merge_strategy == "replace":
            results = [result]
        elif merge_strategy == "chain":
            ctx = _apply_chain_result(hook_name, ctx, result)
            results = [result]

    if merge_strategy == "accumulate":
        return results
    return results[0] if results else None
