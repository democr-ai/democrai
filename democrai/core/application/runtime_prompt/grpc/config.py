from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from democrai.core.runtime.foundation.paths import state_dir


RUNTIME_PROMPT_AUTH_AUDIENCE = "runtime-prompt"
RUNTIME_PROMPT_AUTH_SCOPE = "runtime_prompt:access"


def runtime_prompt_transport(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    configured = str(
        getter("runtime_prompt.transport", "") if callable(getter) else ""
    ).strip().lower()
    if configured:
        return configured
    return "tcp" if sys.platform == "win32" else "unix"


def runtime_prompt_socket_path(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    configured = str(
        getter("runtime_prompt.socket_path", "") if callable(getter) else ""
    ).strip()
    if configured:
        return configured
    return str((state_dir() / "runtime-prompt.sock").resolve())


def runtime_prompt_host(config: Any | None = None) -> str:
    getter = getattr(config, "get", None)
    return str(
        getter("runtime_prompt.host", "127.0.0.1")
        if callable(getter)
        else "127.0.0.1"
    ).strip() or "127.0.0.1"


def runtime_prompt_port(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = getter("runtime_prompt.port", 40152) if callable(getter) else 40152
    return int(value or 40152)


def runtime_prompt_timeout_seconds(config: Any | None = None) -> float | None:
    getter = getattr(config, "get", None)
    value = getter("runtime_prompt.timeout_seconds", 300) if callable(getter) else 300
    resolved = float(value or 300)
    if resolved <= 0:
        return None
    return resolved


def runtime_prompt_rpc_timeout_seconds(
    config: Any | None = None,
    *,
    prompt_timeout_seconds: float,
    configured_timeout_seconds: float | None = None,
) -> float | None:
    configured = (
        configured_timeout_seconds
        if configured_timeout_seconds is not None
        else runtime_prompt_timeout_seconds(config)
    )
    if configured is None:
        return None
    prompt_timeout = max(0.0, float(prompt_timeout_seconds or 0.0))
    return max(float(configured), prompt_timeout + 5.0)


def runtime_prompt_start_timeout_seconds(config: Any | None = None) -> float:
    getter = getattr(config, "get", None)
    value = (
        getter("runtime_prompt.start_timeout_seconds", 10)
        if callable(getter)
        else 10
    )
    return max(1.0, float(value or 10))


def runtime_prompt_max_message_bytes(config: Any | None = None) -> int:
    getter = getattr(config, "get", None)
    value = getter("runtime_prompt.max_message_mb", 16) if callable(getter) else 16
    return max(4, int(value or 16)) * 1024 * 1024


def runtime_prompt_grpc_options(config: Any | None = None) -> list[tuple[str, int]]:
    max_message_bytes = runtime_prompt_max_message_bytes(config)
    return [
        ("grpc.max_send_message_length", max_message_bytes),
        ("grpc.max_receive_message_length", max_message_bytes),
    ]


def runtime_prompt_target(config: Any | None = None) -> str:
    transport = runtime_prompt_transport(config)
    if transport == "unix":
        return f"unix:{runtime_prompt_socket_path(config)}"
    if transport == "tcp":
        return f"{runtime_prompt_host(config)}:{runtime_prompt_port(config)}"
    raise ValueError(f"runtime_prompt_transport_unsupported:{transport}")


def cleanup_runtime_prompt_socket(config: Any | None = None) -> None:
    if runtime_prompt_transport(config) != "unix":
        return
    path = Path(runtime_prompt_socket_path(config))
    try:
        if path.exists() or path.is_socket():
            path.unlink()
    except FileNotFoundError:
        return
