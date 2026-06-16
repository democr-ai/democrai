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


def _windows_git_command_dirs() -> tuple[str, ...]:
    """Locate the Git executable directory on Windows.

    Git is needed to install ``git+<url>`` requirements (e.g. parler-tts), but on
    Windows it lives outside System32 (typically ``C:\\Program Files\\Git\\cmd``),
    so it is absent from the conservative pip PATH and uv reports "Git executable
    not found". On POSIX git already sits in ``/usr/bin`` (covered by the existing
    entries), so this is Windows-only. Probe the real PATH first, then the
    standard install roots.
    """
    import shutil

    dirs: list[str] = []
    found = shutil.which("git")
    if found:
        dirs.append(os.path.dirname(found))
    candidates: list[str] = []
    for env_var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        root = os.environ.get(env_var)
        if root:
            candidates.append(os.path.join(root, "Git", "cmd"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.append(os.path.join(local, "Programs", "Git", "cmd"))
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "git.exe")):
            dirs.append(candidate)
    seen: set[str] = set()
    ordered: list[str] = []
    for directory in dirs:
        if directory and directory not in seen:
            seen.add(directory)
            ordered.append(directory)
    return tuple(ordered)


def pip_install_command_path() -> str:
    key = os_key()
    entries = {
        "linux": LINUX_PIP_INSTALL_COMMAND_PATHS,
        "darwin": DARWIN_PIP_INSTALL_COMMAND_PATHS,
        "win32": WINDOWS_PIP_INSTALL_COMMAND_PATHS,
    }.get(key, ())
    if key == "win32":
        entries = (*entries, *_windows_git_command_dirs())
    return command_path_from_entries(entries)


def engine_runtime_command_path(engine_env: str) -> str:
    entries = {
        "linux": LINUX_ENGINE_RUNTIME_COMMAND_PATHS,
        "darwin": DARWIN_ENGINE_RUNTIME_COMMAND_PATHS,
        "win32": WINDOWS_ENGINE_RUNTIME_COMMAND_PATHS,
    }.get(os_key(), ())
    return command_path_from_entries(entries, engine_env=engine_env)
