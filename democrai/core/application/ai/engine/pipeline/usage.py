from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.schemas.audio import SpeechResponse
from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.application.ai.engine.schemas.completion import StreamChunk
from democrai.core.application.ai.engine.schemas.runtime import EngineMethodResponse
from democrai.core.application.ai.engine.schemas.runtime import EngineStreamFinal


def usage_tuple(response: Any) -> tuple[int | None, int | None, int | None, float | None]:
    if isinstance(response, EngineMethodResponse):
        return (
            response.usage.prompt_tokens,
            response.usage.completion_tokens,
            response.usage.total_tokens,
            response.tokens_per_second,
        )
    if isinstance(response, dict) and response.get("usage") is not None:
        usage = _usage_object(response)
        return (
            _usage_value(usage, "prompt_tokens"),
            _usage_value(usage, "completion_tokens"),
            _usage_value(usage, "total_tokens"),
            _usage_float(response, "tokens_per_second"),
        )
    if isinstance(response, SpeechResponse):
        return _response_usage_tuple(response)
    if not isinstance(response, CompletionResponse):
        return None, None, None, None
    return _response_usage_tuple(response)


def speech_usage_metadata(result: Any, *, text: str | None = None) -> dict[str, Any]:
    usage = _usage_object(result)
    return {
        key: value
        for key, value in {
            "input_characters": _usage_value(usage, "input_characters")
            if usage is not None
            else _text_characters(text),
            "audio_bytes": _usage_value(usage, "audio_bytes")
            if usage is not None
            else _audio_bytes(result),
        }.items()
        if value is not None
    }


def _response_usage_tuple(response: Any) -> tuple[int | None, int | None, int | None, float | None]:
    usage = response.usage
    tokens_per_second = _usage_float(response, "tokens_per_second")
    if usage is None:
        return None, None, None, tokens_per_second
    return (
        _usage_value(usage, "prompt_tokens"),
        _usage_value(usage, "completion_tokens"),
        _usage_value(usage, "total_tokens"),
        tokens_per_second,
    )


def stream_usage_tuple(items: Any) -> tuple[int | None, int | None, int | None, float | None]:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    tokens_per_second: float | None = None
    for item in list(items or []) if isinstance(items, list) else []:
        if isinstance(item, EngineStreamFinal):
            return (
                item.usage.prompt_tokens,
                item.usage.completion_tokens,
                item.usage.total_tokens,
                item.tokens_per_second,
            )
        if not isinstance(item, StreamChunk):
            continue
        prompt, completion, total, tps = _chunk_usage_tuple(item)
        if prompt is not None:
            prompt_tokens = prompt
        if completion is not None:
            completion_tokens = completion
        if total is not None:
            total_tokens = total
        if tps is not None:
            tokens_per_second = tps
    return prompt_tokens, completion_tokens, total_tokens, tokens_per_second


def _usage_value(value: Any, key: str) -> int | None:
    raw = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
    return int(raw) if isinstance(raw, int) else None


def _usage_float(value: Any, key: str) -> float | None:
    raw = value.get(key) if isinstance(value, dict) else getattr(value, key, None)
    return float(raw) if isinstance(raw, (int, float)) else None


def _usage_object(value: Any) -> Any:
    usage = getattr(value, "usage", None)
    if usage is None and isinstance(value, dict):
        usage = value.get("usage")
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    return usage if usage is not None else None


def _text_characters(text: str | None) -> int | None:
    if text is None:
        return None
    return len(str(text))


def _audio_bytes(value: Any) -> int | None:
    data = getattr(value, "data", None)
    if isinstance(value, dict):
        data = value.get("data", data)
    if isinstance(value, list):
        total = 0
        found = False
        for item in value:
            item_bytes = _audio_bytes(item)
            if item_bytes is None:
                continue
            total += item_bytes
            found = True
        return total if found else None
    if isinstance(data, bytes | bytearray):
        return len(data)
    return None


def _chunk_usage_tuple(chunk: StreamChunk) -> tuple[int | None, int | None, int | None, float | None]:
    return (
        _usage_value(chunk, "prompt_tokens"),
        _usage_value(chunk, "completion_tokens"),
        _usage_value(chunk, "total_tokens"),
        _usage_float(chunk, "tokens_per_second"),
    )
