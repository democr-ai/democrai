from __future__ import annotations

import ipaddress
import sys
from pathlib import Path
from typing import Any

from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.paths import state_dir


KNOWLEDGE_QUERY_AUTH_AUDIENCE = "knowledge-query"
KNOWLEDGE_QUERY_AUTH_SCOPE = "knowledge_query:access"


def knowledge_query_enabled(config: Any | None = None) -> bool:
    getter = getattr(config, "get", None)
    if callable(getter):
        return bool(getter("knowledge.query_service.enabled", True))
    return True


def knowledge_query_transport(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    configured = str(
        getter("knowledge.query_service.transport", "") if callable(getter) else ""
    ).strip().lower()
    if configured:
        return configured
    return "tcp" if sys.platform == "win32" else "unix"


def knowledge_query_socket_path(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    configured = str(
        getter("knowledge.query_service.socket_path", "") if callable(getter) else ""
    ).strip()
    if configured:
        return configured
    return str((state_dir() / "knowledge-query.sock").resolve())


def knowledge_query_host(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("knowledge.query_service.host", "127.0.0.1")
        if callable(getter)
        else "127.0.0.1"
    ).strip() or "127.0.0.1"


def knowledge_query_port(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = getter("knowledge.query_service.port", 50153) if callable(getter) else 50153
    return int(value or 50153)


def knowledge_query_tls_enabled(config: Any | None = None) -> bool:
    getter = getattr(config, "get", None)
    value = (
        getter("knowledge.query_service.tls.enabled", False)
        if callable(getter)
        else False
    )
    return normalize_bool(value, default=False)


def knowledge_query_tls_cert_file(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("knowledge.query_service.tls.cert_file", "")
        if callable(getter)
        else ""
    ).strip()


def knowledge_query_tls_key_file(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("knowledge.query_service.tls.key_file", "")
        if callable(getter)
        else ""
    ).strip()


def knowledge_query_tls_ca_file(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("knowledge.query_service.tls.ca_file", "")
        if callable(getter)
        else ""
    ).strip()


def _knowledge_query_host_is_loopback(host: str) -> bool:
    resolved = host.strip().lower()
    if resolved in {"localhost"}:
        return True
    if resolved.startswith("[") and resolved.endswith("]"):
        resolved = resolved[1:-1]
    try:
        return ipaddress.ip_address(resolved).is_loopback
    except ValueError:
        return False


def validate_knowledge_query_transport_security(config: Any | None = None) -> None:
    if knowledge_query_transport(config) != "tcp":
        return
    if knowledge_query_tls_enabled(config):
        return
    host = knowledge_query_host(config)
    if _knowledge_query_host_is_loopback(host):
        return
    raise RuntimeError(
        "knowledge_query_insecure_tcp_requires_tls:"
        f"host={host!r}; set knowledge.query_service.tls.enabled=true"
    )


def knowledge_query_startup_timeout_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("knowledge.query_service.startup_timeout_seconds", 30)
        if callable(getter)
        else 30
    )
    return max(1.0, float(value or 30))


def knowledge_query_timeout_seconds(config: Any | None = None) -> float | None:
    getter = getattr(config, "get", None)
    value = (
        getter("knowledge.query_service.timeout_seconds", 120)
        if callable(getter)
        else 120
    )
    resolved = float(value or 120)
    if resolved <= 0:
        return None
    return resolved


def knowledge_query_max_message_bytes(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("knowledge.query_service.max_message_mb", 64)
        if callable(getter)
        else 64
    )
    return max(4, int(value or 64)) * 1024 * 1024


def knowledge_query_grpc_options(config: Any | None = None) -> list[tuple[str, int]]:
    max_message_bytes = knowledge_query_max_message_bytes(config)
    return [
        ("grpc.max_send_message_length", max_message_bytes),
        ("grpc.max_receive_message_length", max_message_bytes),
    ]


def knowledge_query_target(config: Any | None = None) -> str:
    transport = knowledge_query_transport(config)
    if transport == "unix":
        return f"unix:{knowledge_query_socket_path(config)}"
    if transport == "tcp":
        validate_knowledge_query_transport_security(config)
        return f"{knowledge_query_host(config)}:{knowledge_query_port(config)}"
    raise ValueError(f"knowledge_query_transport_unsupported:{transport}")


def cleanup_knowledge_query_socket(config: Any | None = None) -> None:
    if knowledge_query_transport(config) != "unix":
        return
    path = Path(knowledge_query_socket_path(config))
    try:
        if path.exists() or path.is_socket():
            path.unlink()
    except FileNotFoundError:
        return
