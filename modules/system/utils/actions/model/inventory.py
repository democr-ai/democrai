from __future__ import annotations

from typing import Any

from modules.system.utils.actions.engine.models import parse_capabilities, sanitize_name


def prepare_available_model_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_name = str(payload["name"]).strip()
    name = sanitize_name(raw_name) if raw_name else ""
    label = str(payload["label"]).strip()
    model_format = str(payload["format"]).strip().lower()
    source_kind = str(payload["source_kind"]).strip().lower()
    capabilities = parse_capabilities(payload["capabilities"])
    summary = str(payload.get("summary") or "").strip()
    return {
        "name": name,
        "label": label,
        "format": model_format,
        "source_kind": source_kind,
        "capabilities": capabilities,
        "interfaces": [],
        "family": "",
        "summary": summary,
    }
