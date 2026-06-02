from __future__ import annotations

import os
import tempfile
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

SESSION_COOKIE_NAME = os.getenv("DEMOCRAI_SESSION_COOKIE_NAME", "democrai_sid")


def runtime_window(app_instance: Any) -> Any:
    current = app_instance
    visited = 0
    while current is not None and visited < 10:
        if hasattr(current, "jwt") and hasattr(current, "client"):
            return current
        parent_getter = getattr(current, "parent", None)
        if callable(parent_getter):
            current = parent_getter()
        else:
            break
        visited += 1
    return None


def media_request_path(source: str) -> str:
    raw_source = str(source or "").strip()
    parsed = urlparse(raw_source)
    if parsed.scheme in {"http", "https"} and parsed.path.startswith("/media/"):
        if parsed.query:
            return f"{parsed.path}?{parsed.query}"
        return parsed.path
    if raw_source.startswith("/media/"):
        return raw_source
    return ""


def media_http_url(app_instance: Any, request_path: str) -> str:
    current = app_instance
    visited = 0
    host = "127.0.0.1"
    port = 8000
    while current is not None and visited < 10:
        current_host = getattr(current, "host", None)
        current_port = getattr(current, "port", None)
        if current_host is not None or current_port is not None:
            host = str(current_host or "127.0.0.1")
            port = int(current_port or 8000)
            break
        parent_getter = getattr(current, "parent", None)
        if callable(parent_getter):
            current = parent_getter()
        else:
            break
        visited += 1
    return f"http://{host}:{port}{request_path}"


def fetch_media_bytes(
    app_instance: Any,
    source: str,
    *,
    timeout: float = 15.0,
) -> bytes:
    request_path = media_request_path(source)
    if not request_path:
        return b""
    window = runtime_window(app_instance)
    if window is None:
        return b""
    jwt = str(getattr(window, "jwt", "") or "").strip()
    session_key = str(getattr(window, "session_key", "") or "").strip()
    if not jwt:
        return b""
    headers = {"X-JWT": jwt, "Accept": "*/*"}
    if session_key:
        headers["Cookie"] = f"{SESSION_COOKIE_NAME}={session_key}"
    request = urllib.request.Request(
        url=media_http_url(app_instance, request_path),
        method="GET",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - local app endpoint
            return bytes(response.read() or b"")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return b""


def download_media_to_temp(
    app_instance: Any,
    source: str,
    *,
    prefix: str,
    timeout: float = 30.0,
) -> str:
    request_path = media_request_path(source)
    if not request_path:
        return str(source or "")
    payload = fetch_media_bytes(app_instance, request_path, timeout=timeout)
    if not payload:
        return ""
    suffix = os.path.splitext(request_path.split("?", 1)[0])[1] or ".bin"
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            suffix=suffix,
            prefix=prefix,
            delete=False,
        ) as handle:
            handle.write(payload)
            return handle.name
    except OSError:
        return ""
