from __future__ import annotations

import asyncio
from typing import Any


class WindowsHelperBackend:
    supports_pid_enforcement = False

    def ensure_ready(self) -> None:
        return

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
