from __future__ import annotations

from democrai.core.platform.utils.normalize import os_key


EXTRACTOR_RUNTIME_READ_PATHS_BY_OS = {
    "linux": ("/dev/null",),
    "darwin": ("/dev/null",),
    "win32": (),
}

EXTRACTOR_RUNTIME_CREATE_PATHS_BY_OS = {
    "linux": (),
    "darwin": (),
    "win32": (),
}

EXTRACTOR_RUNTIME_MODIFY_PATHS_BY_OS = {
    "linux": ("/dev/null",),
    "darwin": ("/dev/null",),
    "win32": (),
}


def extractor_runtime_read_paths() -> tuple[str, ...]:
    return EXTRACTOR_RUNTIME_READ_PATHS_BY_OS.get(os_key(), ())


def extractor_runtime_create_paths() -> tuple[str, ...]:
    return EXTRACTOR_RUNTIME_CREATE_PATHS_BY_OS.get(os_key(), ())


def extractor_runtime_modify_paths() -> tuple[str, ...]:
    return EXTRACTOR_RUNTIME_MODIFY_PATHS_BY_OS.get(os_key(), ())
