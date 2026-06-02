from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Any, Callable

from modules.system.utils.actions.engine.model_test_support import (
    _required_prompt,
    _state_result_update,
    _test_result,
)


@dataclass
class ModelTestContext:
    row_id: int
    row: dict[str, Any]
    payload: dict[str, Any]
    extra_config: dict[str, Any]
    defaults: dict[str, Any]
    generation: dict[str, Any]
    runtime: dict[str, Any]
    test_config: dict[str, Any]
    prompt: str


def load_context(
    ctx: dict[str, Any],
    module_sdk,
    *,
    require_prompt: bool = False,
) -> ModelTestContext | None:
    if "model_row_id" not in ctx:
        return None
    row_id = int(ctx["model_row_id"])
    row = module_sdk.models.model_registry.view(row_id)
    if not isinstance(row, dict):
        return None
    payload = dict(ctx[str(ctx["form_id"])])
    extra_config = (
        row.get("extra_config") if isinstance(row.get("extra_config"), dict) else {}
    )
    defaults = (
        extra_config.get("defaults")
        if isinstance(extra_config.get("defaults"), dict)
        else {}
    )
    generation = (
        defaults.get("generation")
        if isinstance(defaults.get("generation"), dict)
        else {}
    )
    runtime = (
        defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    )
    test_config = (
        extra_config.get("test_config")
        if isinstance(extra_config.get("test_config"), dict)
        else {}
    )
    prompt = (
        _required_prompt(payload, test_config, module_sdk)
        if require_prompt
        else str(payload.get("prompt") or test_config.get("prompt") or "").strip()
    )
    return ModelTestContext(
        row_id=row_id,
        row=row,
        payload=payload,
        extra_config=extra_config,
        defaults=defaults,
        generation=generation,
        runtime=runtime,
        test_config=test_config,
        prompt=prompt,
    )


def render_response(module_sdk, result: dict[str, Any], *, error: Exception | None = None):
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([_state_result_update(result)]),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "error" if error is not None else "success",
                "message": (
                    str(error)
                    if error is not None
                    else module_sdk.i18n.t("system.engine.model.test.completed")
                ),
            },
        ),
    )


async def get_provider(module_sdk, row_id: int):
    provider_result = await module_sdk.ai.get_provider_by_model_registry_id(row_id)
    if provider_result.get("status") != "ok" or not provider_result.get("provider"):
        message = str(provider_result.get("error") or "provider_unavailable")
        if provider_result.get("status") == "need_confirmation":
            to_unload = provider_result.get("to_unload")
            if to_unload:
                message = f"need_confirmation: {to_unload}"
        return None, None, message
    warmup = await module_sdk.ai.warmup_provider(
        provider_result["provider"],
        wait=True,
    )
    if warmup is None:
        return provider_result["provider"], None, ""
    if warmup.get("status") != "ok":
        return (
            None,
            warmup.get("warmup_ms"),
            str(warmup.get("error") or "provider_warmup_failed"),
        )
    return provider_result["provider"], warmup.get("warmup_ms"), ""


async def run_simple_provider_test(
    ctx: dict[str, Any],
    module_sdk,
    *,
    method: str,
    require_prompt: bool,
    execute: Callable[[ModelTestContext, Any], Any],
    enrich_result: Callable[[dict[str, Any]], None] | None = None,
):
    test_ctx = load_context(ctx, module_sdk, require_prompt=require_prompt)
    if test_ctx is None:
        return module_sdk.effects.respond(module_sdk.effects.render())
    try:
        provider, warmup_ms, provider_error = await get_provider(
            module_sdk,
            test_ctx.row_id,
        )
        if provider is None:
            result = _test_result(
                status="error",
                method=method,
                output=provider_error,
                warmup_ms=warmup_ms,
            )
            return render_response(module_sdk, result, error=RuntimeError(provider_error))
        started = time.perf_counter()
        response, output, chunks = await execute(test_ctx, provider)
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        stats = getattr(response, "stats", {})
        result = _test_result(
            status="ok",
            method=method,
            output=output,
            warmup_ms=warmup_ms,
            duration_ms=stats.get("duration_ms", duration_ms),
            prompt_tokens=stats.get("prompt_tokens"),
            completion_tokens=stats.get("completion_tokens"),
            total_tokens=stats.get("total_tokens"),
            tokens_per_second=stats.get("tokens_per_second"),
            chunks=chunks,
        )
        if enrich_result is not None:
            enrich_result(result)
        return render_response(module_sdk, result)
    except Exception as exc:
        result = _test_result(status="error", method=method, output=str(exc))
        return render_response(module_sdk, result, error=exc)
