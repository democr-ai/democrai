from __future__ import annotations

from democrai.core.platform.utils.normalize import os_key

DEFAULT_ENGINE_INSTALL_RECEIVE_URLS = (
    "https://pypi.org",
    "https://files.pythonhosted.org",
    "https://download.pytorch.org",
    "https://download-r2.pytorch.org",
    "https://pypi.nvidia.com",
    "https://abetlen.github.io",
)

ENGINE_RUNTIME_DEVICE_READ_PATHS_BY_OS = {
    "linux": ("/dev/null",),
    "darwin": ("/dev/null",),
    "win32": (),
}

ENGINE_RUNTIME_DEVICE_MODIFY_PATHS_BY_OS = {
    "linux": ("/dev/null",),
    "darwin": ("/dev/null",),
    "win32": (),
}

ENGINE_RUNTIME_DRIVER_LIBRARY_DIR_NAME = "driver_libs"
ENGINE_RUNTIME_TOOLCHAIN_BIN_DIR_NAME = "toolchain/bin"

ENGINE_RUNTIME_LIBCUDA_CANDIDATE_PATHS_BY_OS = {
    "linux": (
        "/usr/lib/x86_64-linux-gnu/libcuda.so.1",
        "/usr/lib64/libcuda.so.1",
        "/usr/lib/wsl/lib/libcuda.so.1",
        "/usr/local/cuda/compat/libcuda.so.1",
    ),
    "darwin": (),
    "win32": (),
}

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
    return ENGINE_RUNTIME_DEVICE_READ_PATHS_BY_OS.get(os_key(), ())


def engine_runtime_device_modify_paths() -> tuple[str, ...]:
    return ENGINE_RUNTIME_DEVICE_MODIFY_PATHS_BY_OS.get(os_key(), ())


def engine_runtime_libcuda_candidate_paths() -> tuple[str, ...]:
    return ENGINE_RUNTIME_LIBCUDA_CANDIDATE_PATHS_BY_OS.get(os_key(), ())


def engine_runtime_c_compiler_candidate_paths() -> tuple[str, ...]:
    return ENGINE_RUNTIME_C_COMPILER_CANDIDATE_PATHS_BY_OS.get(os_key(), ())


def engine_runtime_toolchain_program_candidate_paths() -> dict[str, tuple[str, ...]]:
    return ENGINE_RUNTIME_TOOLCHAIN_PROGRAM_CANDIDATE_PATHS_BY_OS.get(os_key(), {})


def engine_runtime_compiler_internal_program_names() -> tuple[str, ...]:
    return ENGINE_RUNTIME_COMPILER_INTERNAL_PROGRAM_NAMES


def engine_runtime_engine_env_executable_relative_paths() -> tuple[str, ...]:
    return ENGINE_RUNTIME_ENGINE_ENV_EXECUTABLE_RELATIVE_PATHS
