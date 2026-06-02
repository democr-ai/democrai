from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import data_dir

from .models import NetworkEndpoint
from .normalize import dedupe_endpoints, endpoint_from_target


def get_observed_endpoints_file_path(config: Any | None = None) -> str:
    resolved_config = app_ctx().config if config is None else config
    getter = getattr(resolved_config, "get", None)
    if callable(getter):
        configured = str(getter("sandbox.os.observed_file", "") or "").strip()
        if configured:
            return configured
    return str((data_dir() / "os_sandbox_observed_endpoints.json").resolve())


def _read_observed_endpoints(config: Any | None = None) -> list[NetworkEndpoint]:
    path = Path(get_observed_endpoints_file_path(config)).expanduser().resolve()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    raw_items = payload.get("endpoints")
    if not isinstance(raw_items, list):
        return []
    endpoints: list[NetworkEndpoint] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        endpoint = endpoint_from_target(
            f"{str(item.get('host') or '').strip()}:{int(item.get('port') or 0)}",
            source=str(item.get("source") or "observed").strip(),
            purpose=str(item.get("purpose") or "observed").strip(),
            protocol=str(item.get("protocol") or "tcp").strip() or "tcp",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return dedupe_endpoints(endpoints)


def collect_observed_runtime_endpoints(config: Any | None = None) -> list[NetworkEndpoint]:
    return _read_observed_endpoints(config)


def record_observed_runtime_target(
    target: str,
    *,
    source: str = "observed",
    purpose: str = "observed",
    protocol: str = "tcp",
    config: Any | None = None,
) -> bool:
    endpoint = endpoint_from_target(
        str(target or "").strip(),
        source=source,
        purpose=purpose,
        protocol=protocol,
    )
    if endpoint is None or "*" in str(endpoint.host or ""):
        return False

    path = Path(get_observed_endpoints_file_path(config)).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    endpoints = _read_observed_endpoints(config)
    existing = {
        (item.host, int(item.port), str(item.protocol or "tcp").strip().lower())
        for item in endpoints
    }
    key = (endpoint.host, int(endpoint.port), str(endpoint.protocol or "tcp").strip().lower())
    if key in existing:
        return False
    endpoints.append(endpoint)
    payload = {
        "version": 1,
        "endpoints": [
            {
                "host": item.host,
                "port": int(item.port),
                "protocol": str(item.protocol or "tcp").strip().lower(),
                "source": str(item.source or "").strip(),
                "purpose": str(item.purpose or "").strip(),
            }
            for item in dedupe_endpoints(endpoints)
        ],
    }
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)
    os.chmod(path, 0o600)
    return True
