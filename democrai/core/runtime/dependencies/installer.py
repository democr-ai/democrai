from __future__ import annotations

import importlib
import importlib.machinery
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from democrai.core.platform.utils.normalize import normalize_bool
from democrai.core.platform.utils.system import get_resource_monitor
from democrai.core.runtime.dependencies.env_constants import pip_install_command_path
from democrai.core.runtime.foundation.paths import is_frozen as runtime_is_frozen
from democrai.core.runtime.dependencies.installer_state import (
    load_state as _load_state,
    save_state as _save_state,
)


def get_gpu_info() -> dict:
    """Detect NVIDIA GPU and VRAM without spawning subprocesses."""
    try:
        resources = get_resource_monitor().get_resources()
        return {
            "has_nvidia": bool(resources.get("has_nvidia_gpu")),
            "vram_mb": int(resources.get("vram_total_mb") or 0),
            "nvidia_driver_version": str(resources.get("nvidia_driver_version") or ""),
            "cuda_driver_version": str(resources.get("cuda_driver_version") or ""),
            "error": "",
        }
    except Exception:
        return {
            "has_nvidia": False,
            "vram_mb": 0,
            "nvidia_driver_version": "",
            "cuda_driver_version": "",
            "error": "Failed to detect GPU information",
        }


def _norm_arch(machine: str) -> str:
    m = machine.lower()
    if m in {"amd64", "x86_64"}:
        return "x86_64"
    if m in {"arm64", "aarch64"}:
        return "arm64"
    return m


