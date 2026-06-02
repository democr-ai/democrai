from __future__ import annotations

import asyncio
import io
import re
import time
import wave
from typing import Any

from democrai.core.application.ai.engine.base.llm import ai_call_context
from democrai.core.application.ai.engine.base.llm import current_ai_call_context
from democrai.core.application.ai.engine.pipeline.usage import stream_usage_tuple
from democrai.core.application.ai.engine.pipeline.usage import speech_usage_metadata
from democrai.core.application.ai.engine.pipeline.usage import usage_tuple
from democrai.core.application.ai.engine.schemas.runtime import EngineMethodResponse
from democrai.core.application.ai.engine.schemas.runtime import EngineStreamFinal
from democrai.core.application.ai.engine.schemas.runtime import EngineUsage
from democrai.core.application.ai.engine.runtime.environment import runtime_config_signature
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import mark_step_progress
from democrai.core.application.ai.pipeline_context import pipeline_usage_metadata


VISUAL_BASE_PIXELS = 512 * 512


async def invoke_with_usage(
    provider: Any,
    method: str,
    payload: dict[str, Any] | None = None,
    *,
    metadata: dict[str, Any] | None = None,
    metadata_from_result: Any = None,
) -> Any:
    started_at = time.perf_counter()
    result: Any = None
    response: Any = None
    error: BaseException | None = None
    usage_step_id: str | None = None
    try:
        async with ai_pipeline_step(
            type="engine.call",
            name=method,
            input={"method": method},
        ) as step:
            usage_step_id = (
                step.get("step_id") if isinstance(step, dict) else None
            )
            with ai_call_context(**pipeline_usage_metadata(usage_step_id)):
                result = await asyncio.to_thread(provider._invoke, method, payload)
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            response = (
                result
                if method == "generate_completion"
                else _method_response(
                    provider=provider,
                    method=method,
                    payload=payload,
                    result=result,
                    duration_ms=duration_ms,
                    metadata=metadata if metadata is not None else {},
                    metadata_from_result=metadata_from_result,
                )
            )
            if isinstance(step, dict):
                step["output"] = {"result_type": type(result).__name__}
                step["stats"] = (
                    response.stats
                    if isinstance(response, EngineMethodResponse)
                    else _usage_stats(method, response)
                )
        return response
    except asyncio.CancelledError as exc:
        error = exc
        raise
    except Exception as exc:
        error = exc
        raise
    finally:
        try:
            record_usage_or_fail(
                provider,
                method=method,
                result=response if response is not None else result,
                duration_ms=(
                    response.duration_ms
                    if isinstance(response, EngineMethodResponse)
                    else (time.perf_counter() - started_at) * 1000.0
                ),
                success=error is None,
                error=(
                    "request_cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else str(error)
                    if error is not None
                    else None
                ),
                metadata={
                    **(metadata if metadata is not None else {}),
                    **pipeline_usage_metadata(usage_step_id),
                    **(
                        metadata_from_result(result)
                        if callable(metadata_from_result)
                        else {}
                    ),
                },
            )
        except Exception:
            if error is None:
                raise
            _log_usage_persistence_failure()


async def invoke_stream_with_usage(
    provider: Any,
    method: str,
    payload: dict[str, Any] | None = None,
    *,
    metadata: dict[str, Any] | None = None,
    metadata_from_result: Any = None,
):
    started_at = time.perf_counter()
    items: list[Any] = []
    final: EngineStreamFinal | None = None
    error: BaseException | None = None
    usage_step_id: str | None = None
    try:
        async with ai_pipeline_step(
            type="engine.call",
            name=method,
            input={"method": method},
        ) as step:
            usage_step_id = (
                step.get("step_id") if isinstance(step, dict) else None
            )
            with ai_call_context(**pipeline_usage_metadata(usage_step_id)):
                async for item in provider._invoke_stream(method, payload):
                    items.append(item)
                    mark_step_progress(step, chunks=len(items))
                    yield item
            duration_ms = (time.perf_counter() - started_at) * 1000.0
            provider_final_emitted = any(
                isinstance(item, EngineStreamFinal) for item in items
            )
            final = _stream_final(
                provider=provider,
                method=method,
                payload=payload,
                items=items,
                duration_ms=duration_ms,
                metadata=metadata if metadata is not None else {},
                metadata_from_result=metadata_from_result,
            )
            if not provider_final_emitted:
                yield final
            if isinstance(step, dict):
                step["output"] = {"result_type": "stream", "chunks": len(items)}
                step["stats"] = final.stats
    except asyncio.CancelledError as exc:
        error = exc
        raise
    except Exception as exc:
        error = exc
        raise
    finally:
        try:
            record_usage_or_fail(
                provider,
                method=method,
                result=(
                    items
                    if any(isinstance(item, EngineStreamFinal) for item in items)
                    else [*items, final]
                    if final is not None
                    else items
                ),
                duration_ms=(
                    final.duration_ms
                    if final is not None
                    else (time.perf_counter() - started_at) * 1000.0
                ),
                success=error is None,
                error=(
                    "request_cancelled"
                    if isinstance(error, asyncio.CancelledError)
                    else str(error)
                    if error is not None
                    else None
                ),
                metadata={
                    **(metadata if metadata is not None else {}),
                    **pipeline_usage_metadata(usage_step_id),
                    **(
                        metadata_from_result(items)
                        if callable(metadata_from_result)
                        else {}
                    ),
                },
            )
        except Exception:
            if error is None:
                raise
            _log_usage_persistence_failure()


