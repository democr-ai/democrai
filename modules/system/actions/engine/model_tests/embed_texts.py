from __future__ import annotations

import time
from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.actions.engine.model_tests.structured_result import (
    append_structured_error,
    append_structured_success,
    append_structured_trace,
    clear_structured_result,
    update_structured_status,
)


@action("test_engine_model_embed_texts")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_embed_texts(ctx: dict[str, Any], module_sdk):
    method = "embed_texts"
    stream_id = str(ctx.get("stream_id") or "")
    test_ctx = load_context(ctx, module_sdk, require_prompt=False)
    if test_ctx is None:
        return module_sdk.effects.respond(module_sdk.effects.render())
    if not stream_id:
        raise RuntimeError("stream_id_required")

    await clear_structured_result(module_sdk, stream_id)
    try:
        texts = [
            item.strip()
            for item in str(test_ctx.payload.get("texts") or "").splitlines()
            if item.strip()
        ]
        if not texts:
            raise ValueError("texts_required")
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="embed request",
            payload={"model_row_id": test_ctx.row_id, "items": len(texts)},
        )
        provider, warmup_ms, provider_error = await get_provider(module_sdk, test_ctx.row_id)
        if provider is None:
            await append_structured_error(
                module_sdk,
                stream_id,
                method=method,
                message=provider_error,
            )
            await update_structured_status(module_sdk, stream_id, "error")
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {"level": "error", "message": provider_error},
                )
            )
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="provider ready",
            payload={"warmup_ms": warmup_ms},
        )
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="engine call started",
            payload={"method": method, "items": len(texts)},
        )
        started = time.perf_counter()
        response = await provider.embed_texts(texts=texts)
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        vectors = list(response or [])
        dimensions = len(vectors[0]) if vectors and isinstance(vectors[0], list) else 0
        result = {
            "items": len(vectors),
            "dimensions": dimensions,
            "preview": vectors[0][:8] if vectors and isinstance(vectors[0], list) else [],
        }
        await append_structured_trace(
            module_sdk,
            stream_id,
            method=method,
            label="engine response received",
            payload={"items": len(vectors), "dimensions": dimensions},
        )
        await append_structured_success(
            module_sdk,
            stream_id,
            method=method,
            result_label="embeddings",
            result=result,
            stats=getattr(response, "stats", {}),
            extra_stats={"items": len(vectors), "dimensions": dimensions},
        )
        await update_structured_status(module_sdk, stream_id, "ok")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "success",
                    "message": module_sdk.i18n.t("system.engine.model.test.completed"),
                },
            )
        )
    except Exception as exc:
        await append_structured_error(module_sdk, stream_id, method=method, message=str(exc))
        await update_structured_status(module_sdk, stream_id, "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify("toast", {"level": "error", "message": str(exc)})
        )