def _runtime_env() -> dict:
    return {
        "os": platform.system().lower(),  # linux, windows, darwin
        "arch": _norm_arch(platform.machine()),
        "gpu": get_gpu_info(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def get_target_dir() -> Path:
    from democrai.core.runtime.dependencies.engine_env import (
        get_engine_local_env_path,
        has_engine_env_context,
    )
    from democrai.core.runtime.dependencies.extractor_env import (
        get_extractor_local_env_path,
        has_extractor_env_context,
    )
    from democrai.core.runtime.foundation.paths import data_dir

    if has_extractor_env_context():
        target = get_extractor_local_env_path()
    elif has_engine_env_context():
        target = get_engine_local_env_path()
    else:
        target = data_dir() / "dependency_env"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _install_into_current_env() -> bool:
    from democrai.core.runtime.dependencies.engine_env import has_engine_env_context
    from democrai.core.runtime.dependencies.extractor_env import (
        has_extractor_env_context,
    )

    if has_engine_env_context() or has_extractor_env_context():
        return False
    # Dev default: install into active interpreter environment (same as manual pip).
    # Frozen/build default: install into dependency_env target.
    if runtime_is_frozen():
        return False
    raw = os.environ.get("DEMOCRAI_INSTALL_IN_CURRENT_ENV")
    if raw is None or str(raw).strip() == "":
        return True
    return normalize_bool(raw, default=True)


def run_pip_subprocess(args: List[str], *, env: dict[str, str] | None = None) -> None:
    """Run pip via subprocess using the current interpreter (dev mode)."""
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-input",
        "--prefer-binary",
    ] + args
    install_env = dict(os.environ)
    if env:
        install_env.update(env)
    _run_install_subprocess(
        cmd,
        label=f"[Installer] pip (subprocess) {' '.join(args)}",
        env=install_env,
    )


def run_pip_internal(
    args: List[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> None:
    """Run pip in target-install mode for dev and frozen runtimes."""
    if runtime_is_frozen():
        cmd = [
            sys.executable,
            "--pip-helper",
            "install",
            "--no-input",
            "--prefer-binary",
            *args,
        ]
        log_label = "helper subprocess"
    else:
        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-input",
            "--prefer-binary",
            *args,
        ]
        log_label = "subprocess"
    install_env = dict(os.environ)
    install_env["PATH"] = _sanitized_path_for_pip()
    install_env["NETRC"] = "/dev/null"
    install_env["PIP_CONFIG_FILE"] = "/dev/null"
    install_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    from democrai.core.runtime.dependencies.engine_env import has_engine_env_context
    from democrai.core.runtime.dependencies.extractor_env import (
        has_extractor_env_context,
    )

    if not has_engine_env_context() and not has_extractor_env_context():
        install_env["XDG_CONFIG_HOME"] = tempfile.gettempdir()
        install_env["XDG_CACHE_HOME"] = tempfile.gettempdir()
    if extra_env:
        install_env.update(extra_env)

    _run_install_subprocess(
        cmd,
        label=f"[Installer] pip ({log_label}) {' '.join(args)}",
        env=install_env,
    )


def _emit_install_output(
    line: str, *, phase: str = "install", stream: str = "stdout"
) -> None:
    try:
        from democrai.core.application.ai.engine.install_events import emit_engine_install_output

        emit_engine_install_output(line, phase=phase, stream=stream)
    except Exception:
        pass
    try:
        from democrai.core.application.knowledge.extractor.install_events import (
            emit_extractor_install_output,
        )

        emit_extractor_install_output(line, phase=phase, stream=stream)
    except Exception:
        pass


def _run_install_subprocess(
    cmd: list[str],
    *,
    label: str,
    env: dict[str, str] | None = None,
) -> None:
    print(label, flush=True)
    _emit_install_output(label, phase="install", stream="stdout")
    process = subprocess.Popen(  # nosec B603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    assert process.stdout is not None
    try:
        for line in process.stdout:
            text = str(line or "").rstrip()
            if not text:
                continue
            print(text, flush=True)
            _emit_install_output(text, phase="install", stream="stdout")
    finally:
        process.stdout.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"pip failed with exit code {return_code}")


def _sanitized_path_for_pip() -> str:
    """Return a conservative PATH for pip to avoid sandbox-denied lookups."""
    return pip_install_command_path()


@dataclass
class InstallPlan:
    packages: List[str]
    index_url: Optional[str] = None
    extra_index_url: Optional[str] = None
    allow_source: bool = False
    extra_pip_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    clean_target: bool = False


def _import_any(modules: List[str], *, search_path: Path | None = None) -> bool:
    """Fast spec check used for cache-hit detection (no code execution)."""
    paths = [str(search_path)] if search_path is not None else None
    for m in modules:
        if paths is None:
            found = importlib.util.find_spec(m)
        else:
            found = _find_spec_in_path(str(m), paths)
        if found:
            return True
    return False


def _find_spec_in_path(module_name: str, paths: list[str]):
    current_paths = paths
    current_name = ""
    found = None
    for part in module_name.split("."):
        if not part:
            return None
        current_name = f"{current_name}.{part}" if current_name else part
        found = importlib.machinery.PathFinder.find_spec(current_name, current_paths)
        if found is None:
            return None
        locations = found.submodule_search_locations
        current_paths = list(locations or [])
    return found


def _verify_imports(modules: List[str]) -> tuple[bool, Optional[Exception]]:
    """Attempt actual import for post-install verification (catches native failures)."""
    last_exc: Optional[Exception] = None
    for m in modules:
        try:
            importlib.import_module(m)
            return True, None
        except Exception as e:
            last_exc = e
    return False, last_exc


def _normalize_items(values: List[str] | None) -> list[str]:
    resolved: list[str] = []
    for value in values or []:
        normalized = str(value or "").strip()
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return resolved


def _normalize_env(value: dict[str, str] | None) -> dict[str, str]:
    resolved: dict[str, str] = {}
    for key, current in dict(value or {}).items():
        name = str(key or "").strip()
        if not name:
            continue
        resolved[name] = str(current)
    return resolved


def _build_pip_args_for_plan(
    *, plan: InstallPlan, target: Path | None = None
) -> list[str]:
    pip_args: list[str] = []
    if target is not None:
        pip_args += ["--target", str(target), "--upgrade"]
    pip_args += ["--no-cache-dir"]
    if plan.allow_source:
        pip_args += ["--prefer-binary"]
    if plan.index_url:
        pip_args += ["--index-url", plan.index_url]
    if plan.extra_index_url:
        pip_args += ["--extra-index-url", plan.extra_index_url]
    pip_args += list(plan.extra_pip_args)
    pip_args += list(plan.packages)
    return pip_args


def install_dependencies(packages: List[str], force: bool = False) -> bool:
    return install_python_packages(packages, force=force)


def install_dependency(package: str, force: bool = False) -> bool:
    return install_dependencies([package], force)


def install_python_packages(
    packages: List[str],
    *,
    modules: List[str] | None = None,
    force: bool = False,
    index_url: str | None = None,
    extra_index_url: str | None = None,
    allow_source: bool = False,
    extra_pip_args: List[str] | None = None,
    env: dict[str, str] | None = None,
    clean_target: bool = False,
) -> bool:
    from democrai.core.runtime.dependencies.engine_env import has_engine_env_context
    from democrai.core.runtime.dependencies.extractor_env import (
        has_extractor_env_context,
    )

    resolved_packages = _normalize_items(packages)
    if not resolved_packages:
        return True

    resolved_modules = _normalize_items(modules)
    plan = InstallPlan(
        packages=resolved_packages,
        index_url=str(index_url or "").strip() or None,
        extra_index_url=str(extra_index_url or "").strip() or None,
        allow_source=allow_source,
        extra_pip_args=_normalize_items(extra_pip_args),
        env=_normalize_env(env),
        clean_target=clean_target,
    )

    if _install_into_current_env():
        run_pip_subprocess(_build_pip_args_for_plan(plan=plan), env=plan.env)
        importlib.invalidate_caches()
        if resolved_modules:
            ok, err = _verify_imports(resolved_modules)
            if not ok:
                raise RuntimeError(
                    f"package install completed but module import failed: {err}"
                )
        return True

    target = get_target_dir()
    if plan.clean_target:
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
    if str(target) not in sys.path:
        sys.path.insert(0, str(target))
    state = _load_state(target)
    deps_state = state.setdefault("deps", {})
    cache_key = "python_packages:" + "|".join(
        [
            *resolved_packages,
            f"index={plan.index_url or ''}",
            f"extra_index={plan.extra_index_url or ''}",
            f"allow_source={int(plan.allow_source)}",
            "pip_args=" + ",".join(plan.extra_pip_args),
            "env="
            + ",".join(f"{key}={value}" for key, value in sorted(plan.env.items())),
        ]
    )
    if (
        not force
        and deps_state.get(cache_key, {}).get("installed") is True
        and (
            not resolved_modules
            or _import_any(
                resolved_modules,
                search_path=target
                if has_engine_env_context() or has_extractor_env_context()
                else None,
            )
        )
    ):
        return True

    run_pip_internal(
        _build_pip_args_for_plan(plan=plan, target=target),
        extra_env=plan.env,
    )

    importlib.invalidate_caches()
    if str(target) not in sys.path:
        sys.path.insert(0, str(target))
    if (
        resolved_modules
        and not has_engine_env_context()
        and not has_extractor_env_context()
    ):
        ok, err = _verify_imports(resolved_modules)
        if not ok:
            raise RuntimeError(
                f"package install completed but module import failed: {err}"
            )

    env = _runtime_env()
    deps_state[cache_key] = {
        "installed": True,
        "packages": list(plan.packages),
        "env": {
            "os": env["os"],
            "arch": env["arch"],
            "gpu": env["gpu"],
            "python": env["python"],
        },
        "index_url": plan.index_url,
        "extra_index_url": plan.extra_index_url,
        "extra_pip_args": list(plan.extra_pip_args),
        "install_env": dict(plan.env),
    }
    _save_state(target, state)
    (target / ".success").touch()
    return True


def ensure_dependency_installed(
    module_name: str, *, dependency_key: Optional[str] = None
) -> bool:
    raise RuntimeError(
        "ensure_dependency_installed is no longer available; use the current engine install flow"
    )