def record_usage_or_fail(
    provider: Any,
    *,
    method: str,
    result: Any,
    duration_ms: float,
    success: bool,
    error: str | None,
    metadata: dict[str, Any] | None = None,
) -> None:
    context = current_ai_call_context()
    if method.endswith("_stream"):
        prompt_tokens, completion_tokens, total_tokens, tokens_per_second = (
            stream_usage_tuple(result)
        )
    else:
        prompt_tokens, completion_tokens, total_tokens, tokens_per_second = (
            usage_tuple(result)
        )
    usage_metadata = {
        "engine_row_id": provider.engine_row_id,
        "model_registry_id": provider.model_registry_id,
        "engine_id": provider.engine_id,
        "config_signature": runtime_config_signature(provider.config),
        **(
            speech_usage_metadata(result)
            if method in {"synthesize", "synthesize_stream"}
            else {}
        ),
        **_response_metadata(result),
        **(metadata if metadata is not None else {}),
    }
    try:
        from democrai.core.application.observability.service import (
            observability_service,
        )

        event = observability_service.record_ai_model_usage(
            objective=context.get("objective"),
            provider=provider.engine_id or None,
            engine=provider.engine_id or None,
            model_name=provider.config.get("model") or provider.config.get("model_path"),
            deployment_mode="runtime",
            request_kind=context.get("request_kind") or method,
            agent_id=context.get("agent_id"),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
            tokens_per_second=tokens_per_second,
            success=success,
            error=error,
            metadata=usage_metadata,
        )
    except Exception as exc:
        raise RuntimeError(f"ai_model_usage_event_write_failed:{exc}") from exc
    if event is None:
        raise RuntimeError("ai_model_usage_event_not_persisted")


def _usage_stats(method: str, result: Any) -> dict[str, Any]:
    if method.endswith("_stream"):
        prompt_tokens, completion_tokens, total_tokens, tokens_per_second = (
            stream_usage_tuple(result)
        )
    else:
        prompt_tokens, completion_tokens, total_tokens, tokens_per_second = (
            usage_tuple(result)
        )
    return {
        key: value
        for key, value in {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "tokens_per_second": tokens_per_second,
        }.items()
        if value is not None
    }


def _method_response(
    *,
    provider: Any,
    method: str,
    payload: dict[str, Any] | None,
    result: Any,
    duration_ms: float,
    metadata: dict[str, Any],
    metadata_from_result: Any,
) -> EngineMethodResponse:
    if isinstance(result, EngineMethodResponse):
        resolved_payload = payload if payload is not None else {}
        response_metadata = {
            **metadata,
            **result.metadata,
            **_method_metadata(method, resolved_payload, result.result),
        }
        if callable(metadata_from_result):
            response_metadata.update(metadata_from_result(result.result))
        duration = result.duration_ms or duration_ms
        tokens_per_second = result.tokens_per_second or _tokens_per_second(
            result.usage.total_tokens,
            duration,
        )
        return EngineMethodResponse(
            result=result.result,
            usage=result.usage,
            duration_ms=round(duration, 2),
            tokens_per_second=tokens_per_second,
            metadata=response_metadata,
        )
    usage, usage_metadata = _usage_for_result(
        provider=provider,
        method=method,
        payload=payload if payload is not None else {},
        result=result,
        duration_ms=duration_ms,
        metadata=metadata,
        metadata_from_result=metadata_from_result,
    )
    return EngineMethodResponse(
        result=result,
        usage=usage,
        duration_ms=round(duration_ms, 2),
        tokens_per_second=_tokens_per_second(usage.total_tokens, duration_ms),
        metadata=usage_metadata,
    )


def _stream_final(
    *,
    provider: Any,
    method: str,
    payload: dict[str, Any] | None,
    items: list[Any],
    duration_ms: float,
    metadata: dict[str, Any],
    metadata_from_result: Any,
) -> EngineStreamFinal:
    usage, usage_metadata = _usage_for_result(
        provider=provider,
        method=method,
        payload=payload if payload is not None else {},
        result=items,
        duration_ms=duration_ms,
        metadata=metadata,
        metadata_from_result=metadata_from_result,
    )
    return EngineStreamFinal(
        usage=usage,
        duration_ms=round(duration_ms, 2),
        tokens_per_second=_tokens_per_second(usage.total_tokens, duration_ms),
        metadata=usage_metadata,
    )


