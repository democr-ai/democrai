from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from democrai.sdk.normalize import FALSE_STRINGS, TRUE_STRINGS, normalize_key

DEFAULT_TEMPERATURE = 0.7
DEFAULT_TOP_P = 0.9
DEFAULT_GENERATION = {
    "temperature": DEFAULT_TEMPERATURE,
    "top_p": DEFAULT_TOP_P,
    "max_tokens": None,
}


def _number_value(value: Any, default: float) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise ValueError("expected_number") from None


def _optional_int_value(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ValueError("expected_int") from None


def _bool_payload(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    normalized = normalize_key(value)
    if normalized in TRUE_STRINGS:
        return True
    if normalized in FALSE_STRINGS:
        return False
    raise ValueError("thinking_must_be_boolean")


def _runtime_field_names(options_schema: dict[str, Any]) -> list[str]:
    fields = options_schema.get("fields") if isinstance(options_schema, dict) else []
    return [
        str(field.get("name") or "").strip()
        for field in list(fields or [])
        if isinstance(field, dict) and str(field.get("name") or "").strip()
    ]


def _runtime_field_by_name(options_schema: dict[str, Any], name: str) -> dict[str, Any]:
    fields = options_schema.get("fields") if isinstance(options_schema, dict) else []
    for field in list(fields or []):
        if not isinstance(field, dict):
            continue
        if field.get("name") == name:
            return field
    return {}


def _runtime_schema_value(field: dict[str, Any], value: Any) -> tuple[bool, Any]:
    field_type = str(field.get("type") or "").strip()
    if field_type not in {"integer", "number"}:
        return True, value
    if value in (None, ""):
        return False, None
    try:
        if field_type == "integer" or field.get("step") == 1:
            resolved: int | float = int(value)
        else:
            resolved = float(value)
    except (TypeError, ValueError):
        raise ValueError("expected_number") from None
    minimum = field.get("min")
    maximum = field.get("max")
    if isinstance(minimum, int | float) and resolved < minimum:
        raise ValueError("expected_number")
    if isinstance(maximum, int | float) and resolved > maximum:
        raise ValueError("expected_number")
    return True, resolved


def _nested_payload_value(payload: dict[str, Any], path: str) -> Any:
    if path in payload:
        return payload.get(path)
    current: Any = payload
    for part in [item for item in str(path or "").split(".") if item]:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _payload_has_path(payload: dict[str, Any], path: str) -> bool:
    if path in payload:
        return True
    current: Any = payload
    for part in [item for item in str(path or "").split(".") if item]:
        if not isinstance(current, dict) or part not in current:
            return False
        current = current.get(part)
    return True


def _set_nested_value(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [item for item in str(path or "").split(".") if item]
    if not parts:
        return
    current = target
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def _response_text(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, dict):
        return str(response.get("content") or response.get("text") or response)
    return str(
        getattr(response, "content", "") or getattr(response, "text", "") or response
    )


def _required_prompt(payload: dict[str, Any], test_config: dict[str, Any], module_sdk) -> str:
    prompt = str(
        payload.get("prompt")
        or payload.get("value")
        or payload.get("text")
        or test_config.get("prompt")
        or ""
    ).strip()
    if not prompt:
        prompt = module_sdk.i18n.t("system.engine.model.test.default_prompt")
    if not prompt.strip():
        raise ValueError("prompt_required")
    return prompt


def _completion_tokens_per_second(
    completion_tokens: int | None,
    duration_ms: float | None,
) -> float | None:
    if not completion_tokens or not duration_ms or duration_ms <= 0:
        return None
    return round(float(completion_tokens) / (float(duration_ms) / 1000.0), 2)


def _response_usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        return {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _performance_stats(
    *,
    status: str,
    method: str,
    token_input: int | None = None,
    token_output: int | None = None,
    token_total: int | None = None,
    tps: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    resolved_input = _zero_if_none(token_input)
    resolved_output = _zero_if_none(token_output)
    resolved_total = (
        _zero_if_none(token_total)
        if token_total is not None
        else resolved_input + resolved_output
    )
    payload = {
        "status": status,
        "method": method,
        "token_input": resolved_input,
        "token_output": resolved_output,
        "token_total": resolved_total,
        "tps": 0.0 if tps is None else float(tps),
        "prompt_tokens": resolved_input,
        "completion_tokens": resolved_output,
        "total_tokens": resolved_total,
        "tokens_per_second": 0.0 if tps is None else float(tps),
    }
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def _zero_if_none(value: int | None) -> int:
    return 0 if value is None else int(value)


def _estimated_text_tokens(text: str) -> int:
    normalized = str(text or "").strip()
    if not normalized:
        return 0
    return len(re.findall(r"\w+|[^\w\s]", normalized, flags=re.UNICODE))


def _first_upload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    raw = payload.get(key)
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        return dict(raw[0])
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def _upload_storage_path(payload: dict[str, Any], key: str) -> str:
    item = _first_upload(payload, key)
    return str(item.get("storage_path") or item.get("path") or "").strip()


def _upload_mime(payload: dict[str, Any], key: str) -> str:
    item = _first_upload(payload, key)
    return str(
        item.get("mime")
        or item.get("type")
        or item.get("content_type")
        or "application/octet-stream"
    ).strip()


def _upload_size_bytes(payload: dict[str, Any], key: str) -> int:
    item = _first_upload(payload, key)
    return max(0, int(item.get("size_bytes") or item.get("size") or 0))


def _media_bytes_from_upload(module_sdk, payload: dict[str, Any], key: str) -> bytes:
    storage_path = _upload_storage_path(payload, key)
    if not storage_path:
        raise ValueError(f"{key}_required")
    return bytes(module_sdk.media.view(storage_path))


def _upload_public_url(module_sdk, payload: dict[str, Any], key: str) -> str:
    storage_path = _upload_storage_path(payload, key)
    if not storage_path:
        return ""
    return str(module_sdk.media.get_public_url(storage_path) or storage_path)


def _speech_extension(content_type: str) -> str:
    normalized = str(content_type or "").strip().lower()
    if "wav" in normalized:
        return "wav"
    if "ogg" in normalized:
        return "ogg"
    if "mpeg" in normalized or "mp3" in normalized:
        return "mp3"
    return "audio"


def _save_speech_response_media(module_sdk, row_id: int, response: Any) -> str:
    data = getattr(response, "data", None)
    content_type = str(getattr(response, "content_type", None) or "audio/mpeg")
    if isinstance(response, dict):
        data = response.get("data", data)
        content_type = str(response.get("content_type") or content_type)
    if not isinstance(data, bytes | bytearray) or not data:
        return ""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    extension = _speech_extension(content_type)
    storage_path = module_sdk.media.add(
        f"engine_model_tests/{row_id}/synthesize_{timestamp}.{extension}",
        bytes(data),
    )
    return str(module_sdk.media.get_public_url(storage_path) or storage_path)


def _tool_call_test_tools() -> list[dict[str, Any]]:
    return [
        {
            "function": {
                "name": "get_test_temperature",
                "description": "Return a deterministic test temperature for a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name.",
                        }
                    },
                    "required": ["city"],
                },
            }
        }
    ]


def _state_result_update(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stateUpdate": {
            "scope": "page",
            "values": {
                "/engine_model_test/last_result": result,
                "/engine_model_test/last_status": str(result.get("status") or ""),
            },
        }
    }


def _test_result(
    *,
    status: str,
    method: str,
    output: str,
    duration_ms: float | None = None,
    warmup_ms: float | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    tokens_per_second: float | None = None,
    chunks: int | None = None,
    resources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metric_parts = []
    if warmup_ms is not None:
        metric_parts.append(f"warmup_ms={warmup_ms}")
    if duration_ms is not None:
        metric_parts.append(f"duration_ms={duration_ms}")
    if chunks is not None:
        metric_parts.append(f"chunks={chunks}")
    if tokens_per_second is not None:
        metric_parts.append(f"tokens_per_second={tokens_per_second}")
    metric_parts.extend(
        [
            f"prompt_tokens={prompt_tokens}",
            f"completion_tokens={completion_tokens}",
            f"total_tokens={total_tokens}",
        ]
    )
    return {
        "status": status,
        "method": method,
        "duration_ms": duration_ms,
        "warmup_ms": warmup_ms,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "tokens_per_second": tokens_per_second,
        "chunks": chunks,
        "resources": dict(resources or {}),
        "output": output,
        "metrics": " | ".join(metric_parts),
    }


def _stream_chunk_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, bytes | bytearray):
        return chunk.decode("utf-8", errors="ignore")
    if isinstance(chunk, dict):
        return str(
            chunk.get("delta") or chunk.get("content") or chunk.get("text") or ""
        )
    return str(
        getattr(chunk, "delta", None)
        or getattr(chunk, "content", None)
        or getattr(chunk, "text", None)
        or ""
    )
