from __future__ import annotations

import fnmatch
import ipaddress
import socket
import threading
import time
from urllib.parse import urlparse

from democrai.core.runtime.foundation.app import app_ctx


def normalize_network_target(value: str) -> str:
    return str(value or "").strip()


def _is_ip_literal(host: str) -> bool:
    raw = str(host or "").strip()
    if not raw:
        return False
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    try:
        ipaddress.ip_address(raw)
        return True
    except ValueError:
        return False


def _normalize_host(host: str) -> str:
    normalized = str(host or "").strip()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1].strip()
    return normalized


def _split_netloc(netloc: str) -> tuple[str, str | None]:
    value = str(netloc or "").strip()
    if not value:
        return "", None
    if value.startswith("[") and "]:" in value:
        host, _, port = value.partition("]:")
        return host + "]", port or None
    if value.startswith("[") and value.endswith("]"):
        return value, None
    if ":" in value:
        host, _, port = value.rpartition(":")
        if host:
            return host, port or None
    return value, None


def _parse_endpoint_target(target: str) -> tuple[str | None, str, int | None]:
    raw = normalize_network_target(target)
    if not raw:
        return None, "", None
    if "://" in raw:
        parsed = urlparse(raw)
        scheme = str(parsed.scheme or "").strip().lower() or None
        host = _normalize_host(parsed.hostname or "")
        port = parsed.port
        return scheme, host, port
    host, raw_port = _split_netloc(raw)
    resolved_host = _normalize_host(host)
    try:
        port = int(raw_port) if raw_port else None
    except Exception:
        port = None
    return None, resolved_host, port


def _url_matches_pattern(url: str, pattern: str) -> bool:
    parsed_url = urlparse(normalize_network_target(url))
    parsed_pattern = urlparse(normalize_network_target(pattern))
    if parsed_pattern.scheme and parsed_pattern.scheme != parsed_url.scheme:
        return False
    if parsed_pattern.netloc and not fnmatch.fnmatch(parsed_url.netloc, parsed_pattern.netloc):
        return False
    path_pattern = parsed_pattern.path or "/*"
    return fnmatch.fnmatch(parsed_url.path or "/", path_pattern)


def _hosts_for_match(host: str) -> list[str]:
    normalized = _normalize_host(host)
    if not normalized:
        return []
    hosts = [normalized]
    if normalized == "localhost":
        hosts.extend(["127.0.0.1", "::1"])
    elif normalized == "127.0.0.1":
        hosts.extend(["localhost", "::1"])
    elif normalized == "::1":
        hosts.extend(["localhost", "127.0.0.1"])
    return hosts


def _resolve_host_ips(hostname: str) -> tuple[str, ...]:
    # Keep DNS results fresh in long-running processes.
    ttl_seconds = 60.0
    max_entries = 256
    now = time.monotonic()
    normalized = _normalize_host(hostname)
    if not normalized:
        return ()
    with _RESOLVED_IPS_LOCK:
        cached = _RESOLVED_IPS.get(normalized)
        if cached is not None:
            expires_at, values = cached
            if now < expires_at:
                return values
            _RESOLVED_IPS.pop(normalized, None)
    try:
        infos = socket.getaddrinfo(
            normalized,
            None,
            family=socket.AF_UNSPEC,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        app_ctx().logger.warning(
            f"[Network] DNS resolution failed for network target host {normalized!r}: {exc}"
        )
        return ()
    resolved: set[str] = set()
    for info in infos:
        sockaddr = info[4] if len(info) > 4 else None
        if not isinstance(sockaddr, tuple) or not sockaddr:
            continue
        value = _normalize_host(str(sockaddr[0] or ""))
        if value:
            resolved.add(value)
    values = tuple(sorted(resolved))
    with _RESOLVED_IPS_LOCK:
        _RESOLVED_IPS[normalized] = (now + ttl_seconds, values)
        while len(_RESOLVED_IPS) > max_entries:
            _RESOLVED_IPS.pop(next(iter(_RESOLVED_IPS)), None)
    return values


_RESOLVED_IPS: dict[str, tuple[float, tuple[str, ...]]] = {}
_RESOLVED_IPS_LOCK = threading.Lock()


def _endpoint_pattern_matches(
    *,
    host: str,
    port: int | None,
    pattern: str,
    protocol: str | None = None,
) -> bool:
    raw_pattern = normalize_network_target(pattern)
    if not raw_pattern:
        return False
    parsed = urlparse(raw_pattern.replace("*", "__wildcard__"))
    pattern_scheme = str(parsed.scheme or "").strip().lower() or None
    pattern_netloc = parsed.netloc.replace("__wildcard__", "*")
    if pattern_scheme and pattern_scheme in {"http", "https"}:
        pattern_host, pattern_port = _split_netloc(pattern_netloc)
    elif pattern_scheme:
        if protocol and pattern_scheme != protocol:
            return False
        pattern_host = _normalize_host(parsed.hostname or "")
        pattern_port = str(parsed.port) if parsed.port is not None else None
    else:
        pattern_host, pattern_port = _split_netloc(raw_pattern)
    normalized_pattern_host = _normalize_host(pattern_host)
    if not normalized_pattern_host:
        return False
    if port is not None and pattern_port is not None:
        if not fnmatch.fnmatch(str(port), str(pattern_port)):
            return False
    for candidate_host in _hosts_for_match(host):
        if fnmatch.fnmatch(candidate_host, normalized_pattern_host):
            return True
    if _is_ip_literal(host) and not _is_ip_literal(normalized_pattern_host) and "*" not in normalized_pattern_host:
        resolved_ips = _resolve_host_ips(normalized_pattern_host)
        if _normalize_host(host) in resolved_ips:
            return True
    return False


def is_network_target_allowed(
    target: str,
    allowed_patterns: list[str] | tuple[str, ...] | None,
) -> bool:
    normalized_target = normalize_network_target(target)
    if not normalized_target:
        return False
    patterns = [normalize_network_target(item) for item in list(allowed_patterns or []) if normalize_network_target(item)]
    if not patterns:
        return False
    if normalized_target.startswith(("http://", "https://")):
        for pattern in patterns:
            if _url_matches_pattern(normalized_target, pattern):
                return True
        parsed_target = urlparse(normalized_target)
        for pattern in patterns:
            if _endpoint_pattern_matches(
                host=_normalize_host(parsed_target.hostname or ""),
                port=parsed_target.port,
                pattern=pattern,
                protocol=str(parsed_target.scheme or "").strip().lower() or None,
            ):
                return True
        return False

    protocol, host, port = _parse_endpoint_target(normalized_target)
    if not host:
        return False
    for pattern in patterns:
        if _endpoint_pattern_matches(host=host, port=port, pattern=pattern, protocol=protocol):
            return True
    return False
