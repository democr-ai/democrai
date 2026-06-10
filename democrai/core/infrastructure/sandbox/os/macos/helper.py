from __future__ import annotations

import asyncio
import os
import socket
import struct
import subprocess
from pathlib import Path
from typing import Any


class MacOSHelperBackend:
    supports_pid_enforcement = False

    def ensure_ready(self) -> None:
        return

    def default_socket_path(self) -> str:
        return str(Path("/tmp") / f"dc-os-helper-{os.getpid()}.sock")

    def can_autostart_directly(self) -> bool:
        return True

    def autostart_interactive(self, runtime_mode: str | None) -> bool:
        return False

    def autostart_stdin(self, *, strategy: str, interactive: bool) -> Any:
        return subprocess.DEVNULL

    def peer_credentials(
        self,
        writer: asyncio.StreamWriter,
    ) -> tuple[int | None, int, int]:
        sock = writer.get_extra_info("socket")
        if sock is None:
            raise RuntimeError("os_sandbox_helper_missing_peer_socket")
        if not hasattr(socket, "LOCAL_PEERCRED"):
            raise RuntimeError("os_sandbox_helper_peer_credentials_unsupported:macos")
        raw = sock.getsockopt(
            0,
            socket.LOCAL_PEERCRED,
            struct.calcsize("3i"),
        )
        if len(raw) < struct.calcsize("2i"):
            raise RuntimeError("os_sandbox_helper_peer_credentials_invalid:macos")
        _version, uid = struct.unpack("2i", raw[: struct.calcsize("2i")])
        gid = 0
        if len(raw) >= struct.calcsize("3i"):
            _version, uid, gid = struct.unpack("3i", raw[: struct.calcsize("3i")])
        return None, int(uid), int(gid)

    def validate_client_and_target_pid(
        self,
        *,
        writer: asyncio.StreamWriter,
        requested_pid: int | None,
        parent_pid: int | None,
    ) -> int | None:
        _peer_pid, peer_uid, _peer_gid = self.peer_credentials(writer)
        expected_uid = expected_client_uid()
        if peer_uid != expected_uid:
            raise RuntimeError(
                f"os_sandbox_helper_invalid_client_uid:{peer_uid}:{expected_uid}"
            )
        if requested_pid is None:
            return None
        return int(requested_pid)

    def apply(self, endpoints: list[dict[str, Any]], *, pid: int | None) -> None:
        raise RuntimeError("os_sandbox_helper_network_enforcement_not_supported:macos")

    def clear(self, *, pid: int | None) -> None:
        raise RuntimeError("os_sandbox_helper_network_enforcement_not_supported:macos")


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
