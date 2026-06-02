from __future__ import annotations

import socket
from urllib.parse import urlparse


def _normalize_host(value: str | None) -> str:
    normalized = value.strip().lower() if isinstance(value, str) else ""
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1].strip()
    return normalized


def target_matches_runtime_url(target: str, approved_url: str) -> bool:
    normalized_target = target.strip() if isinstance(target, str) else ""
    normalized_url = approved_url.strip() if isinstance(approved_url, str) else ""
    if not normalized_target or not normalized_url:
        return False
    if normalized_target == normalized_url:
        return True
    if "://" in normalized_target:
        return False
    parsed = urlparse(normalized_url)
    host = _normalize_host(parsed.hostname)
    if not host:
        return False
    scheme = parsed.scheme.strip().lower() if isinstance(parsed.scheme, str) else ""
    port = parsed.port
    if port is None:
        if scheme == "https":
            port = 443
        elif scheme == "http":
            port = 80
    if port is None:
        return False
    resolved_targets = {normalized_url}
    try:
        infos = socket.getaddrinfo(
            host,
            port,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except Exception:
        infos = []
    for info in infos:
        sockaddr = info[4] if len(info) > 4 else None
        if not isinstance(sockaddr, tuple) or not sockaddr:
            continue
        ip_value = _normalize_host(sockaddr[0] if isinstance(sockaddr[0], str) else "")
        if not ip_value:
            continue
        resolved_targets.add(f"{ip_value}:{int(port)}")
    return normalized_target in resolved_targets
