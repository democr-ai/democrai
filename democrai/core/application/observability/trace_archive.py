from __future__ import annotations

import gzip
import hashlib
import json
from datetime import timedelta
from typing import Any

from democrai.core.platform.utils.env import SERVER_NAME
from democrai.core.platform.utils.timezone import utc_now_naive
from democrai.core.runtime.foundation.app import app_ctx


TRACE_SCHEMA = "democrai.trace_payload.v1"
DEFAULT_PREVIEW_CHARS = 512


def describe_payload(value: Any, *, preview_chars: int = DEFAULT_PREVIEW_CHARS) -> dict[str, Any]:
    payload_json = _json_text(value)
    payload_hash = _hash_text(payload_json)
    descriptor: dict[str, Any] = {
        "kind": _kind(value),
        "chars": len(payload_json),
        "bytes": len(payload_json.encode("utf-8")),
        "hash": payload_hash,
        "truncated": len(payload_json) > max(0, preview_chars),
    }
    if isinstance(value, dict):
        descriptor["keys"] = sorted(str(key) for key in value.keys())
    if isinstance(value, list):
        descriptor["items"] = len(value)
    preview = _preview(value, preview_chars=max(0, preview_chars))
    if preview not in ({}, [], ""):
        descriptor["preview"] = preview
    return descriptor


def prepare_pipeline_step_record(
    payload: dict[str, Any],
    *,
    preview_chars: int = DEFAULT_PREVIEW_CHARS,
    archive_enabled: bool = True,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    full_input = payload.get("input") or {}
    full_output = payload.get("output") or {}
    full_stats = payload.get("stats") or {}
    full_metadata = payload.get("metadata") or {}
    input_descriptor = describe_payload(full_input, preview_chars=preview_chars)
    output_descriptor = describe_payload(full_output, preview_chars=preview_chars)

    stored = dict(payload)
    stored["input"] = input_descriptor
    stored["output"] = output_descriptor
    stored["stats"] = full_stats
    stored["metadata"] = full_metadata
    stored["input_hash"] = input_descriptor["hash"]
    stored["output_hash"] = output_descriptor["hash"]
    stored["input_size_bytes"] = input_descriptor["bytes"]
    stored["output_size_bytes"] = output_descriptor["bytes"]
    stored["archive_status"] = "pending" if archive_enabled else "none"

    if not archive_enabled:
        return stored, None

    archived = {
        "schema": TRACE_SCHEMA,
        "pipeline_id": payload.get("pipeline_id"),
        "request_id": payload.get("request_id"),
        "step_id": payload.get("step_id"),
        "parent_step_id": payload.get("parent_step_id"),
        "root_method": payload.get("root_method"),
        "type": payload.get("type"),
        "name": payload.get("name"),
        "status": payload.get("status"),
        "started_at": _stringify_datetime(payload.get("started_at")),
        "duration_ms": payload.get("duration_ms"),
        "provider": payload.get("provider"),
        "engine": payload.get("engine"),
        "engine_row_id": payload.get("engine_row_id"),
        "model_registry_id": payload.get("model_registry_id"),
        "model_name": payload.get("model_name"),
        "user_id": payload.get("user_id"),
        "organization_id": payload.get("organization_id"),
        "session_id": payload.get("session_id"),
        "node_id": payload.get("node_id"),
        "input": full_input,
        "output": full_output,
        "stats": full_stats,
        "metadata": full_metadata,
        "error": payload.get("error"),
        "hashes": {
            "input": input_descriptor["hash"],
            "output": output_descriptor["hash"],
        },
    }
    return stored, archived


def archive_queue_payload_hash(payload: dict[str, Any]) -> str:
    return _hash_text(_json_text(payload))


def archive_media_path(payload: dict[str, Any]) -> str:
    now = utc_now_naive()
    pipeline_id = _path_part(payload.get("pipeline_id"), "pipeline")
    step_id = _path_part(payload.get("step_id"), "step")
    return (
        f"observability/traces/{now:%Y/%m/%d}/"
        f"{pipeline_id}/{step_id}.json.gz"
    )


def process_trace_archive_queue(
    provider: Any,
    *,
    limit: int,
    lock_timeout_seconds: int,
) -> dict[str, int]:
    rows = provider.get_trace_archive_ready(
        limit=limit,
        lock_timeout_seconds=lock_timeout_seconds,
    )
    archived = 0
    failed = 0
    node_id = str(getattr(app_ctx(), "node_id", "") or SERVER_NAME or "local")
    for row in rows:
        provider.mark_trace_archive_processing(row.id, locked_by=node_id)
        try:
            payload = json.loads(row.payload_json or "{}")
            media_path = archive_media_path(payload)
            compressed = gzip.compress(
                _json_text(payload).encode("utf-8"),
                compresslevel=6,
            )
            media = getattr(app_ctx(), "media", None)
            if media is None:
                raise RuntimeError("media_provider_unavailable")
            stored_path = str(media.save(media_path, compressed))
            provider.mark_trace_archive_archived(
                row.id,
                archived_media_path=stored_path,
            )
            provider.update_ai_model_pipeline_step_archive(
                step_db_id=row.pipeline_step_db_id,
                step_id=row.step_id,
                archive_status="archived",
                archive_media_path=stored_path,
                archive_error=None,
            )
            archived += 1
        except Exception as exc:
            failed += 1
            retry_at = utc_now_naive() + timedelta(seconds=60)
            provider.mark_trace_archive_failed(
                row.id,
                error=str(exc),
                retry_at=retry_at,
            )
            provider.update_ai_model_pipeline_step_archive(
                step_db_id=row.pipeline_step_db_id,
                step_id=row.step_id,
                archive_status="failed",
                archive_media_path=None,
                archive_error=str(exc),
            )
    return {"processed": len(rows), "archived": archived, "failed": failed}


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _hash_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _kind(value: Any) -> str:
    if isinstance(value, dict):
        return "dict"
    if isinstance(value, list):
        return "list"
    if value is None:
        return "null"
    return type(value).__name__


def _preview(value: Any, *, preview_chars: int) -> Any:
    if preview_chars <= 0:
        return {}
    if isinstance(value, dict):
        preview: dict[str, Any] = {}
        used = 0
        for key in sorted(value.keys(), key=str):
            item = value[key]
            if isinstance(item, (dict, list)):
                continue
            text = str(item)
            if used + len(text) > preview_chars:
                continue
            preview[str(key)] = item
            used += len(text)
        return preview
    if isinstance(value, list):
        return value[:5]
    text = str(value)
    return text[:preview_chars]


def _stringify_datetime(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return str(value.isoformat())
        except Exception:
            return str(value)
    return str(value)


def _path_part(value: Any, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    allowed = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            allowed.append(char)
    return "".join(allowed) or fallback
