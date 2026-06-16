from __future__ import annotations

import ipaddress
import os
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.runtime.foundation.paths import runtime_unix_socket_path


ENGINE_ORCHESTRATOR_AUTH_AUDIENCE = "engine-orchestrator"
ENGINE_ORCHESTRATOR_AUTH_SCOPE = "engine_orchestrator:access"


def _get(config: Any | None, key: str, default: Any) -> Any:
    getter = getattr(config, "get", None)
    return getter(key, default) if callable(getter) else default


def _default_transport() -> str:
    return "tcp" if sys.platform == "win32" else "unix"


def _default_socket_path() -> str:
    return str(runtime_unix_socket_path("engine-orchestrator.sock").resolve())


def _host_is_loopback(host: str) -> bool:
    resolved = str(host or "").strip().lower()
    if resolved in {"localhost"}:
        return True
    if resolved.startswith("[") and resolved.endswith("]"):
        resolved = resolved[1:-1]
    try:
        return ipaddress.ip_address(resolved).is_loopback
    except ValueError:
        return False


class EngineOrchestratorConfig(BaseModel):
    enabled: bool = True
    transport: str = _default_transport()
    socket_path: str = _default_socket_path()
    host: str = "127.0.0.1"
    port: int = 40151
    tls_enabled: bool = False
    tls_cert_file: str = ""
    tls_key_file: str = ""
    tls_ca_file: str = ""
    startup_timeout_seconds: float = 30.0
    invoke_timeout_seconds: float | None = None
    registry_reconcile_seconds: float = 5.0
    job_terminal_ttl_seconds: float = 300.0
    job_output_queue_size: int = 256
    scheduler_max_queue_depth: int = 100
    scheduler_submit_timeout_seconds: float = 0.0
    scheduler_worker_count: int = 4
    scheduler_graceful_shutdown_seconds: float = 30.0
    batch_wait_seconds: float = 0.05
    batch_queue_size: int = 256
    runtime_transition_worker_count: int = 1
    invocation_worker_count: int = 4
    max_message_bytes: int = 128 * 1024 * 1024

    @classmethod
    def load(cls, config: Any | None = None) -> "EngineOrchestratorConfig":
        transport = str(
            _get(config, "ai.engine_orchestrator.transport", "") or ""
        ).strip().lower()
        socket_path = str(
            _get(config, "ai.engine_orchestrator.socket_path", "") or ""
        ).strip()
        invoke_timeout = float(
            _get(config, "ai.engine_orchestrator.invoke_timeout_seconds", 0) or 0
        )
        max_message_mb = int(
            _get(config, "ai.engine_orchestrator.max_message_mb", 128) or 128
        )
        return cls(
            enabled=bool(_get(config, "ai.engine_orchestrator.enabled", True)),
            transport=transport or _default_transport(),
            socket_path=socket_path or _default_socket_path(),
            host=str(
                _get(config, "ai.engine_orchestrator.host", "127.0.0.1")
                or "127.0.0.1"
            ).strip()
            or "127.0.0.1",
            port=int(_get(config, "ai.engine_orchestrator.port", 40151) or 40151),
            tls_enabled=normalize_bool(
                _get(config, "ai.engine_orchestrator.tls.enabled", False),
                default=False,
            ),
            tls_cert_file=str(
                _get(config, "ai.engine_orchestrator.tls.cert_file", "") or ""
            ).strip(),
            tls_key_file=str(
                _get(config, "ai.engine_orchestrator.tls.key_file", "") or ""
            ).strip(),
            tls_ca_file=str(
                _get(config, "ai.engine_orchestrator.tls.ca_file", "") or ""
            ).strip(),
            startup_timeout_seconds=max(
                1.0,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.startup_timeout_seconds",
                        30,
                    )
                    or 30
                ),
            ),
            invoke_timeout_seconds=None if invoke_timeout <= 0 else invoke_timeout,
            registry_reconcile_seconds=max(
                1.0,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.registry_reconcile_seconds",
                        5,
                    )
                    or 5
                ),
            ),
            job_terminal_ttl_seconds=max(
                0.0,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.job_terminal_ttl_seconds",
                        300,
                    )
                    or 0
                ),
            ),
            job_output_queue_size=max(
                1,
                int(
                    _get(config, "ai.engine_orchestrator.job_output_queue_size", 256)
                    or 256
                ),
            ),
            scheduler_max_queue_depth=max(
                1,
                int(
                    _get(
                        config,
                        "ai.engine_orchestrator.scheduler_max_queue_depth",
                        100,
                    )
                    or 100
                ),
            ),
            scheduler_submit_timeout_seconds=max(
                0.0,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.scheduler_submit_timeout_seconds",
                        0,
                    )
                    or 0
                ),
            ),
            scheduler_worker_count=max(
                4,
                int(
                    _get(
                        config,
                        "ai.engine_orchestrator.scheduler_worker_count",
                        4,
                    )
                    or 4
                ),
            ),
            scheduler_graceful_shutdown_seconds=max(
                0.1,
                float(
                    _get(
                        config,
                        "ai.engine_orchestrator.scheduler_graceful_shutdown_seconds",
                        30,
                    )
                    or 30
                ),
            ),
            batch_wait_seconds=max(
                0.0,
                float(
                    _get(config, "ai.engine_orchestrator.batch_wait_seconds", 0.05)
                    or 0.05
                ),
            ),
            batch_queue_size=max(
                1,
                int(_get(config, "ai.engine_orchestrator.batch_queue_size", 256) or 256),
            ),
            runtime_transition_worker_count=max(
                1,
                int(
                    _get(
                        config,
                        "ai.engine_orchestrator.runtime_transition_worker_count",
                        1,
                    )
                    or 1
                ),
            ),
            invocation_worker_count=max(
                4,
                int(
                    _get(
                        config,
                        "ai.engine_orchestrator.invocation_worker_count",
                        4,
                    )
                    or 4
                ),
            ),
            max_message_bytes=max(4, max_message_mb) * 1024 * 1024,
        )

    @property
    def grpc_options(self) -> list[tuple[str, int]]:
        return [
            ("grpc.max_send_message_length", self.max_message_bytes),
            ("grpc.max_receive_message_length", self.max_message_bytes),
        ]

    @property
    def target(self) -> str:
        if self.transport == "unix":
            return f"unix:{self.socket_path}"
        if self.transport == "tcp":
            self.validate_transport_security()
            return f"{self.host}:{self.port}"
        raise ValueError(f"engine_orchestrator_transport_unsupported:{self.transport}")

    def validate_transport_security(self) -> None:
        if self.transport != "tcp":
            return
        if self.tls_enabled:
            return
        if _host_is_loopback(self.host):
            return
        raise RuntimeError(
            "engine_orchestrator_insecure_tcp_requires_tls:"
            f"host={self.host!r}; set ai.engine_orchestrator.tls.enabled=true"
        )

    def cleanup_socket(self) -> None:
        if self.transport != "unix":
            return
        path = Path(self.socket_path)
        try:
            if path.exists() or path.is_socket():
                path.unlink()
        except FileNotFoundError:
            return

    @staticmethod
    def process_env(*, parent_pid: int | None = None) -> dict[str, str]:
        env = dict(os.environ)
        env["DEMOCRAI_ENGINE_ORCHESTRATOR"] = "1"
        if parent_pid is not None and int(parent_pid) > 0:
            env["DEMOCRAI_ENGINE_ORCHESTRATOR_PARENT_PID"] = str(int(parent_pid))
        return env
