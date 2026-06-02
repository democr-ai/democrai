from __future__ import annotations

import io
import wave
from typing import Any

from democrai.sdk.decorators import action
from democrai.sdk.auth import permission_required

from modules.system.actions.engine.model_tests.common import get_provider, load_context
from modules.system.actions.engine.model_tests.synthesize_result import (
    append_synthesize_error,
    append_synthesize_success,
    append_synthesize_trace,
    clear_synthesize_result,
    update_synthesize_status,
)
from modules.system.utils.actions.engine.model_test_support import (
    _number_value,
    _save_speech_response_media,
)


@action("test_engine_model_synthesize")
@permission_required(["system.engine.model.manage"])
async def test_engine_model_synthesize(ctx: dict[str, Any], module_sdk):
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
        label="synthesize request",
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
            payload={"method": "synthesize", "options": _trace_options(options)},
        )
        response = await provider.synthesize(text=test_ctx.prompt, options=options)
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
            audio_source=audio_source,
            content_type=_response_content_type(response),
            audio_bytes=_response_audio_bytes(response),
            prompt_chars=len(test_ctx.prompt),
            duration_seconds=_response_duration(response),
            stats=getattr(response, "stats", {}),
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


def _synthesize_options(test_ctx) -> dict[str, Any]:
    return {
        "voice": str(
            test_ctx.payload.get("voice")
            or test_ctx.test_config.get("voice")
            or test_ctx.runtime.get("voice")
            or ""
        ),
        "model": str(test_ctx.row.get("model_path") or ""),
        "wpm": int(
            _number_value(
                test_ctx.payload.get("wpm") or test_ctx.runtime.get("wpm"),
                175,
            )
        ),
        "pitch": int(
            _number_value(
                test_ctx.payload.get("pitch") or test_ctx.runtime.get("pitch"),
                50,
            )
        ),
        "amplitude": int(
            _number_value(
                test_ctx.payload.get("amplitude") or test_ctx.runtime.get("amplitude"),
                100,
            )
        ),
        "word_gap": int(
            _number_value(
                test_ctx.payload.get("word_gap") or test_ctx.runtime.get("word_gap"),
                0,
            )
        ),
        "response_format": str(
            test_ctx.payload.get("response_format")
            or test_ctx.runtime.get("response_format")
            or "wav"
        ),
    }


def _trace_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in dict(options or {}).items()
        if key
        in {
            "voice",
            "wpm",
            "pitch",
            "amplitude",
            "word_gap",
            "response_format",
        }
    }


def _response_content_type(response: Any) -> str:
    if isinstance(response, dict):
        return str(response.get("content_type") or "audio/mpeg")
    return str(getattr(response, "content_type", None) or "audio/mpeg")


def _response_audio_bytes(response: Any) -> int:
    return len(_response_audio_data(response))


def _response_duration(response: Any) -> float | None:
    value = (
        response.get("duration")
        if isinstance(response, dict)
        else getattr(response, "duration", None)
    )
    if isinstance(value, int | float):
        return float(value)
    return _wav_duration_seconds(_response_audio_data(response))


def _response_audio_data(response: Any) -> bytes:
    data = (
        response.get("data")
        if isinstance(response, dict)
        else getattr(response, "data", None)
    )
    return bytes(data) if isinstance(data, bytes | bytearray) else b""


def _wav_duration_seconds(data: bytes) -> float | None:
    if not data.startswith(b"RIFF"):
        return None
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            frame_rate = wav.getframerate()
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            if frame_rate <= 0:
                return None
            data_start = _wav_data_start(data)
            bytes_per_frame = channels * sample_width
            if data_start is not None and bytes_per_frame > 0:
                available_audio_bytes = max(0, len(data) - data_start)
                frame_count = available_audio_bytes // bytes_per_frame
            else:
                frame_count = wav.getnframes()
            return round(float(frame_count) / float(frame_rate), 3)
    except wave.Error:
        return None
    return None


def _wav_data_start(data: bytes) -> int | None:
    marker_index = data.find(b"data")
    if marker_index < 0:
        return None
    return marker_index + 8
