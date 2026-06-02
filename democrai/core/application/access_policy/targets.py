from __future__ import annotations

import os
from urllib.parse import urlparse

from democrai.core.application.access_policy.operations import ResourceType
from democrai.core.application.access_policy.operations import verify_resource_type


def normalize_target(resource_type: str | ResourceType, target: str) -> str:
    resolved_resource_type = verify_resource_type(resource_type)
    raw = str(target or "").strip()
    if not raw:
        return ""
    if resolved_resource_type == ResourceType.FILESYSTEM:
        return os.path.normpath(os.path.abspath(os.path.expanduser(raw)))
    if resolved_resource_type == ResourceType.NETWORK:
        return normalize_network_target(raw)
    return raw


def normalize_network_target(target: str) -> str:
    raw = target
    parsed = urlparse(raw)
    scheme = parsed.scheme
    netloc = parsed.netloc
    if scheme in {"http", "https", "ws", "wss"} and netloc:
        path = parsed.path or ""
        params = f";{parsed.params}" if parsed.params else ""
        query = f"?{parsed.query}" if parsed.query else ""
        fragment = f"#{parsed.fragment}" if parsed.fragment else ""
        return f"{scheme}://{netloc}{path}{params}{query}{fragment}"
    if scheme and netloc:
        return f"{scheme}://{netloc}"
    return raw.lower() if _looks_like_host_port(raw) else raw


def _looks_like_host_port(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw or "/" in raw:
        return False
    if ":" in raw:
        host, _, port = raw.rpartition(":")
        return bool(host.strip()) and port.isdigit()
    return "." in raw
