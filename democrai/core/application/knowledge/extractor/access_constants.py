from __future__ import annotations

from democrai.core.infrastructure.sandbox.platform_policy import (
    runtime_dependency_read_paths,
    system_probe_read_paths,
    trusted_read_path_variants,
)
from democrai.core.platform.utils.normalize import os_key


# Package infrastructure every extractor install needs, mirroring
# DEFAULT_ENGINE_INSTALL_RECEIVE_URLS on the engine twin (pytorch ships its
# wheels from the download-r2 CDN mirror via redirect).
DEFAULT_EXTRACTOR_INSTALL_RECEIVE_URLS = (
    "https://pypi.org",
    "https://files.pythonhosted.org",
    "https://download.pytorch.org",
    "https://download-r2.pytorch.org",
)

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


def extractor_runtime_dependency_read_paths() -> tuple[str, ...]:
    return trusted_read_path_variants(runtime_dependency_read_paths(os_key()))


def extractor_runtime_system_probe_read_paths() -> tuple[str, ...]:
    return trusted_read_path_variants(system_probe_read_paths(os_key()))


def extractor_runtime_create_paths() -> tuple[str, ...]:
    return EXTRACTOR_RUNTIME_CREATE_PATHS_BY_OS.get(os_key(), ())


def extractor_runtime_modify_paths() -> tuple[str, ...]:
    return EXTRACTOR_RUNTIME_MODIFY_PATHS_BY_OS.get(os_key(), ())
