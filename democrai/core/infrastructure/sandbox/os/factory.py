from __future__ import annotations

import sys

from democrai.core.infrastructure.sandbox.os.base import (
    BaseOsSandboxProvider,
    NoopOsSandboxProvider,
)
from democrai.core.infrastructure.sandbox.os.linux.provider import LinuxOsSandboxProvider
from democrai.core.infrastructure.sandbox.os.linux.helper import LinuxHelperBackend
from democrai.core.infrastructure.sandbox.os.linux.launch import LinuxCoreLaunchStrategy
from democrai.core.infrastructure.sandbox.os.macos.helper import MacOSHelperBackend
from democrai.core.infrastructure.sandbox.os.macos.launch import MacOSCoreLaunchStrategy
from democrai.core.infrastructure.sandbox.os.macos.provider import MacOSOsSandboxProvider
from democrai.core.infrastructure.sandbox.os.windows.helper import WindowsHelperBackend
from democrai.core.infrastructure.sandbox.os.windows.launch import WindowsCoreLaunchStrategy
from democrai.core.infrastructure.sandbox.os.windows.provider import WindowsOsSandboxProvider


class PortableHelperBackend:
    supports_pid_enforcement = False

    def __init__(self, *, platform: str = "portable") -> None:
        self.platform = str(platform or "portable")

    def ensure_ready(self) -> None:
        return

    def validate_client_and_target_pid(
        self,
        *,
        writer,
        requested_pid: int | None,
        parent_pid: int | None,
    ) -> int | None:
        if requested_pid is None:
            return None
        return int(requested_pid)

    def apply(self, endpoints, *, pid: int | None) -> None:
        raise RuntimeError(
            f"os_sandbox_helper_network_enforcement_not_supported:{self.platform}"
        )

    def clear(self, *, pid: int | None) -> None:
        raise RuntimeError(
            f"os_sandbox_helper_network_enforcement_not_supported:{self.platform}"
        )


class PortableCoreLaunchStrategy:
    requires_relaunch = False

    def __init__(self, *, platform: str = "portable") -> None:
        self.platform = str(platform or "portable")

    def run(self, policy) -> None:
        raise RuntimeError(f"os_sandbox_core_relaunch_not_supported:{self.platform}")


def get_os_sandbox_provider(platform: str | None = None) -> BaseOsSandboxProvider:
    key = platform or sys.platform
    if key.startswith("linux"):
        return LinuxOsSandboxProvider()
    if key == "darwin":
        return MacOSOsSandboxProvider()
    if key == "win32":
        return WindowsOsSandboxProvider()
    return NoopOsSandboxProvider()


def get_helper_backend(platform: str | None = None):
    key = str(platform or sys.platform)
    if key.startswith("linux"):
        return LinuxHelperBackend()
    if key == "darwin":
        return MacOSHelperBackend()
    if key == "win32":
        return WindowsHelperBackend()
    return PortableHelperBackend(platform=key or "portable")


def get_core_launch_strategy(platform: str | None = None):
    key = str(platform or sys.platform)
    if key.startswith("linux"):
        return LinuxCoreLaunchStrategy()
    if key == "darwin":
        return MacOSCoreLaunchStrategy()
    if key == "win32":
        return WindowsCoreLaunchStrategy()
    return PortableCoreLaunchStrategy(platform=key or "portable")
