from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import resource
import struct
import sys
import time
import traceback
from typing import Any
import uuid
import zlib


APP_ROOT = Path(__file__).resolve().parents[2]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from democrai.core.application.ai.engine.pipeline.tool_calls import stream_tool_calls
from democrai.core.runtime.cli.commands import init_module_command_context
from democrai.core.runtime.foundation.app import RequestContext
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import reset_req_ctx
from democrai.core.runtime.foundation.app import set_req_ctx
from tests.runtime import model_registry_app_flow as app_flow


TEST_TOOL_NAME = "system.test-echo"
IMAGE_EXPECTED_TERMS = (("rosso", "red"), ("blu", "blue"))
TEST_TOOL_MARKER = "system_test_tool"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run an end-to-end diagnostic for one model registry row."
    )
    parser.add_argument("--model-registry-id", type=int, required=True)
    parser.add_argument("--prompt", default="Rispondi solo: ok")
    parser.add_argument(
        "--tool-prompt",
        default=(
            "Chiama il tool di test con il parametro text uguale a "
            "'diagnostica tool calling'. Non rispondere con testo normale."
        ),
    )
    parser.add_argument(
        "--image-prompt",
        default=(
            "Osserva l'immagine allegata e leggi le parole scritte. Rispondi solo nel formato: "
            "sinistra=<colore>; destra=<colore>."
        ),
    )
    parser.add_argument(
        "--image-reasoning-prompt",
        default=(
            "Osserva l'immagine allegata. Se il colore a sinistra è rosso vale 10 "
            "e se il colore a destra è blu vale 5. Ragiona e rispondi nel formato: "
            "sinistra=<colore>; destra=<colore>; totale=<numero>."
        ),
    )
    parser.add_argument(
        "--image-final-prompt",
        default=(
            "Osserva l'immagine allegata. Se il colore a sinistra è rosso vale 10 "
            "e se il colore a destra è blu vale 5. Rispondi solo nel formato: "
            "sinistra=<colore>; destra=<colore>; totale=<numero>."
        ),
    )
    parser.add_argument("--image-path", default="")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--top-p", type=float, default=None)
    parser.add_argument("--output", default="")
    parser.add_argument("--confirm-swap", action="store_true")
    return parser.parse_args()


def _request_context() -> RequestContext:
    return RequestContext(
        request_id=f"model-registry-diagnostic-{uuid.uuid4().hex}",
        user=1,
        role=None,
        organization_id=1,
        access_level=10,
        channel="cli",
        session_key="model-registry-diagnostic",
        module_name="system",
        action_name="system.model_registry_diagnostic",
    )


def _model_capabilities(row: dict[str, Any]) -> set[str]:
    raw = row.get("capabilities")
    if isinstance(raw, list):
        return {str(item).strip() for item in raw if str(item).strip()}
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(",") if item.strip()}
    return set()


def _usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if hasattr(usage, "model_dump"):
        usage = usage.model_dump()
    if not isinstance(usage, dict):
        usage = {}
    return {
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "tokens_per_second": getattr(response, "tokens_per_second", None),
    }


def _tool_calls(value: Any) -> list[dict[str, Any]]:
    calls = getattr(value, "tool_calls", None) or []
    result = []
    for call in calls:
        if hasattr(call, "model_dump"):
            result.append(call.model_dump())
        elif isinstance(call, dict):
            result.append(dict(call))
    return result


def _chunk_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, dict):
        return str(chunk.get("delta") or chunk.get("content") or chunk.get("text") or "")
    return str(
        getattr(chunk, "delta", None)
        or getattr(chunk, "content", None)
        or getattr(chunk, "text", None)
        or ""
    )


def _chunk_reasoning(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, dict):
        return str(chunk.get("reasoning") or "")
    return str(getattr(chunk, "reasoning", None) or "")


def _chunk_stats(chunk: Any) -> dict[str, Any] | None:
    stats = chunk.get("stats") if isinstance(chunk, dict) else getattr(chunk, "stats", None)
    return dict(stats) if isinstance(stats, dict) else None


