from __future__ import annotations

from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.actions.engine.model_tests.transcribe_result import (
    append_transcribe_error,
    append_transcribe_success,
    append_transcribe_trace,
    clear_transcribe_result,
    update_transcribe_status,
)
from modules.system.utils.actions.engine.model_test_support import (
    _media_bytes_from_upload,
    _upload_mime,
)


@action("test_engine_model_transcribe")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_transcribe(ctx: dict[str, Any], module_sdk):
    stream_id = str(ctx.get("stream_id") or "")
    test_ctx = load_context(ctx, module_sdk, require_prompt=False)
    if test_ctx is None:
        return module_sdk.effects.respond(module_sdk.effects.render())
    if not stream_id:
        raise RuntimeError("stream_id_required")

    await clear_transcribe_result(module_sdk, stream_id)
    try:
        audio_data = _media_bytes_from_upload(module_sdk, test_ctx.payload, "audio")
        audio_mime = _upload_mime(test_ctx.payload, "audio")
        await append_transcribe_trace(
            module_sdk,
            stream_id,
            label="transcribe request",
            payload={
                "model_row_id": test_ctx.row_id,
                "audio_bytes": len(audio_data),
                "audio_mime": audio_mime,
            },
        )
        provider, warmup_ms, provider_error = await get_provider(
            module_sdk,
            test_ctx.row_id,
        )
        if provider is None:
            await append_transcribe_error(
                module_sdk,
                stream_id,
                message=provider_error,
            )
            await update_transcribe_status(module_sdk, stream_id, "error")
            return module_sdk.effects.respond(
                module_sdk.effects.notify(
                    "toast",
                    {"level": "error", "message": provider_error},
                )
            )
        await append_transcribe_trace(
            module_sdk,
            stream_id,
            label="provider ready",
            payload={"warmup_ms": warmup_ms},
        )
        language = str(
            test_ctx.payload.get("language")
            or test_ctx.test_config.get("language")
            or test_ctx.runtime.get("language")
            or ""
        ).strip()
        await append_transcribe_trace(
            module_sdk,
            stream_id,
            label="engine call started",
            payload={"method": "transcribe", "language": language or None},
        )
        response = await provider.transcribe(
            audio_data=audio_data,
            language=language or None,
        )
        text = _response_text(response)
        response_language = _response_language(response)
        audio_duration_seconds = _response_duration(response)
        await append_transcribe_trace(
            module_sdk,
            stream_id,
            label="engine response received",
            payload={
                "text_chars": len(text),
                "language": response_language,
                "audio_duration_seconds": audio_duration_seconds,
            },
        )
        await append_transcribe_success(
            module_sdk,
            stream_id,
            text=text,
            language=response_language,
            audio_bytes=len(audio_data),
            audio_duration_seconds=audio_duration_seconds,
            stats=getattr(response, "stats", {}),
        )
        await update_transcribe_status(module_sdk, stream_id, "ok")
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
        await append_transcribe_error(module_sdk, stream_id, message=str(exc))
        await update_transcribe_status(module_sdk, stream_id, "error")
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {"level": "error", "message": str(exc)},
            )
        )


def _response_text(response: Any) -> str:
    result = _response_result(response)
    if isinstance(result, dict):
        return str(result.get("text") or "").strip()
    return str(getattr(result, "text", "") or "").strip()


def _response_language(response: Any) -> str:
    result = _response_result(response)
    if isinstance(result, dict):
        return str(result.get("language") or "").strip()
    return str(getattr(result, "language", "") or "").strip()


def _response_duration(response: Any) -> float | None:
    result = _response_result(response)
    value = (
        result.get("duration")
        if isinstance(result, dict)
        else getattr(result, "duration", None)
    )
    if isinstance(value, int | float):
        return float(value)
    return None


def _response_result(response: Any) -> Any:
    return getattr(response, "result", response)
