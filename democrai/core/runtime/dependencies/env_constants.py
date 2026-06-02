from __future__ import annotations

import os
import threading
from pathlib import Path

from democrai.core.platform.utils.normalize import os_key

ENVIRONMENT_CONTEXT_LOCK = threading.RLock()


LINUX_SYSTEM_COMMAND_PATHS = (
    "~/.local/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)

DARWIN_SYSTEM_COMMAND_PATHS = (
    "~/.local/bin",
    "/opt/homebrew/bin",
    "/opt/local/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
)

WINDOWS_SYSTEM_COMMAND_PATHS = (
    "C:\\Windows\\System32",
    "C:\\Windows",
)

LINUX_PIP_INSTALL_COMMAND_PATHS = (
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
    "~/.cargo/bin",
)

DARWIN_PIP_INSTALL_COMMAND_PATHS = (
    "/opt/homebrew/bin",
    "/opt/local/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
    "~/.cargo/bin",
)

WINDOWS_PIP_INSTALL_COMMAND_PATHS = WINDOWS_SYSTEM_COMMAND_PATHS

LINUX_ENGINE_RUNTIME_COMMAND_PATHS = (
    "{engine_env}/bin",
    "{engine_env}",
)

DARWIN_ENGINE_RUNTIME_COMMAND_PATHS = (
    "{engine_env}/bin",
    "{engine_env}",
)

WINDOWS_ENGINE_RUNTIME_COMMAND_PATHS = (
    "{engine_env}\\Scripts",
    "{engine_env}",
)


def _expand_path_template(raw: str, *, engine_env: str | None = None) -> str:
    value = raw.strip()
    if not value:
        return ""
    if engine_env is not None:
        value = value.replace("{engine_env}", str(engine_env))
    if value.startswith("~/"):
        return str(Path.home() / value[2:])
    return value


def command_path_from_entries(
    entries: tuple[str, ...],
    *,
    engine_env: str | None = None,
) -> str:
    resolved: list[str] = []
    seen: set[str] = set()
    for entry in entries:
        normalized = _expand_path_template(entry, engine_env=engine_env)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        resolved.append(normalized)
    return os.pathsep.join(resolved)


def system_command_path() -> str:
    entries = {
        "linux": LINUX_SYSTEM_COMMAND_PATHS,
        "darwin": DARWIN_SYSTEM_COMMAND_PATHS,
        "win32": WINDOWS_SYSTEM_COMMAND_PATHS,
    }.get(os_key(), ())
    return command_path_from_entries(entries)


def pip_install_command_path() -> str:
    entries = {
        "linux": LINUX_PIP_INSTALL_COMMAND_PATHS,
        "darwin": DARWIN_PIP_INSTALL_COMMAND_PATHS,
        "win32": WINDOWS_PIP_INSTALL_COMMAND_PATHS,
    }.get(os_key(), ())
    return command_path_from_entries(entries)


def engine_runtime_command_path(engine_env: str) -> str:
    entries = {
        "linux": LINUX_ENGINE_RUNTIME_COMMAND_PATHS,
        "darwin": DARWIN_ENGINE_RUNTIME_COMMAND_PATHS,
        "win32": WINDOWS_ENGINE_RUNTIME_COMMAND_PATHS,
    }.get(os_key(), ())
    return command_path_from_entries(entries, engine_env=engine_env)