def _pipeline_event(message: Any) -> dict[str, Any]:
    if hasattr(message, "model_dump"):
        payload = message.model_dump()
    elif isinstance(message, dict):
        payload = dict(message)
    else:
        payload = {}
    return {
        "type": payload.get("type"),
        "name": payload.get("name"),
        "status": payload.get("status"),
        "duration_ms": payload.get("duration_ms"),
        "payload": payload.get("payload") or {},
    }


def _diagnostic_events(case: dict[str, Any], suffix: str | None = None) -> list[dict[str, Any]]:
    events = []
    for event in list(case.get("pipeline_events") or []):
        if not isinstance(event, dict):
            continue
        if event.get("type") != "llm.diagnostic_raw":
            continue
        if suffix and event.get("name") != suffix:
            continue
        events.append(event)
    return events


def _iteration_diagnostics(case: dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for event in list(case.get("pipeline_events") or []):
        if not isinstance(event, dict):
            continue
        if event.get("type") != "llm.iteration_diagnostic_raw":
            continue
        payload = event.get("payload") or {}
        if isinstance(payload, dict):
            items.append(dict(payload))
    return items


def _diagnostic_items(case: dict[str, Any]) -> list[dict[str, Any]]:
    raw = case.get("raw_diagnostic")
    if isinstance(raw, list):
        return [dict(item) for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        return [dict(raw)]
    return [
        dict(event.get("payload") or {})
        for event in _diagnostic_events(case)
        if isinstance(event.get("payload"), dict)
    ]


def _raw_text(case: dict[str, Any]) -> str:
    parts = []
    for item in _diagnostic_items(case):
        for section_name in ("raw", "parsed"):
            section = item.get(section_name)
            if not isinstance(section, dict):
                continue
            for key in ("content", "delta", "reasoning"):
                value = section.get(key)
                if isinstance(value, str):
                    parts.append(value)
        for key in ("content", "delta", "reasoning"):
            value = item.get(key)
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


def _has_tool_detected(case: dict[str, Any]) -> bool:
    for event in list(case.get("pipeline_events") or []):
        if isinstance(event, dict) and event.get("type") == "tool.detected":
            return True
    return False


def _raw_contains_tool_call(case: dict[str, Any]) -> bool:
    return _contains_tool_call_text(_raw_text(case))


def _contains_tool_call_text(text: str) -> bool:
    return any(marker in text for marker in ("<tool_call>", "\"name\"", "<function="))


def _raw_contains_nonempty_reasoning(case: dict[str, Any]) -> bool:
    return _raw_contains_nonempty_reasoning_text(_raw_text(case))


def _raw_contains_nonempty_reasoning_text(text: str) -> bool:
    if "<think>" in text and "</think>" in text:
        reasoning = text.partition("<think>")[2].partition("</think>")[0]
        return bool(reasoning.strip())
    return text.lstrip().startswith("Thinking Process:")


def _iteration_raw_text(case: dict[str, Any]) -> str:
    parts = []
    for item in _iteration_diagnostics(case):
        diagnostic = item.get("diagnostic_raw")
        if isinstance(diagnostic, dict):
            for section_name in ("raw", "parsed"):
                section = diagnostic.get(section_name)
                if not isinstance(section, dict):
                    continue
                for key in ("content", "delta", "reasoning"):
                    value = section.get(key)
                    if isinstance(value, str):
                        parts.append(value)
            for key in ("content", "delta", "reasoning"):
                value = diagnostic.get(key)
                if isinstance(value, str):
                    parts.append(value)
    return "".join(parts)


def _resource_snapshot() -> dict[str, Any]:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        "process_max_rss_kb": usage.ru_maxrss,
        "children_max_rss_kb": children.ru_maxrss,
        "user_cpu_seconds": round(float(usage.ru_utime), 4),
        "system_cpu_seconds": round(float(usage.ru_stime), 4),
    }


def _pid_snapshot(pid: Any) -> dict[str, Any]:
    if not pid:
        return {}
    try:
        import psutil

        process = psutil.Process(int(pid))
        memory = process.memory_info()
        return {
            "pid": int(pid),
            "status": process.status(),
            "rss_mb": round(memory.rss / (1024 * 1024), 2),
            "vms_mb": round(memory.vms / (1024 * 1024), 2),
            "cpu_percent": process.cpu_percent(interval=0.0),
        }
    except Exception as exc:
        return {"pid": int(pid), "error": str(exc)}


def _system_resource_snapshot(sdk) -> dict[str, Any]:
    try:
        return dict(sdk.system.metrics.read())
    except Exception as exc:
        return {"error": str(exc)}


async def _loaded_model_snapshots(sdk) -> list[dict[str, Any]]:
    try:
        rows = await sdk.engines.list_loaded_models()
    except Exception as exc:
        return [{"error": str(exc)}]
    result = []
    for row in rows:
        item = dict(row)
        item["process"] = _pid_snapshot(item.get("pid"))
        result.append(item)
    return result


def _ensure_engine_orchestrator() -> None:
    from democrai.core.application.ai.engine.orchestrator.runtime import (
        start_engine_orchestrator_process,
    )

    process = start_engine_orchestrator_process(app_ctx())
    if process is None:
        return
    if process.poll() is not None:
        raise RuntimeError(f"engine_orchestrator_exited:{process.returncode}")


def _extra_config(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("extra_config")
    return dict(value) if isinstance(value, dict) else {}


def _generation_defaults(row: dict[str, Any]) -> dict[str, Any]:
    extra_config = _extra_config(row)
    defaults = extra_config.get("defaults")
    if not isinstance(defaults, dict):
        return {}
    generation = defaults.get("generation")
    return dict(generation) if isinstance(generation, dict) else {}


def _base_options(args: argparse.Namespace, row: dict[str, Any]) -> dict[str, Any]:
    options = _generation_defaults(row)
    if args.temperature is not None:
        options["temperature"] = float(args.temperature)
    if args.top_p is not None:
        options["top_p"] = float(args.top_p)
    if args.max_tokens is not None:
        options["max_tokens"] = int(args.max_tokens)
    extra = dict(options.get("extra") or {})
    extra["diagnostic_raw"] = True
    options["extra"] = extra
    return options


def _text_messages(prompt: str) -> list[dict[str, Any]]:
    return [{"role": "user", "content": [{"type": "text", "text": prompt}]}]


def _image_messages(prompt: str, attachment: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image",
                    "mime_type": attachment["content_type"],
                    "storage_path": attachment["storage_path"],
                },
            ],
        }
    ]


