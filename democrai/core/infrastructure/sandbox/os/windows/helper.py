from __future__ import annotations

import asyncio
import os
import subprocess
from typing import Any


class WindowsHelperBackend:
    supports_pid_enforcement = False

    def ensure_ready(self) -> None:
        return

    def default_socket_path(self) -> str:
        from democrai.core.runtime.foundation.paths import runtime_unix_socket_path

        return str(
            runtime_unix_socket_path(f"os_sandbox_helper_{os.getpid()}.sock").resolve()
        )

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
