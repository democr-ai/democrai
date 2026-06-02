from __future__ import annotations

from datetime import datetime, timedelta
import json
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk


def _t(key: str, context: dict[str, Any] | None = None) -> str:
    return sdk.i18n.t(f"monitor.{key}", context=context or {})


def _route_pipeline_id(params: dict[str, Any]) -> str:
    route_params = params.get("route_params")
    if isinstance(route_params, dict):
        pipeline_id = str(route_params.get("id") or "").strip()
        if pipeline_id:
            return pipeline_id
    return str(params.get("id") or params.get("pipeline_id") or "").strip()


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _metric_value(stats: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = stats.get(key)
        if value not in (None, ""):
            return value
    return None


def _step_detail(row: dict[str, Any]) -> dict[str, Any]:
    step = dict(row)
    row_id = str(row.get("id") or "").strip()
    if row_id:
        detail = sdk.models.ai_model_pipeline_steps.view(row_id)
        if isinstance(detail, dict):
            step.update(detail)

    stats = _json_dict(step.get("stats_json"))
    step["prompt_tokens"] = _metric_value(stats, "prompt_tokens", "token_input")
    step["completion_tokens"] = _metric_value(stats, "completion_tokens", "token_output")
    step["total_tokens"] = _metric_value(stats, "total_tokens", "token_total")
    step["tokens_per_second"] = _metric_value(stats, "tokens_per_second", "tps")
    step["archive_available"] = (
        str(step.get("archive_status") or "").strip() == "archived"
        and bool(str(step.get("archive_media_path") or "").strip())
    )
    step["archive_open_disabled"] = not bool(step["archive_available"])
    for key, value in list(step.items()):
        if value is None:
            step[key] = ""
    return step


def _pipeline_steps(pipeline_id: str) -> list[dict[str, Any]]:
    result = sdk.models.ai_model_pipeline_steps.all(
        filters={"pipeline_id": pipeline_id},
        sort={"field": "timestamp", "direction": "asc"},
    )
    rows = list((result or {}).get("rows") or [])
    steps = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        step = _step_detail(row)
        step["accordion_title"] = _accordion_title(step, index)
        step["accordion_meta"] = _accordion_meta(step)
        step["open"] = False
        steps.append(step)
    return steps


def _summary(pipeline_id: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    duration = sum(float(step.get("duration_ms") or 0.0) for step in steps)
    total_tokens = sum(int(step.get("total_tokens") or 0) for step in steps)
    statuses = {str(step.get("status") or "").strip() for step in steps}
    if not steps:
        status = "empty"
    elif "error" in statuses or "failed" in statuses:
        status = "failed"
    elif statuses == {"completed"}:
        status = "completed"
    elif "running" in statuses:
        status = "running"
    else:
        status = ", ".join(sorted(value for value in statuses if value)) or "-"
    request_id = str(steps[0].get("request_id") or "") if steps else ""
    return {
        "pipeline_id": pipeline_id,
        "request_id": request_id,
        "steps": len(steps),
        "status": status,
        "duration_ms": round(duration, 2),
        "total_tokens": total_tokens,
    }


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is not None:
                return parsed.astimezone().replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    return None


def _gantt_status(status: str) -> str:
    value = status.strip().lower()
    if value in {"completed", "ok", "done"}:
        return "done"
    if value in {"running", "active"}:
        return "active"
    if value in {"error", "failed"}:
        return "risk"
    return value or "planned"


def _pipeline_status_label(status: str) -> str:
    value = status.strip().lower()
    if value in {"completed", "done", "ok"}:
        return "ok"
    if value in {"running", "active"}:
        return "running"
    if value in {"error", "failed"}:
        return "failed"
    return value or "idle"


def _pipeline_gantt_scale(start: datetime, end: datetime) -> str:
    duration_ms = max(1.0, (end - start).total_seconds() * 1000.0)
    if duration_ms <= 5_000:
        return "100ms"
    if duration_ms <= 30_000:
        return "500ms"
    if duration_ms <= 5 * 60_000:
        return "1s"
    if duration_ms <= 60 * 60_000:
        return "10s"
    return "1m"


def _step_type_color(step_type: str) -> str:
    value = step_type.strip().upper()
    if value == "GAP":
        return "#64748b"
    if value == "REQUEST":
        return "#f59e0b"
    if value.startswith("SECURITY."):
        return "#8b5cf6"
    if value.startswith("ENGINE."):
        return "#06b6d4"
    if value.startswith("TOOL."):
        return "#22c55e"
    return "#64748b"


def _gantt_payload(steps: list[dict[str, Any]]) -> dict[str, Any]:
    step_items: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        step_id = str(step.get("step_id") or step.get("id") or f"step_{index}").strip()
        start = _parse_timestamp(step.get("timestamp"))
        if start is None:
            continue
        duration_ms = max(1.0, float(step.get("duration_ms") or 1.0))
        end = start + timedelta(milliseconds=duration_ms)
        name = str(step.get("name") or step_id).strip()
        status = str(step.get("status") or "").strip()
        duration = _format_duration(step.get("duration_ms"))
        tokens = step.get("total_tokens")
        label_parts = [name]
        if status:
            label_parts.append(status)
        if duration:
            label_parts.append(duration)
        if tokens not in (None, "", 0):
            label_parts.append(f"{tokens} tok")
        step_type = str(step.get("type") or step.get("root_method") or "pipeline")
        gantt_status = _gantt_status(status)
        item = {
            "id": step_id,
            "label": " - ".join(label_parts),
            "group": step_type,
            "start": start.isoformat(timespec="milliseconds"),
            "end": end.isoformat(timespec="milliseconds"),
            "status": gantt_status,
            "status_label": _pipeline_status_label(status),
            "progress": 100 if gantt_status == "done" else (55 if gantt_status == "active" else 0),
            "color": _step_type_color(step_type),
        }
        step_items.append(item)

    step_items.sort(key=lambda item: (_parse_timestamp(item["start"]) or datetime.min, _parse_timestamp(item["end"]) or datetime.min))
    flat_items: list[dict[str, Any]] = []
    previous_end: datetime | None = None
    previous_id = ""
    step_number = 1
    for item in step_items:
        current_start = _parse_timestamp(item["start"])
        current_end = _parse_timestamp(item["end"])
        if current_start is None or current_end is None:
            continue
        if previous_end is not None and current_start > previous_end:
            gap_ms = (current_start - previous_end).total_seconds() * 1000.0
            if gap_ms >= 2.0:
                flat_items.append(
                    {
                        "id": f"gap_{previous_id}_{item['id']}",
                        "label": f"gap - {_format_duration(gap_ms)}",
                        "group": "GAP",
                        "start": previous_end.isoformat(timespec="milliseconds"),
                        "end": current_start.isoformat(timespec="milliseconds"),
                        "status": "planned",
                        "status_label": "idle",
                        "progress": 100,
                        "color": _step_type_color("GAP"),
                    }
                )
        display_item = dict(item)
        display_item["label"] = f"{step_number:02d} - {item['label']}"
        flat_items.append(display_item)
        previous_end = max(previous_end, current_end) if previous_end is not None else current_end
        previous_id = str(item["id"])
        step_number += 1

    starts = [_parse_timestamp(item["start"]) for item in flat_items]
    ends = [_parse_timestamp(item["end"]) for item in flat_items]
    starts = [value for value in starts if value is not None]
    ends = [value for value in ends if value is not None]
    if not starts or not ends:
        return {"items": [], "start": "", "end": "", "scale": "1d"}
    start = min(starts)
    end = max(ends)
    return {
        "items": flat_items,
        "start": start.isoformat(timespec="milliseconds"),
        "end": end.isoformat(timespec="milliseconds"),
        "scale": _pipeline_gantt_scale(start, end),
    }


def _format_duration(value: Any) -> str:
    if value in (None, ""):
        return ""
    duration = float(value)
    if duration >= 1000:
        return f"{duration / 1000:.2f} s"
    return f"{duration:.0f} ms"


def _accordion_title(step: dict[str, Any], index: int) -> str:
    name = str(step.get("name") or step.get("step_id") or f"Step {index + 1}").strip()
    status = str(step.get("status") or "").strip()
    return f"{index + 1}. {name}" + (f" - {status}" if status else "")


def _accordion_meta(step: dict[str, Any]) -> str:
    duration = step.get("duration_ms")
    tokens = step.get("total_tokens")
    meta_parts = []
    if duration not in (None, ""):
        meta_parts.append(f"{duration} ms")
    if tokens not in (None, "", 0):
        meta_parts.append(f"{tokens} tokens")
    archive_status = str(step.get("archive_status") or "").strip()
    if archive_status and archive_status != "none":
        meta_parts.append(f"trace {archive_status}")
    return " - ".join(meta_parts)


@permission_required(["monitor.view"])
async def render(params: dict, session: dict):
    pipeline_id = _route_pipeline_id(params)
    builder = sdk.ui.load("utils/ui/yaml/pipeline_detail")
    steps = _pipeline_steps(pipeline_id) if pipeline_id else []
    gantt = _gantt_payload(steps)

    builder.set_data(
        "/pipeline/title",
        _t("pipeline.detail.title", {"pipeline_id": pipeline_id})
        if pipeline_id
        else _t("pipeline.detail.title_empty"),
    )
    builder.set_data("/pipeline/subtitle", _t("pipeline.detail.subtitle"))
    builder.set_data("/pipeline/summary", _summary(pipeline_id, steps))
    builder.set_data("/pipeline/steps", steps)
    builder.set_data("/pipeline/gantt_title", _t("pipeline.detail.timeline"))
    builder.set_data("/pipeline/gantt/items", gantt["items"])
    builder.set_data("/pipeline/gantt/start", gantt["start"])
    builder.set_data("/pipeline/gantt/end", gantt["end"])
    builder.set_data("/pipeline/gantt/scale", gantt["scale"])

    return builder
