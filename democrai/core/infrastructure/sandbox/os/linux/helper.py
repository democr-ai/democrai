from __future__ import annotations

import asyncio
import os
import socket
import struct
from pathlib import Path
from typing import Any

from democrai.core.infrastructure.sandbox.os.linux.network import (
    apply_application_network_endpoints,
    clear_application_network_allowlist,
    ensure_linux_network_enforcement_ready,
)


class LinuxHelperBackend:
    supports_pid_enforcement = True

    def ensure_ready(self) -> None:
        ensure_linux_network_enforcement_ready()

    def peer_credentials(
        self,
        writer: asyncio.StreamWriter,
    ) -> tuple[int, int, int]:
        sock = writer.get_extra_info("socket")
        if sock is None:
            raise RuntimeError("os_sandbox_helper_missing_peer_socket")
        option = getattr(socket, "SO_PEERCRED", 17)
        raw = sock.getsockopt(socket.SOL_SOCKET, option, struct.calcsize("3i"))
        pid, uid, gid = struct.unpack("3i", raw)
        return int(pid), int(uid), int(gid)

    def parent_pid_of(self, pid: int) -> int | None:
        try:
            raw = Path(f"/proc/{int(pid)}/status").read_text(encoding="utf-8")
        except Exception:
            return None
        for line in raw.splitlines():
            if not line.startswith("PPid:"):
                continue
            try:
                return int(str(line.split(":", 1)[1]).strip())
            except Exception:
                return None
        return None

    def is_same_or_descendant(self, pid: int, root_pid: int) -> bool:
        current = int(pid)
        root = int(root_pid)
        visited: set[int] = set()
        while current > 1 and current not in visited:
            if current == root:
                return True
            visited.add(current)
            parent = self.parent_pid_of(current)
            if parent is None:
                return False
            current = parent
        return current == root

    def validate_client_and_target_pid(
        self,
        *,
        writer: asyncio.StreamWriter,
        requested_pid: int | None,
        parent_pid: int | None,
    ) -> int | None:
        peer_pid, peer_uid, _peer_gid = self.peer_credentials(writer)
        expected_uid = expected_client_uid()
        if peer_uid != expected_uid:
            raise RuntimeError(
                f"os_sandbox_helper_invalid_client_uid:{peer_uid}:{expected_uid}"
            )
        if parent_pid is not None and not self.is_same_or_descendant(
            int(peer_pid),
            int(parent_pid),
        ):
            raise RuntimeError(
                f"os_sandbox_helper_invalid_client_pid:{peer_pid}:{int(parent_pid)}"
            )
        if requested_pid is None:
            return None
        resolved_pid = int(requested_pid)
        if parent_pid is not None and not self.is_same_or_descendant(
            resolved_pid,
            int(parent_pid),
        ):
            raise RuntimeError(
                f"os_sandbox_helper_invalid_target_pid:{resolved_pid}:{int(parent_pid)}"
            )
        return resolved_pid

    def apply(self, endpoints: list[dict[str, Any]], *, pid: int | None) -> None:
        apply_application_network_endpoints(endpoints, pid=pid)

    def clear(self, *, pid: int | None) -> None:
        clear_application_network_allowlist(pid=pid)


def expected_client_uid() -> int:
    elevated_uid = str(
        os.environ.get("SUDO_UID") or os.environ.get("PKEXEC_UID") or ""
    ).strip()
    if elevated_uid:
        try:
            return int(elevated_uid)
        except Exception:
            pass
    return int(os.getuid())