def _usage_for_result(
    *,
    provider: Any,
    method: str,
    payload: dict[str, Any],
    result: Any,
    duration_ms: float,
    metadata: dict[str, Any],
    metadata_from_result: Any,
) -> tuple[EngineUsage, dict[str, Any]]:
    prompt_tokens, completion_tokens, total_tokens, tokens_per_second = (
        stream_usage_tuple(result) if method.endswith("_stream") else usage_tuple(result)
    )
    resolved_metadata = {
        **metadata,
        **(
            metadata_from_result(result) if callable(metadata_from_result) else {}
        ),
        **_method_metadata(method, payload, result),
    }
    if (
        prompt_tokens in (None, 0)
        and completion_tokens in (None, 0)
        and total_tokens in (None, 0)
    ):
        explicit_usage = _provider_usage_override(
            provider=provider,
            method=method,
            payload=payload,
            result=result,
        )
        if explicit_usage is not None:
            prompt_tokens, completion_tokens, total_tokens = explicit_usage
    prompt = _coerce_int(prompt_tokens)
    completion = _coerce_int(completion_tokens)
    use_calculated_fallback = (
        _should_calculate_usage(provider=provider, method=method)
        and prompt is None
        and completion is None
        and _coerce_int(total_tokens) is None
    )
    if prompt is None and use_calculated_fallback:
        prompt = _input_tokens(method, payload, result)
    if completion is None and use_calculated_fallback:
        completion = _output_tokens(method, payload, result)
    total = _coerce_int(total_tokens)
    if total is None and use_calculated_fallback:
        total = (prompt if prompt is not None else 0) + (
            completion if completion is not None else 0
        )
    if use_calculated_fallback:
        resolved_metadata.setdefault("usage_source", "calculated")
        resolved_metadata.setdefault("usage_calculation", _usage_calculation_name(method))
    if tokens_per_second is not None:
        resolved_metadata.setdefault("provider_tokens_per_second", tokens_per_second)
    return (
        EngineUsage(
            prompt_tokens=prompt if prompt is not None else 0,
            completion_tokens=completion if completion is not None else 0,
            total_tokens=total if total is not None else 0,
        ),
        resolved_metadata,
    )


def _input_tokens(method: str, payload: dict[str, Any], result: Any) -> int:
    if method in {"detect", "get_detections"}:
        return _visual_input_tokens(result)
    if method in {"transcribe"}:
        return 0
    texts: list[str] = []
    if method in {"embed_texts", "classify"}:
        texts.extend(payload.get("texts") or [])
    elif method == "rerank":
        texts.append(payload.get("query") or "")
        texts.extend(payload.get("texts") or [])
    elif method == "extract_tokens":
        texts.append(payload.get("text") or "")
    elif method == "extract_triples":
        texts.extend(
            payload.get(key) or ""
            for key in ("title", "summary", "content")
        )
    elif method in {"synthesize", "synthesize_stream"}:
        texts.append(payload.get("text") or "")
    return sum(_text_tokens(text) for text in texts)


def _output_tokens(method: str, payload: dict[str, Any], result: Any) -> int:
    if method in {"synthesize", "synthesize_stream"}:
        return 0
    if method == "transcribe":
        text = getattr(result, "text", "")
        if isinstance(result, dict):
            text = result.get("text", text)
        return _text_tokens(text or "")
    if method == "embed_texts":
        return 0
    if method == "extract_tokens":
        return 0
    if method in {"classify", "rerank", "extract_triples"}:
        return 0
    if method in {"detect", "get_detections"}:
        if not isinstance(result, dict):
            return 0
        detections = _positive_int(result.get("detections_count"))
        return detections or 0
    if method == "generate_stream":
        _, completion, _, _ = stream_usage_tuple(result)
        return completion if completion is not None else 0
    return 0


