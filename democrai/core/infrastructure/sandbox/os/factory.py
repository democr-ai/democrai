from __future__ import annotations

import sys

from democrai.core.infrastructure.sandbox.os.base import (
    BaseOsSandboxProvider,
    NoopOsSandboxProvider,
)
from democrai.core.infrastructure.sandbox.os.linux.provider import LinuxOsSandboxProvider
from democrai.core.infrastructure.sandbox.os.macos.provider import MacOSOsSandboxProvider
from democrai.core.infrastructure.sandbox.os.windows.provider import WindowsOsSandboxProvider


def get_os_sandbox_provider(platform: str | None = None) -> BaseOsSandboxProvider:
    key = platform or sys.platform
    if key.startswith("linux"):
        return LinuxOsSandboxProvider()
    if key == "darwin":
        return MacOSOsSandboxProvider()
    if key == "win32":
        return WindowsOsSandboxProvider()
    return NoopOsSandboxProvider()
