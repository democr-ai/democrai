from __future__ import annotations

import gzip
from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk


_MAX_PAYLOAD_CHARS = 200_000


def _t(key: str, context: dict[str, Any] | None = None) -> str:
    return sdk.i18n.t(f"monitor.{key}", context=context or {})


def _route_step_row_id(params: dict[str, Any]) -> str:
    route_params = params.get("route_params")
    if isinstance(route_params, dict):
        row_id = str(route_params.get("id") or "").strip()
        if row_id:
            return row_id
    return str(params.get("id") or params.get("row_id") or "").strip()


def _payload_markdown(payload_text: str, *, truncated: bool) -> str:
    text = payload_text[:_MAX_PAYLOAD_CHARS] if truncated else payload_text
    suffix = "\n\n_Trace payload truncated for UI preview._" if truncated else ""
    return f"```json\n{text}\n```{suffix}"


def _load_trace_payload(row: dict[str, Any]) -> tuple[str, bool, str | None]:
    media_path = str(row.get("archive_media_path") or "").strip()
    if not media_path:
        return "{}", False, "trace_archive_missing_media_path"
    try:
        raw = sdk.media.view(media_path)
        decoded = gzip.decompress(raw).decode("utf-8")
        return decoded, len(decoded) > _MAX_PAYLOAD_CHARS, None
    except Exception as exc:
        return "{}", False, str(exc)


@permission_required(["monitor.view"])
async def render(params: dict, session: dict):
    row_id = _route_step_row_id(params)
    builder = sdk.ui.load("utils/ui/yaml/pipeline_trace")
    row = sdk.models.ai_model_pipeline_steps.view(row_id) if row_id else {}
    if not isinstance(row, dict):
        row = {}

    payload_text, truncated, error = _load_trace_payload(row)
    if error:
        notice_title = _t("trace.error.title")
        notice = error
        notice_variant = "danger"
        payload_markdown = "```json\n{}\n```"
    else:
        notice_title = _t("trace.loaded.title")
        notice = _t("trace.loaded.description")
        notice_variant = "info"
        payload_markdown = _payload_markdown(payload_text, truncated=truncated)

    builder.set_data(
        "/trace/title",
        _t("trace.title", {"step_id": str(row.get("step_id") or row_id)}),
    )
    builder.set_data("/trace/notice_title", notice_title)
    builder.set_data("/trace/notice", notice)
    builder.set_data("/trace/notice_variant", notice_variant)
    builder.set_data(
        "/trace/overview",
        {
            "step_id": str(row.get("step_id") or ""),
            "type": str(row.get("type") or ""),
            "name": str(row.get("name") or ""),
            "status": str(row.get("status") or ""),
            "archive_media_path": str(row.get("archive_media_path") or ""),
            "input_size_bytes": int(row.get("input_size_bytes") or 0),
            "output_size_bytes": int(row.get("output_size_bytes") or 0),
            "input_hash": str(row.get("input_hash") or ""),
            "output_hash": str(row.get("output_hash") or ""),
        },
    )
    builder.set_data("/trace/payload_markdown", payload_markdown)
    return builder
