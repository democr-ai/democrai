from __future__ import annotations

import asyncio
import socket
import subprocess
import threading
from typing import Any


_default_endpoint: str | None = None
_default_endpoint_lock = threading.Lock()


class WindowsHelperBackend:
    supports_pid_enforcement = False

    def ensure_ready(self) -> None:
        return

    def default_socket_path(self) -> str:
        # CPython on Windows has no AF_UNIX: the helper listens on loopback
        # TCP. The port is OS-assigned (bind to 0) and cached per process so
        # every caller in this process sees the same endpoint — the same
        # stability the per-pid unix socket path provided. Children inherit it
        # via OS_SANDBOX_HELPER_SOCKET_ENV before the helper starts.
        global _default_endpoint
        with _default_endpoint_lock:
            if _default_endpoint is None:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                    probe.bind(("127.0.0.1", 0))
                    port = probe.getsockname()[1]
                _default_endpoint = f"tcp:127.0.0.1:{port}"
            return _default_endpoint

    def can_autostart_directly(self) -> bool:
        return True

    def autostart_interactive(self, runtime_mode: str | None) -> bool:
        return False

    def autostart_stdin(self, *, strategy: str, interactive: bool) -> Any:
        return subprocess.DEVNULL

    def validate_client_and_target_pid(
        self,
        *,
        writer: asyncio.StreamWriter,
        requested_pid: int | None,
        parent_pid: int | None,
    ) -> int | None:
        if requested_pid is None:
            return None
        return int(requested_pid)

    def apply(self, endpoints: list[dict[str, Any]], *, pid: int | None) -> None:
        raise RuntimeError("os_sandbox_helper_network_enforcement_not_supported:win32")

    def clear(self, *, pid: int | None) -> None:
        raise RuntimeError("os_sandbox_helper_network_enforcement_not_supported:win32")
