from __future__ import annotations

import json
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse


def parse_proxy_source(source: str) -> tuple[str, str] | None:
    parsed = urlparse(str(source or ""))
    if parsed.path != "/media/proxy":
        return None
    params = parse_qs(parsed.query)
    module_name = str((params.get("module_name") or [""])[0])
    url = str((params.get("url") or [""])[0])
    return module_name, url


def _send_ipc(window: Any, payload: dict[str, Any]) -> None:
    data = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    window.client.write(data)
    window.client.flush()


def send_media_resolve(
    window: Any,
    *,
    request_id: str,
    module_name: str,
    url: str,
    force_refresh: bool,
    client_generation: int | None = None,
) -> None:
    _send_ipc(
        window,
        {
            "request_id": request_id,
            "jwt": window.jwt,
            "session_key": str(getattr(window, "session_key", "") or ""),
            "type": "mediaResolve",
            "mediaResolve": {
                "module_name": module_name,
                "url": url,
                "force_refresh": bool(force_refresh),
                "client_generation": int(client_generation or 0),
            },
        },
    )


def send_media_stream_open(
    window: Any,
    *,
    request_id: str,
    module_name: str,
    url: str,
    client_generation: int | None = None,
) -> None:
    _send_ipc(
        window,
        {
            "request_id": request_id,
            "jwt": window.jwt,
            "session_key": str(getattr(window, "session_key", "") or ""),
            "type": "mediaStreamOpen",
            "mediaStreamOpen": {
                "module_name": module_name,
                "url": url,
                "client_generation": int(client_generation or 0),
            },
        },
    )


def send_media_stream_close(window: Any, *, stream_id: str) -> None:
    _send_ipc(
        window,
        {
            "request_id": str(uuid.uuid4()),
            "jwt": window.jwt,
            "session_key": str(getattr(window, "session_key", "") or ""),
            "type": "mediaStreamClose",
            "mediaStreamClose": {"stream_id": stream_id},
        },
    )
