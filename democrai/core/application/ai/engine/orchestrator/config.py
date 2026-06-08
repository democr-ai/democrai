from __future__ import annotations

import os
import ipaddress
import sys
from pathlib import Path
from typing import Any

from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.paths import runtime_unix_socket_path


ENGINE_ORCHESTRATOR_AUTH_AUDIENCE = "engine-orchestrator"
ENGINE_ORCHESTRATOR_AUTH_SCOPE = "engine_orchestrator:access"


def orchestrator_enabled(config: Any | None = None) -> bool:
    getter = getattr(config, "get", None)
    if callable(getter):
        return bool(getter("ai.engine_orchestrator.enabled", True))
    return True


def orchestrator_transport(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    configured = str(
        getter("ai.engine_orchestrator.transport", "") if callable(getter) else ""
    ).strip().lower()
    if configured:
        return configured
    return "tcp" if sys.platform == "win32" else "unix"


def orchestrator_socket_path(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    configured = str(
        getter("ai.engine_orchestrator.socket_path", "") if callable(getter) else ""
    ).strip()
    if configured:
        return configured
    return str(runtime_unix_socket_path("engine-orchestrator.sock").resolve())


def orchestrator_host(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("ai.engine_orchestrator.host", "127.0.0.1")
        if callable(getter)
        else "127.0.0.1"
    ).strip() or "127.0.0.1"


def orchestrator_port(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = getter("ai.engine_orchestrator.port", 40151) if callable(getter) else 40151
    return int(value or 40151)


def orchestrator_tls_enabled(config: Any | None = None) -> bool:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.tls.enabled", False)
        if callable(getter)
        else False
    )
    return normalize_bool(value, default=False)


def orchestrator_tls_cert_file(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("ai.engine_orchestrator.tls.cert_file", "")
        if callable(getter)
        else ""
    ).strip()


def orchestrator_tls_key_file(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("ai.engine_orchestrator.tls.key_file", "")
        if callable(getter)
        else ""
    ).strip()


def orchestrator_tls_ca_file(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("ai.engine_orchestrator.tls.ca_file", "")
        if callable(getter)
        else ""
    ).strip()


def _orchestrator_host_is_loopback(host: str) -> bool:
    resolved = str(host or "").strip().lower()
    if resolved in {"localhost"}:
        return True
    if resolved.startswith("[") and resolved.endswith("]"):
        resolved = resolved[1:-1]
    try:
        return ipaddress.ip_address(resolved).is_loopback
    except ValueError:
        return False


def validate_orchestrator_transport_security(config: Any | None = None) -> None:
    if orchestrator_transport(config) != "tcp":
        return
    if orchestrator_tls_enabled(config):
        return
    host = orchestrator_host(config)
    if _orchestrator_host_is_loopback(host):
        return
    raise RuntimeError(
        "engine_orchestrator_insecure_tcp_requires_tls:"
        f"host={host!r}; set ai.engine_orchestrator.tls.enabled=true"
    )


def orchestrator_startup_timeout_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.startup_timeout_seconds", 30)
        if callable(getter)
        else 30
    )
    return max(1.0, float(value or 30))


def orchestrator_invoke_timeout_seconds(config: Any | None = None) -> float | None:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.invoke_timeout_seconds", 0)
        if callable(getter)
        else 0
    )
    resolved = float(value or 0)
    if resolved <= 0:
        return None
    return resolved


def orchestrator_registry_reconcile_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.registry_reconcile_seconds", 5)
        if callable(getter)
        else 5
    )
    return max(1.0, float(value or 5))


def orchestrator_job_terminal_ttl_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.job_terminal_ttl_seconds", 300)
        if callable(getter)
        else 300
    )
    return max(0.0, float(value or 0))


def orchestrator_job_output_queue_size(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.job_output_queue_size", 256)
        if callable(getter)
        else 256
    )
    return max(1, int(value or 256))


def orchestrator_scheduler_max_queue_depth(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.scheduler_max_queue_depth", 100)
        if callable(getter)
        else 100
    )
    return max(1, int(value or 100))


def orchestrator_scheduler_submit_timeout_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.scheduler_submit_timeout_seconds", 0)
        if callable(getter)
        else 0
    )
    return max(0.0, float(value or 0))


def orchestrator_scheduler_worker_count(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.scheduler_worker_count", 4)
        if callable(getter)
        else 4
    )
    return max(4, int(value or 4))


def orchestrator_scheduler_graceful_shutdown_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.scheduler_graceful_shutdown_seconds", 30)
        if callable(getter)
        else 30
    )
    return max(0.1, float(value or 30))


def orchestrator_batch_wait_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.batch_wait_seconds", 0.05)
        if callable(getter)
        else 0.05
    )
    return max(0.0, float(value or 0.05))


def orchestrator_batch_queue_size(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.batch_queue_size", 256)
        if callable(getter)
        else 256
    )
    return max(1, int(value or 256))


def orchestrator_runtime_transition_worker_count(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.runtime_transition_worker_count", 1)
        if callable(getter)
        else 1
    )
    return max(1, int(value or 1))


def orchestrator_invocation_worker_count(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.invocation_worker_count", 4)
        if callable(getter)
        else 4
    )
    return max(4, int(value or 4))


def orchestrator_max_message_bytes(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = (
        getter("ai.engine_orchestrator.max_message_mb", 128)
        if callable(getter)
        else 128
    )
    return max(4, int(value or 128)) * 1024 * 1024


def orchestrator_grpc_options(config: Any | None = None) -> list[tuple[str, int]]:
    max_message_bytes = orchestrator_max_message_bytes(config)
    return [
        ("grpc.max_send_message_length", max_message_bytes),
        ("grpc.max_receive_message_length", max_message_bytes),
    ]


def orchestrator_target(config: Any | None = None) -> str:
    transport = orchestrator_transport(config)
    if transport == "unix":
        return f"unix:{orchestrator_socket_path(config)}"
    if transport == "tcp":
        validate_orchestrator_transport_security(config)
        return f"{orchestrator_host(config)}:{orchestrator_port(config)}"
    raise ValueError(f"engine_orchestrator_transport_unsupported:{transport}")


def cleanup_orchestrator_socket(config: Any | None = None) -> None:
    if orchestrator_transport(config) != "unix":
        return
    path = Path(orchestrator_socket_path(config))
    try:
        if path.exists() or path.is_socket():
            path.unlink()
    except FileNotFoundError:
        return


def orchestrator_process_env(*, parent_pid: int | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["DEMOCRAI_ENGINE_ORCHESTRATOR"] = "1"
    if parent_pid is not None and int(parent_pid) > 0:
        env["DEMOCRAI_ENGINE_ORCHESTRATOR_PARENT_PID"] = str(int(parent_pid))
    return env