def _reasoning_field(sdk, model_registry_id: int, row: dict[str, Any]) -> dict[str, Any]:
    composer = sdk.ai.get_composer_options_by_model_registry_id(model_registry_id)
    fields = (composer.get("options_schema") or {}).get("fields") or []
    features = _extra_config(row).get("features")
    reasoning = features.get("reasoning") if isinstance(features, dict) else None
    activation = reasoning.get("activation") if isinstance(reasoning, dict) else None
    param = str(activation.get("param") or "").strip() if isinstance(activation, dict) else ""
    if param:
        expected_name = f"extra.{param}"
        for field in fields:
            if isinstance(field, dict) and field.get("name") == expected_name:
                return dict(field)
        return {"name": expected_name, "type": activation.get("type") or "boolean"}
    return {}


def _reasoning_options(base: dict[str, Any], field: dict[str, Any], enabled: bool) -> dict[str, Any]:
    name = str(field.get("name") or "").strip()
    if not name.startswith("extra."):
        raise RuntimeError("reasoning_option_field_missing")
    param = name.removeprefix("extra.")
    value: Any = enabled
    if field.get("type") != "checkbox":
        values = [
            item.get("value")
            for item in list(field.get("options") or [])
            if isinstance(item, dict)
        ]
        if values:
            value = values[-1] if enabled else values[0]
    resolved = dict(base)
    extra = dict(resolved.get("extra") or {})
    extra[param] = value
    resolved["extra"] = extra
    return resolved


