from __future__ import annotations

from democrai.core.platform.utils.normalize import os_key


MODULE_RUNTIME_READ_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}

MODULE_RUNTIME_CREATE_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}

MODULE_RUNTIME_MODIFY_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}


def module_runtime_read_paths() -> tuple[str, ...]:
    return MODULE_RUNTIME_READ_PATHS_BY_OS.get(os_key(), ())


def module_runtime_create_paths() -> tuple[str, ...]:
    return MODULE_RUNTIME_CREATE_PATHS_BY_OS.get(os_key(), ())


def module_runtime_modify_paths() -> tuple[str, ...]:
    return MODULE_RUNTIME_MODIFY_PATHS_BY_OS.get(os_key(), ())
