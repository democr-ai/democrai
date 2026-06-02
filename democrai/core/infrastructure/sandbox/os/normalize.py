from __future__ import annotations

from urllib.parse import urlparse

from .models import NetworkEndpoint


_DEFAULT_PORTS: dict[str, int] = {
    "http": 80,
    "https": 443,
    "ws": 80,
    "wss": 443,
    "smtp": 25,
    "smtps": 465,
    "submission": 587,
    "imap": 143,
    "imaps": 993,
    "redis": 6379,
    "rediss": 6379,
    "postgres": 5432,
    "postgresql": 5432,
    "neo4j": 7687,
    "bolt": 7687,
}


def _normalize_host(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_port(value: int | str | None) -> int | None:
    try:
        port = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if port is None or port <= 0 or port > 65535:
        return None
    return port


def normalize_endpoint(endpoint: NetworkEndpoint) -> NetworkEndpoint | None:
    host = _normalize_host(endpoint.host)
    port = _normalize_port(endpoint.port)
    protocol = str(endpoint.protocol or "tcp").strip().lower() or "tcp"
    if not host or port is None:
        return None
    return NetworkEndpoint(
        host=host,
        port=port,
        protocol=protocol,
        source=str(endpoint.source or "").strip(),
        purpose=str(endpoint.purpose or "").strip(),
    )


def endpoint_from_target(
    target: str,
    *,
    source: str = "",
    purpose: str = "",
    protocol: str = "tcp",
) -> NetworkEndpoint | None:
    raw = str(target or "").strip()
    if not raw:
        return None

    parsed = urlparse(raw)
    if "://" in raw and parsed.scheme:
        host = _normalize_host(parsed.hostname)
        port = _normalize_port(parsed.port) or _DEFAULT_PORTS.get(
            str(parsed.scheme or "").strip().lower()
        )
        if not host or port is None:
            return None
        return normalize_endpoint(
            NetworkEndpoint(
                host=host,
                port=port,
                protocol=protocol,
                source=source,
                purpose=purpose,
            )
        )

    if ":" in raw and "://" not in raw:
        host_part, _, port_part = raw.rpartition(":")
        host = _normalize_host(host_part)
        port = _normalize_port(port_part)
        if host and port is not None:
            return normalize_endpoint(
                NetworkEndpoint(
                    host=host,
                    port=port,
                    protocol=protocol,
                    source=source,
                    purpose=purpose,
                )
            )

    return None


def dedupe_endpoints(endpoints: list[NetworkEndpoint]) -> list[NetworkEndpoint]:
    deduped: list[NetworkEndpoint] = []
    seen: set[tuple[str, int, str]] = set()
    for endpoint in endpoints:
        normalized = normalize_endpoint(endpoint)
        if normalized is None:
            continue
        key = (normalized.host, normalized.port, normalized.protocol)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(normalized)
    return deduped
