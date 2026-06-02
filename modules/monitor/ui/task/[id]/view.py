from __future__ import annotations

import json
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk


def _t(key: str, context: dict[str, Any] | None = None) -> str:
    return sdk.i18n.t(f"monitor.{key}", context=context or {})


def _route_task_id(params: dict[str, Any]) -> str:
    route_params = params.get("route_params")
    if isinstance(route_params, dict):
        task_id = str(route_params.get("id") or "").strip()
        if task_id:
            return task_id
    return str(params.get("id") or params.get("task_id") or "").strip()


def _task_detail(task_id: str) -> dict[str, Any]:
    try:
        row = sdk.models.background_tasks.view(task_id)
    except Exception:
        return {}
    return dict(row or {}) if isinstance(row, dict) else {}


def _json_block(value: Any) -> str:
    if value in (None, "", {}, []):
        return "```text\n-\n```"
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    return f"```text\n{text}\n```"


@permission_required(["monitor.view"])
async def render(params: dict, session: dict):
    task_id = _route_task_id(params)
    builder = sdk.ui.load("utils/ui/yaml/task_detail")
    row = _task_detail(task_id) if task_id else {}
    error = str(row.get("error") or "").strip()

    builder.set_data(
        "/task/title",
        _t("task.detail.title", {"task_id": task_id})
        if task_id
        else _t("task.detail.title_empty"),
    )
    builder.set_data("/task/overview", row)
    builder.set_data("/task/error_description", error or "-")
    builder.set_data("/task/error_variant", "danger" if error else "info")
    builder.set_data("/task/checkpoint_text", _json_block(row.get("checkpoint")))
    builder.set_data("/task/result_text", _json_block(row.get("result")))

    return builder
