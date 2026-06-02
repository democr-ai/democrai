from __future__ import annotations

import os
from pathlib import Path

from democrai.core.application.ai.engine.access_constants import (
    ENGINE_RUNTIME_DRIVER_LIBRARY_DIR_NAME,
    ENGINE_RUNTIME_TOOLCHAIN_BIN_DIR_NAME,
    engine_runtime_c_compiler_candidate_paths,
    engine_runtime_compiler_internal_program_names,
    engine_runtime_engine_env_executable_relative_paths,
    engine_runtime_libcuda_candidate_paths,
    engine_runtime_toolchain_program_candidate_paths,
    os_key,
)
from democrai.core.runtime.dependencies.engine_env import get_engine_local_env_path


def _first_existing_real_path(paths: tuple[str, ...]) -> Path | None:
    for raw_path in paths:
        candidate = Path(str(raw_path or "").strip())
        if not str(candidate):
            continue
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _real_path_targets(*paths: Path) -> tuple[Path, ...]:
    targets: list[Path] = []
    for path in paths:
        for raw_target in (path, Path(os.path.realpath(str(path)))):
            if raw_target not in targets:
                targets.append(raw_target)
    return tuple(targets)


def _gcc_internal_program_paths(
    compiler_path: Path,
    program_names: tuple[str, ...],
) -> dict[str, Path]:
    compiler_name = compiler_path.name
    if "-gcc-" not in compiler_name:
        return {}
    triple, _, version = compiler_name.rpartition("-gcc-")
    if not triple or not version:
        return {}
    roots = (
        Path("/usr/libexec/gcc") / triple / version,
        Path("/usr/lib/gcc") / triple / version,
    )
    resolved: dict[str, Path] = {}
    for program_name in program_names:
        for root in roots:
            candidate = root / program_name
            try:
                if candidate.exists():
                    resolved[program_name] = candidate.resolve()
                    break
            except OSError:
                continue
    return resolved


def ensure_engine_runtime_driver_libs(engine_id: str) -> tuple[Path | None, tuple[Path, ...]]:
    if os_key() != "linux":
        return None, ()
    libcuda_path = _first_existing_real_path(engine_runtime_libcuda_candidate_paths())
    if libcuda_path is None:
        return None, ()
    driver_lib_path = (
        get_engine_local_env_path(engine_id).resolve()
        / ENGINE_RUNTIME_DRIVER_LIBRARY_DIR_NAME
    )
    driver_lib_path.mkdir(parents=True, exist_ok=True)
    for link_name in ("libcuda.so.1", "libcuda.so"):
        link_path = driver_lib_path / link_name
        try:
            if link_path.exists() or link_path.is_symlink():
                if link_path.resolve() == libcuda_path:
                    continue
                if link_path.is_symlink():
                    link_path.unlink()
                else:
                    continue
            link_path.symlink_to(libcuda_path)
        except OSError:
            continue
    return driver_lib_path, _real_path_targets(libcuda_path)


def ensure_engine_runtime_toolchain(engine_id: str) -> tuple[Path | None, tuple[Path, ...]]:
    compiler_path = _first_existing_real_path(
        engine_runtime_c_compiler_candidate_paths()
    )
    if compiler_path is None:
        return None, ()
    toolchain_bin_path = (
        get_engine_local_env_path(engine_id).resolve()
        / ENGINE_RUNTIME_TOOLCHAIN_BIN_DIR_NAME
    )
    toolchain_bin_path.mkdir(parents=True, exist_ok=True)
    for stale_link_name in ("c++", "g++", "cc1plus"):
        stale_link_path = toolchain_bin_path / stale_link_name
        try:
            if stale_link_path.is_symlink():
                stale_link_path.unlink()
        except OSError:
            continue
    compiler_link_path = toolchain_bin_path / "cc"
    for link_name in ("cc", "gcc"):
        link_path = toolchain_bin_path / link_name
        try:
            if link_path.exists() or link_path.is_symlink():
                if link_path.resolve() != compiler_path and link_path.is_symlink():
                    link_path.unlink()
            if not link_path.exists() and not link_path.is_symlink():
                link_path.symlink_to(compiler_path)
        except OSError:
            continue
    if not compiler_link_path.exists() and not compiler_link_path.is_symlink():
        return None, ()
    target_paths = [compiler_path, compiler_link_path]
    for program_name, candidate_paths in engine_runtime_toolchain_program_candidate_paths().items():
        program_path = _first_existing_real_path(candidate_paths)
        if program_path is None:
            continue
        target_paths.append(program_path)
        link_path = toolchain_bin_path / program_name
        try:
            if link_path.exists() or link_path.is_symlink():
                if link_path.resolve() != program_path and link_path.is_symlink():
                    link_path.unlink()
            if not link_path.exists() and not link_path.is_symlink():
                link_path.symlink_to(program_path)
        except OSError:
            continue
    for program_name, program_path in _gcc_internal_program_paths(
        compiler_path,
        engine_runtime_compiler_internal_program_names(),
    ).items():
        target_paths.append(program_path)
        link_path = toolchain_bin_path / program_name
        try:
            if link_path.exists() or link_path.is_symlink():
                if link_path.resolve() != program_path and link_path.is_symlink():
                    link_path.unlink()
            if not link_path.exists() and not link_path.is_symlink():
                link_path.symlink_to(program_path)
        except OSError:
            continue
    return compiler_link_path, _real_path_targets(*target_paths)


def engine_runtime_engine_env_executable_paths(engine_id: str) -> tuple[Path, ...]:
    engine_env_path = get_engine_local_env_path(engine_id).resolve()
    targets: list[Path] = []
    for relative_path in engine_runtime_engine_env_executable_relative_paths():
        path = engine_env_path / relative_path
        try:
            if path.exists():
                targets.extend(_real_path_targets(path))
        except OSError:
            continue
    return tuple(dict.fromkeys(targets))