def _method_metadata(method: str, payload: dict[str, Any], result: Any) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if isinstance(result, dict) and isinstance(result.get("usage_metadata"), dict):
        data.update(result.get("usage_metadata"))
    if method == "transcribe":
        audio_data = payload.get("audio_data")
        if isinstance(audio_data, bytes | bytearray):
            data["audio_bytes"] = len(audio_data)
            duration = _audio_duration_from_bytes(bytes(audio_data))
            if duration is not None:
                data["audio_duration_seconds"] = duration
        duration = _number(getattr(result, "duration", None))
        if duration is not None:
            data["audio_duration_seconds"] = duration
    if method in {"synthesize", "synthesize_stream"}:
        data.update(speech_usage_metadata(result, text=payload.get("text") or ""))
        duration = _number(getattr(result, "duration", None))
        data_bytes = getattr(result, "data", None)
        if isinstance(result, dict):
            duration = _number(result.get("duration")) or duration
            data_bytes = result.get("data", data_bytes)
        if duration is None and isinstance(data_bytes, bytes | bytearray):
            duration = _audio_duration_from_bytes(bytes(data_bytes))
        if duration is not None:
            data["audio_duration_seconds"] = duration
        if method == "synthesize_stream" and isinstance(result, list):
            audio_bytes = _audio_bytes_from_items(result)
            duration = _audio_duration_from_items(result)
            if audio_bytes:
                data["audio_bytes"] = audio_bytes
            if duration is not None:
                data["audio_duration_seconds"] = duration
    if method in {"detect", "get_detections"} and isinstance(result, dict):
        for key in (
            "media_kind",
            "width",
            "height",
            "sampled_frame_count",
            "model_weight_mb",
            "detections_count",
        ):
            if result.get(key) is not None:
                data[key] = result.get(key)
    if method.endswith("_stream"):
        data.setdefault("stream", True)
    return data


def _visual_input_tokens(result: Any) -> int:
    if not isinstance(result, dict):
        return 0
    width = _positive_int(result.get("width"))
    height = _positive_int(result.get("height"))
    if width is None or height is None:
        return 0
    sampled_frame_count = _positive_int(result.get("sampled_frame_count")) or 1
    return int(width * height * sampled_frame_count)


def _tokens_per_second(total_tokens: int, duration_ms: float) -> float:
    if not total_tokens or duration_ms <= 0:
        return 0.0
    return round(total_tokens / (duration_ms / 1000.0), 2)


def _response_metadata(result: Any) -> dict[str, Any]:
    if isinstance(result, EngineMethodResponse | EngineStreamFinal):
        return result.metadata
    if isinstance(result, list):
        for item in reversed(result):
            if isinstance(item, EngineStreamFinal):
                return item.metadata
    return {}


def _text_tokens(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", normalized, flags=re.UNICODE))


def _coerce_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    return None


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, float) and value.is_integer():
        resolved = int(value)
        return resolved if resolved > 0 else None
    return None


def _audio_bytes_from_items(items: list[Any]) -> int:
    return sum(len(item) for item in items if isinstance(item, bytes | bytearray))


def _audio_duration_from_items(items: list[Any]) -> float | None:
    data = b"".join(bytes(item) for item in items if isinstance(item, bytes | bytearray))
    return _audio_duration_from_bytes(data)


def _audio_duration_from_bytes(data: bytes) -> float | None:
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


def _provider_usage_override(
    *,
    provider: Any,
    method: str,
    payload: dict[str, Any],
    result: Any,
) -> tuple[int, int, int] | None:
    resolver = getattr(provider, "_usage_for_method", None)
    if not callable(resolver):
        return None
    resolved = resolver(method=method, payload=payload, result=result)
    if not isinstance(resolved, tuple) or len(resolved) != 3:
        return None
    return (
        resolved[0] or 0,
        resolved[1] or 0,
        resolved[2] or 0,
    )


def _should_calculate_usage(*, provider: Any, method: str) -> bool:
    if method not in {
        "synthesize",
        "synthesize_stream",
        "transcribe",
        "embed_texts",
        "rerank",
        "classify",
        "extract_tokens",
        "extract_triples",
        "detect",
        "get_detections",
    }:
        return False
    engine_id = provider.engine_id
    return engine_id not in {
        "anthropic",
        "gemini",
        "openai",
        "openai_compatible",
        "openai_tts",
        "openai_whisper",
    }


def _usage_calculation_name(method: str) -> str:
    if method in {"detect", "get_detections"}:
        return "runtime.invocation.visual_pixels_plus_detections"
    if method == "transcribe":
        return "runtime.invocation.text_regex_output_tokens"
    if method in {"synthesize", "synthesize_stream"}:
        return "runtime.invocation.text_regex_input_tokens"
    if method == "extract_triples":
        return "runtime.invocation.provider_or_text_regex_fallback"
    return "runtime.invocation.generic_fallback"


def _wav_data_start(data: bytes) -> int | None:
    offset = 12
    size = len(data)
    while offset + 8 <= size:
        chunk_id = data[offset : offset + 4]
        chunk_size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        chunk_data_start = offset + 8
        if chunk_id == b"data":
            return chunk_data_start
        offset = chunk_data_start + chunk_size + (chunk_size % 2)
    return None


def _log_usage_persistence_failure() -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        app_ctx().logger.error(
            "[AI Pipeline] usage persistence failed "
            "generator=observability:ai_model_usage "
            "error_type=usage_persistence_error "
            "error=ai_model_usage_event_not_persisted_after_engine_error",
            exc_info=True,
        )
    except Exception:
        pass
