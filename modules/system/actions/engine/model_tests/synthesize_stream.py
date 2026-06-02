from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.actions.engine.model_tests.synthesize import (
    _response_audio_bytes,
    _response_content_type,
    _response_duration,
    _synthesize_options,
    _trace_options,
)
from modules.system.actions.engine.model_tests.synthesize_result import (
    append_synthesize_error,
    append_synthesize_success,
    append_synthesize_trace,
    clear_synthesize_result,
    update_synthesize_status,
)
from modules.system.utils.actions.engine.model_test_support import (
    _save_speech_response_media,
)


@action("test_engine_model_synthesize_stream")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_synthesize_stream(ctx: dict[str, Any], module_sdk):
    stream_id = str(ctx.get("stream_id") or "")
    test_ctx = load_context(ctx, module_sdk, require_prompt=True)
    if test_ctx is None:
        return module_sdk.effects.respond(module_sdk.effects.render())
    if not stream_id:
        raise RuntimeError("stream_id_required")

    await clear_synthesize_result(module_sdk, stream_id)
    await append_synthesize_trace(
        module_sdk,
        stream_id,
        label="synthesize stream request",
        payload={
            "model_row_id": test_ctx.row_id,
            "prompt_chars": len(test_ctx.prompt),
        },
    )
    try:
        provider, warmup_ms, provider_error = await get_provider(
            module_sdk,
            test_ctx.row_id,
        )
        if provider is None:
            await append_synthesize_error(
                module_sdk,
                stream_id,
                message=provider_error,
            )
            await update_synthesize_status(module_sdk, stream_id, "error")
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {"level": "error", "message": provider_error},
                )
            )
        await append_synthesize_trace(
            module_sdk,
            stream_id,
            label="provider ready",
            payload={"warmup_ms": warmup_ms},
        )
        options = _synthesize_options(test_ctx)
        await append_synthesize_trace(
            module_sdk,
            stream_id,
            label="engine call started",
            payload={"method": "synthesize_stream", "options": _trace_options(options)},
        )
        parts: list[bytes] = []
        chunks = 0
        stream_stats: dict[str, Any] = {}
        async for chunk in provider.synthesize_stream(
            text=test_ctx.prompt,
            options=options,
        ):
            if isinstance(chunk, bytes | bytearray):
                chunks += 1
                parts.append(bytes(chunk))
            elif isinstance(getattr(chunk, "stats", None), dict):
                stream_stats = dict(chunk.stats)
        response = {
            "data": b"".join(parts),
            "content_type": f"audio/{options['response_format']}",
        }
        await append_synthesize_trace(
            module_sdk,
            stream_id,
            label="engine stream completed",
            payload={"chunks": chunks, "audio_bytes": _response_audio_bytes(response)},
        )
        audio_source = _save_speech_response_media(module_sdk, test_ctx.row_id, response)
        await append_synthesize_trace(
            module_sdk,
            stream_id,
            label="media saved",
            payload={"audio_source": audio_source},
        )
        await append_synthesize_success(
            module_sdk,
            stream_id,
            method="synthesize_stream",
            audio_source=audio_source,
            content_type=_response_content_type(response),
            audio_bytes=_response_audio_bytes(response),
            prompt_chars=len(test_ctx.prompt),
            duration_seconds=_response_duration(response),
            stats=stream_stats,
            stream_chunks=chunks,
        )
        await update_synthesize_status(module_sdk, stream_id, "ok")
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
        await append_synthesize_error(module_sdk, stream_id, message=str(exc))
        await update_synthesize_status(module_sdk, stream_id, "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": str(exc)},
            )
        )