def _reasoning_can_disable(field: dict[str, Any]) -> bool:
    if field.get("type") == "checkbox":
        return True
    values = [
        item.get("value")
        for item in list(field.get("options") or [])
        if isinstance(item, dict)
    ]
    disabled_values = {False, "false", "off", "none", "disabled", "no"}
    return any(value in disabled_values for value in values)


def _store_test_image(sdk, image_path: str) -> dict[str, Any]:
    source = Path(image_path).expanduser() if image_path else None
    if source is not None and source.is_file():
        payload = source.read_bytes()
        suffix = source.suffix.lower().lstrip(".") or "png"
        content_type = "image/jpeg" if suffix in {"jpg", "jpeg"} else f"image/{suffix}"
    else:
        payload = _diagnostic_png()
        suffix = "png"
        content_type = "image/png"
    storage_path = sdk.media.add(
        f"engine_model_diagnostics/{uuid.uuid4().hex}.{suffix}",
        payload,
    )
    return {"storage_path": storage_path, "content_type": content_type}


def _diagnostic_png() -> bytes:
    try:
        from PIL import Image, ImageDraw, ImageFont

        width = 512
        height = 256
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, width // 2 - 1, height), fill=(230, 0, 0))
        draw.rectangle((width // 2, 0, width, height), fill=(0, 70, 230))
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 58)
        except Exception:
            font = ImageFont.load_default()
        _draw_centered_text(draw, (0, 0, width // 2, height), "ROSSO", font)
        _draw_centered_text(draw, (width // 2, 0, width, height), "BLU", font)
        import io

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()
    except Exception:
        return _fallback_diagnostic_png()


def _draw_centered_text(draw: Any, box: tuple[int, int, int, int], text: str, font: Any) -> None:
    left, top, right, bottom = box
    text_box = draw.textbbox((0, 0), text, font=font)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    x = left + ((right - left) - text_width) // 2
    y = top + ((bottom - top) - text_height) // 2
    draw.text((x, y), text, fill=(255, 255, 255), font=font)


def _fallback_diagnostic_png() -> bytes:
    width = 128
    height = 64
    rows = []
    for _y in range(height):
        row = bytearray([0])
        for x in range(width):
            row.extend((255, 0, 0) if x < width // 2 else (0, 0, 255))
        rows.append(bytes(row))
    raw = b"".join(rows)
    return _png_bytes(width, height, raw)


def _png_bytes(width: int, height: int, raw_scanlines: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(
            b"IHDR",
            struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0),
        )
        + chunk(b"IDAT", zlib.compress(raw_scanlines))
        + chunk(b"IEND", b"")
    )


def _completion_report(response: Any) -> dict[str, Any]:
    return {
        "response_id": getattr(response, "id", None),
        "pipeline_id": getattr(response, "pipeline_id", None),
        "content": getattr(response, "content", None),
        "reasoning": getattr(response, "reasoning", None),
        "tool_calls": _tool_calls(response),
        "finish_reason": getattr(response, "finish_reason", None),
        "status": getattr(response, "status", None),
        "usage": _usage(response),
        "raw_diagnostic": getattr(response, "diagnostic_raw", None),
    }


async def _run_completion_case(
    provider: Any,
    *,
    case_id: str,
    name: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "case_id": case_id,
        "name": name,
        "method": "generate_completion",
        "request": {"messages": messages, "options": options},
    }
    events: list[dict[str, Any]] = []

    async def _on_message(message: Any) -> None:
        events.append(_pipeline_event(message))

    try:
        response = await provider.generate_completion(
            messages=messages,
            options=options,
            on_message=_on_message,
        )
        result.update(_completion_report(response))
        result["ok"] = True
    except Exception as exc:
        result.update(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    result["pipeline_events"] = events
    if not result.get("raw_diagnostic"):
        result["raw_diagnostic"] = _diagnostic_events(result)
    result["iteration_raw_diagnostic"] = _iteration_diagnostics(result)
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


async def _run_stream_case(
    provider: Any,
    *,
    case_id: str,
    name: str,
    messages: list[dict[str, Any]],
    options: dict[str, Any],
) -> dict[str, Any]:
    started = time.perf_counter()
    result: dict[str, Any] = {
        "case_id": case_id,
        "name": name,
        "method": "generate_stream",
        "request": {"messages": messages, "options": options},
    }
    chunks: list[Any] = []
    raw_diagnostics: list[dict[str, Any]] = []
    stats: dict[str, Any] = {}
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    events: list[dict[str, Any]] = []

    async def _on_message(message: Any) -> None:
        events.append(_pipeline_event(message))

    try:
        async for chunk in provider.generate_stream(
            messages=messages,
            options=options,
            on_message=_on_message,
        ):
            chunk_stats = _chunk_stats(chunk)
            if chunk_stats is not None:
                stats.update(chunk_stats)
                continue
            chunks.append(chunk)
            diagnostic_raw = getattr(chunk, "diagnostic_raw", None)
            if isinstance(diagnostic_raw, dict):
                raw_diagnostics.append(diagnostic_raw)
            text = _chunk_text(chunk)
            reasoning = _chunk_reasoning(chunk)
            if text:
                text_parts.append(text)
            if reasoning:
                reasoning_parts.append(reasoning)
        result.update(
            {
                "ok": True,
                "content": "".join(text_parts),
                "reasoning": "".join(reasoning_parts) or None,
                "tool_calls": [
                    call.model_dump() if hasattr(call, "model_dump") else dict(call)
                    for call in stream_tool_calls(chunks)
                ],
                "chunks": len(chunks),
                "usage": stats,
                "raw_diagnostic": raw_diagnostics,
            }
        )
    except Exception as exc:
        result.update(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
    result["pipeline_events"] = events
    if not result.get("raw_diagnostic"):
        result["raw_diagnostic"] = _diagnostic_events(result)
    result["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
    return result


def _case_errors(case: dict[str, Any]) -> list[str]:
    errors = []
    if not case.get("ok"):
        errors.append(str(case.get("error") or "case_failed"))
    name = str(case.get("name") or "")
    if "tool" in name:
        if not _has_tool_detected(case):
            if _raw_contains_tool_call(case):
                errors.append("tool_call_raw_parser_missed")
            else:
                errors.append("tool_call_raw_not_emitted")
        if not _tool_executed(case):
            errors.append("tool_call_not_executed")
        if not _tool_response_has_marker(case):
            errors.append("tool_response_marker_missing")
    content = str(case.get("content") or "")
    if "<think>" in content or "</think>" in content:
        errors.append("reasoning_marker_leaked_to_content")
    if "image" in name and not _image_seen(case):
        errors.append("image_semantic_mismatch")
    if "image_reasoning" in name and not _image_reasoning_result_ok(case):
        errors.append("image_reasoning_total_mismatch")
    if "reasoning_true" in name and not case.get("reasoning"):
        errors.append("reasoning_not_detected")
    if "reasoning_false" in name and case.get("reasoning"):
        errors.append("reasoning_detected_when_disabled")
    return errors


def _case_id(name: str, method: str) -> str:
    return f"{method}:{name}:{uuid.uuid4().hex[:12]}"


def _image_seen(case: dict[str, Any]) -> bool:
    text = " ".join([str(case.get("content") or ""), _raw_text(case)]).lower()
    return all(any(term in text for term in alternatives) for alternatives in IMAGE_EXPECTED_TERMS)


def _image_reasoning_result_ok(case: dict[str, Any]) -> bool:
    text = " ".join([str(case.get("content") or ""), _raw_text(case)]).lower()
    compact = text.replace(" ", "")
    return "totale=15" in compact or "total=15" in compact


def _case_tool_calls(case: dict[str, Any]) -> list[dict[str, Any]]:
    calls = case.get("tool_calls")
    return [dict(call) for call in calls if isinstance(call, dict)] if isinstance(calls, list) else []


def _tool_events(case: dict[str, Any], event_type: str) -> list[dict[str, Any]]:
    return [
        event
        for event in list(case.get("pipeline_events") or [])
        if isinstance(event, dict) and event.get("type") == event_type
    ]


def _tool_executed(case: dict[str, Any]) -> bool:
    for event in _tool_events(case, "tool.call.finished"):
        payload = event.get("payload") or {}
        if isinstance(payload, dict) and payload.get("error") is None:
            return True
    return False


def _tool_response_has_marker(case: dict[str, Any]) -> bool:
    for event in _tool_events(case, "tool.response"):
        payload = event.get("payload") or {}
        result = payload.get("result") if isinstance(payload, dict) else None
        if isinstance(result, dict) and result.get("marker") == TEST_TOOL_MARKER:
            return True
    return False


def _forced_tool_choice() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {"name": TEST_TOOL_NAME},
    }


def _with_extra(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(base)
    merged = dict(resolved.get("extra") or {})
    merged.update(extra)
    resolved["extra"] = merged
    return resolved


def _build_assessment(report: dict[str, Any]) -> dict[str, Any]:
    capabilities = set(report.get("model", {}).get("capabilities") or [])
    cases = list(report.get("cases") or [])
    errors = list(report.get("errors") or [])
    assessment: dict[str, Any] = {
        "capabilities": {},
        "parser": {},
        "suggested_plan": [],
    }
    for capability in sorted(capabilities):
        related = [error for error in errors if _error_matches_capability(error, capability)]
        assessment["capabilities"][capability] = {
            "declared": True,
            "status": "ok" if not related else "failed",
            "errors": related,
        }
    parser_errors = []
    for case in cases:
        raw = _raw_text(case)
        iteration_raw = _iteration_raw_text(case)
        combined_raw = raw + iteration_raw
        if combined_raw and (
            (_raw_contains_nonempty_reasoning_text(combined_raw) and not case.get("reasoning"))
            or (_contains_tool_call_text(combined_raw) and not _case_tool_calls(case) and not _has_tool_detected(case))
        ):
            parser_errors.append(
                {
                    "method": case.get("method"),
                    "name": case.get("name"),
                    "raw_sample": combined_raw[:500],
                }
            )
    assessment["parser"] = {
        "status": "ok" if not parser_errors else "failed",
        "errors": parser_errors,
    }
    if any("tool_call_raw_not_emitted" in error for error in errors):
        assessment["suggested_plan"].append(
            "Verificare chat template/tool_choice per il modello: il raw LLM non contiene tool call."
        )
    if any("tool_call_raw_parser_missed" in error for error in errors):
        assessment["suggested_plan"].append(
            "Correggere output_parser/tool parser: il raw contiene tool call ma il post-parser non le espone."
        )
    if any("image_semantic_mismatch" in error or "image_reasoning_total_mismatch" in error for error in errors):
        assessment["suggested_plan"].append(
            "Verificare handler multimodale/mmproj/template: l'immagine arriva ma il contenuto visivo atteso non viene riconosciuto."
        )
    if any("reasoning_not_detected" in error for error in errors):
        assessment["suggested_plan"].append(
            "Verificare attivazione reasoning: il parametro è esposto ma non produce reasoning parsato."
        )
    if any("reasoning_marker_leaked_to_content" in error for error in errors):
        assessment["suggested_plan"].append(
            "Correggere parser reasoning: marker di reasoning presenti nel contenuto utente."
        )
    return assessment


def _error_matches_capability(error: str, capability: str) -> bool:
    if capability == "tool_calling":
        return "tool" in error
    if capability == "image_to_text":
        return "image" in error
    if capability == "reasoning":
        return "reasoning" in error
    return False


async def _run() -> int:
    args = _parse_args()
    app_flow.configure_runtime_paths()
    init_module_command_context(app_flow.server_args())
    app_flow.load_system_actions()
    import modules.system.tools.test  # noqa: F401

    await app_flow.ensure_app_runtime()
    _ensure_engine_orchestrator()

    session = app_flow.system_session()
    sdk = app_flow.system_sdk(session)
    row = sdk.models.model_registry.view(int(args.model_registry_id))
    if not isinstance(row, dict):
        raise RuntimeError(f"model_registry_row_not_found:{args.model_registry_id}")

    token = set_req_ctx(_request_context())
    try:
        report: dict[str, Any] = {
            "model_registry_id": int(args.model_registry_id),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "resources_start": _resource_snapshot(),
            "system_resources_start": _system_resource_snapshot(sdk),
            "model": {
                "id": row.get("id"),
                "name": row.get("name"),
                "status": row.get("status"),
                "provider": row.get("provider"),
                "engine_id": row.get("engine_id"),
                "runtime_methods": row.get("runtime_methods"),
                "capabilities": sorted(_model_capabilities(row)),
                "defaults_generation": _generation_defaults(row),
                "defaults_runtime": (
                    _extra_config(row).get("defaults", {}).get("runtime", {})
                    if isinstance(_extra_config(row).get("defaults"), dict)
                    else {}
                ),
            },
            "cases": [],
            "errors": [],
        }
        provider_result = await sdk.ai.get_provider_by_model_registry_id(
            int(args.model_registry_id),
            confirm_swap=bool(args.confirm_swap),
        )
        report["provider"] = {
            key: value
            for key, value in provider_result.items()
            if key != "provider"
        }
        if provider_result.get("status") != "ok" or not provider_result.get("provider"):
            report["errors"].append(str(provider_result.get("error") or "provider_unavailable"))
        else:
            provider = provider_result["provider"]
            warmup_started = time.perf_counter()
            try:
                warmup_result = await sdk.ai.warmup_provider(provider, wait=True)
                report["warmup"] = {
                    "duration_ms": round((time.perf_counter() - warmup_started) * 1000, 2),
                    "result": warmup_result,
                }
            except Exception as exc:
                report["warmup"] = {
                    "duration_ms": round((time.perf_counter() - warmup_started) * 1000, 2),
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
                report["errors"].append(f"warmup_failed:{exc}")
                warmup_result = None
            report["loaded_models_after_warmup"] = await _loaded_model_snapshots(sdk)
            report["system_resources_after_warmup"] = _system_resource_snapshot(sdk)
            capabilities: set[str] = set()
            cases: list[tuple[str, list[dict[str, Any]], dict[str, Any]]] = []
            base_options: dict[str, Any] = {}
            attachment = None
            if warmup_result is not None:
                base_options = _base_options(args, row)
                base_messages = _text_messages(str(args.prompt or ""))
                capabilities = _model_capabilities(row)
                cases = [
                    ("baseline", base_messages, base_options),
                ]
            if "tool_calling" in capabilities:
                cases.append(
                    (
                        "tool_calling_auto",
                        _text_messages(str(args.tool_prompt or "")),
                        {**base_options, "tools": [TEST_TOOL_NAME]},
                    )
                )
                cases.append(
                    (
                        "tool_calling_forced",
                        _text_messages(str(args.tool_prompt or "")),
                        {
                            **base_options,
                            "tools": [TEST_TOOL_NAME],
                            "tool_choice": _forced_tool_choice(),
                        },
                    )
                )
            if "image_to_text" in capabilities:
                attachment = _store_test_image(sdk, str(args.image_path or ""))
                report["image_attachment"] = attachment
                cases.append(
                    (
                        "image_to_text",
                        _image_messages(str(args.image_prompt or ""), attachment),
                        base_options,
                    )
                )
            if "reasoning" in capabilities:
                field = _reasoning_field(sdk, int(args.model_registry_id), row)
                report["reasoning_field"] = field
                if field:
                    reasoning_prompt = _text_messages(
                        "Risolvi: se ho 12 mele e ne regalo 5, quante mele restano? "
                        "Rispondi con il risultato finale."
                    )
                    if _reasoning_can_disable(field):
                        cases.append(
                            (
                                "reasoning_false",
                                reasoning_prompt,
                                _reasoning_options(base_options, field, False),
                            )
                        )
                    else:
                        report["reasoning_false"] = {
                            "status": "not_applicable",
                            "field": field,
                        }
                    cases.append(
                        (
                            "reasoning_true",
                            reasoning_prompt,
                            _reasoning_options(base_options, field, True),
                        )
                    )
                    if "image_to_text" in capabilities and attachment is not None:
                        image_final_messages = _image_messages(
                            str(args.image_final_prompt or ""),
                            attachment,
                        )
                        image_reasoning_messages = _image_messages(
                            str(args.image_reasoning_prompt or ""),
                            attachment,
                        )
                        if _reasoning_can_disable(field):
                            cases.append(
                                (
                                    "image_reasoning_false",
                                    image_final_messages,
                                    _reasoning_options(base_options, field, False),
                                )
                            )
                        cases.append(
                            (
                                "image_reasoning_true",
                                image_reasoning_messages,
                                _reasoning_options(base_options, field, True),
                            )
                        )
                else:
                    report["errors"].append("reasoning_option_field_missing")
            runtime_methods = {
                str(item).strip()
                for item in list(row.get("runtime_methods") or [])
                if str(item).strip()
            }
            if "generate_completion" not in runtime_methods:
                report["errors"].append("runtime_method_missing:generate_completion")
            if "generate_stream" not in runtime_methods:
                report["errors"].append("runtime_method_missing:generate_stream")
            for name, messages, options in cases:
                case_results = []
                if "generate_completion" in runtime_methods:
                    completion_case_id = _case_id(name, "generate_completion")
                    before_completion = await _loaded_model_snapshots(sdk)
                    completion = await _run_completion_case(
                        provider,
                        case_id=completion_case_id,
                        name=name,
                        messages=messages,
                        options=options,
                    )
                    completion["loaded_models_before"] = before_completion
                    completion["loaded_models_after"] = await _loaded_model_snapshots(sdk)
                    case_results.append(completion)
                if "generate_stream" in runtime_methods:
                    stream_case_id = _case_id(name, "generate_stream")
                    before_stream = await _loaded_model_snapshots(sdk)
                    stream = await _run_stream_case(
                        provider,
                        case_id=stream_case_id,
                        name=name,
                        messages=messages,
                        options=options,
                    )
                    stream["loaded_models_before"] = before_stream
                    stream["loaded_models_after"] = await _loaded_model_snapshots(sdk)
                    case_results.append(stream)
                report["cases"].extend(case_results)
                for case in case_results:
                    validation_errors = _case_errors(case)
                    case["runtime_ok"] = bool(case.get("ok"))
                    if validation_errors:
                        case["ok"] = False
                        case["validation_errors"] = validation_errors
                    for error in validation_errors:
                        report["errors"].append(
                            f"{case.get('method')}:{case.get('name')}:{error}"
                        )
        report["assessment"] = _build_assessment(report)
        parser_assessment = report["assessment"].get("parser")
        if isinstance(parser_assessment, dict) and parser_assessment.get("status") == "failed":
            report["errors"].append("parser_assessment_failed")
        report["resources_end"] = _resource_snapshot()
        report["system_resources_end"] = _system_resource_snapshot(sdk)
        report["loaded_models_end"] = await _loaded_model_snapshots(sdk)
        output = Path(args.output).expanduser() if args.output else (
            APP_ROOT
            / ".audit_temp"
            / f"model_registry_diagnostic_{args.model_registry_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"REPORT {output}")
        if report["errors"]:
            print(json.dumps({"errors": report["errors"]}, ensure_ascii=False, indent=2))
            return 1
        print("OK")
        return 0
    finally:
        reset_req_ctx(token)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
