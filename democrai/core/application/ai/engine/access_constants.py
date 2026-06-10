from __future__ import annotations

from democrai.core.infrastructure.sandbox.platform_policy import (
    runtime_dependency_read_paths,
    system_probe_read_paths,
    toolchain_execute_paths,
    trusted_read_path_variants,
)
from democrai.core.infrastructure.sandbox.runtime_access_baseline import (
    RuntimeAccessBaseline,
)
from democrai.core.platform.utils.normalize import os_key

DEFAULT_ENGINE_INSTALL_RECEIVE_URLS = (
    "https://pypi.org",
    "https://files.pythonhosted.org",
    "https://download.pytorch.org",
    "https://download-r2.pytorch.org",
    "https://pypi.nvidia.com",
    "https://abetlen.github.io",
)

ENGINE_RUNTIME_DRIVER_LIBRARY_DIR_NAME = "driver_libs"
ENGINE_RUNTIME_TOOLCHAIN_BIN_DIR_NAME = "toolchain/bin"

ENGINE_RUNTIME_C_COMPILER_CANDIDATE_PATHS_BY_OS = {
    "linux": (
        "/usr/bin/cc",
        "/usr/bin/gcc",
        "/usr/local/bin/gcc",
        "/usr/bin/clang",
        "/usr/local/bin/clang",
    ),
    "darwin": (
        "/usr/bin/cc",
        "/usr/bin/clang",
        "/opt/homebrew/bin/clang",
        "/opt/local/bin/clang",
    ),
    "win32": (),
}

ENGINE_RUNTIME_TOOLCHAIN_PROGRAM_CANDIDATE_PATHS_BY_OS = {
    "linux": {
        "as": (
            "/usr/bin/as",
            "/usr/bin/x86_64-linux-gnu-as",
        ),
        "ld": (
            "/usr/bin/ld",
            "/usr/bin/x86_64-linux-gnu-ld",
        ),
    },
    "darwin": {
        "as": (
            "/usr/bin/as",
        ),
        "ld": (
            "/usr/bin/ld",
        ),
    },
    "win32": {},
}

ENGINE_RUNTIME_COMPILER_INTERNAL_PROGRAM_NAMES = (
    "cc1",
    "collect2",
)

ENGINE_RUNTIME_ENGINE_ENV_EXECUTABLE_RELATIVE_PATHS = (
    "triton/backends/nvidia/bin/ptxas",
    "triton/backends/nvidia/bin/ptxas-blackwell",
)

def engine_runtime_device_read_paths() -> tuple[str, ...]:
    return RuntimeAccessBaseline.gpu_device_read_paths(os_key())


def engine_runtime_device_modify_paths() -> tuple[str, ...]:
    return RuntimeAccessBaseline.gpu_device_modify_paths(os_key())


def engine_runtime_libcuda_candidate_paths() -> tuple[str, ...]:
    return RuntimeAccessBaseline.libcuda_candidate_paths(os_key())


def engine_runtime_dependency_read_paths() -> tuple[str, ...]:
    return trusted_read_path_variants(runtime_dependency_read_paths(os_key()))


def engine_runtime_system_probe_read_paths() -> tuple[str, ...]:
    return trusted_read_path_variants(system_probe_read_paths(os_key()))


def engine_runtime_c_compiler_candidate_paths() -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *ENGINE_RUNTIME_C_COMPILER_CANDIDATE_PATHS_BY_OS.get(os_key(), ()),
                *toolchain_execute_paths(os_key()),
            )
        )
    )


def engine_runtime_toolchain_program_candidate_paths() -> dict[str, tuple[str, ...]]:
    return ENGINE_RUNTIME_TOOLCHAIN_PROGRAM_CANDIDATE_PATHS_BY_OS.get(os_key(), {})


def engine_runtime_compiler_internal_program_names() -> tuple[str, ...]:
    return ENGINE_RUNTIME_COMPILER_INTERNAL_PROGRAM_NAMES


def engine_runtime_engine_env_executable_relative_paths() -> tuple[str, ...]:
    return ENGINE_RUNTIME_ENGINE_ENV_EXECUTABLE_RELATIVE_PATHS
