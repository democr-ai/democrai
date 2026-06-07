from __future__ import annotations

import contextlib
import contextvars
import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

from democrai.core.runtime.dependencies.env_constants import ENVIRONMENT_CONTEXT_LOCK
from democrai.core.runtime.dependencies.env_constants import engine_runtime_command_path
from democrai.core.runtime.foundation.paths import data_dir


_current_engine_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_engine_id",
    default=None,
)
_current_engine_env: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "current_engine_env",
    default=None,
)

_ENGINE_LOCAL_PATH_OVERRIDES: dict[str, dict[str, Path]] = {}
_ENGINE_ENV_ROOT = data_dir() / "engine_env_cache"


_ENGINE_CACHE_ENV_KEYS = (
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "PATH",
    "PYTHONPATH",
    "TMPDIR",
    "TEMP",
    "TMP",
)

_ENGINE_SHIELDED_ENV_KEYS = (
    "ACCELERATE_CONFIG_FILE",
    "CUDA_CACHE_PATH",
    "CUDA_HOME",
    "CUDA_PATH",
    "HF_DATASETS_CACHE",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HUGGINGFACE_HUB_CACHE",
    "LMCACHE_CONFIG_FILE",
    "MPLCONFIGDIR",
    "TORCH_EXTENSIONS_DIR",
    "TORCH_HOME",
    "TRANSFORMERS_CACHE",
    "TRITON_CACHE_DIR",
    "ULTRALYTICS_CONFIG_DIR",
    "VLLM_CONFIG_ROOT",
    "VLLM_TUNED_CONFIG_FOLDER",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "YOLO_CONFIG_DIR",
)


def get_current_engine_id() -> str | None:
    current = _current_engine_id.get()
    if current is None:
        return None
    engine_id = current.strip().lower()
    return engine_id if engine_id else None


def _engine_cache_env(engine_id: str) -> dict[str, str]:
    local_root = get_engine_local_env_path(engine_id)
    venv_root = get_engine_venv_path(engine_id)
    cache_root = get_engine_local_cache_path(engine_id)
    config_root = get_engine_local_config_path(engine_id)
    tmp_root = get_engine_local_tmp_path(engine_id)
    return {
        "XDG_CACHE_HOME": str(cache_root / "xdg"),
        "XDG_CONFIG_HOME": str(config_root),
        "PATH": engine_runtime_command_path(str(venv_root)),
        "PYTHONPATH": "",
        "TMPDIR": str(tmp_root),
        "TEMP": str(tmp_root),
        "TMP": str(tmp_root),
    }


@contextlib.contextmanager
def engine_env_context(engine_id: str, env: dict[str, str] | None = None):
    if engine_id is None:
        resolved = None
    else:
        engine_id_text = engine_id.strip().lower()
        resolved = engine_id_text if engine_id_text else None
    previous_engine = _current_engine_id.get()
    token = _current_engine_id.set(resolved)
    inherited_env = None
    if env is None and resolved == previous_engine:
        inherited_env = _current_engine_env.get()
    stale_env = {}
    if resolved != previous_engine:
        current_env = _current_engine_env.get()
        if current_env is not None:
            stale_env = current_env
    env_source = inherited_env if inherited_env is not None else env
    if env_source is None:
        env_source = {}
    env_overrides = {
        str(key): str(value) for key, value in dict(env_source).items()
    }
    env_token = _current_engine_env.set(env_overrides)
    managed_keys = tuple(
        dict.fromkeys(
            (
                *_ENGINE_CACHE_ENV_KEYS,
                *_ENGINE_SHIELDED_ENV_KEYS,
                *env_overrides.keys(),
                *stale_env.keys(),
            )
        )
    )
    with ENVIRONMENT_CONTEXT_LOCK:
        previous_env = {key: os.environ.get(key) for key in managed_keys}
        previous_tempdir = tempfile.tempdir
        previous_sys_path = list(sys.path)
        previous_importer_cache = dict(sys.path_importer_cache)
        previous_modules = dict(sys.modules)
        if resolved:
            for key in managed_keys:
                os.environ.pop(key, None)
            effective_env = _engine_cache_env(resolved)
            effective_env.update(env_overrides)
            os.environ.update(effective_env)
            tempfile.tempdir = None
        try:
            yield
        finally:
            if resolved:
                _restore_modules_after_engine_context(
                    previous_modules,
                    get_engine_local_env_path(resolved),
                )
            tempfile.tempdir = previous_tempdir
            sys.path[:] = previous_sys_path
            sys.path_importer_cache.clear()
            sys.path_importer_cache.update(previous_importer_cache)
            importlib.invalidate_caches()
            for key, value in previous_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            _current_engine_env.reset(env_token)
            _current_engine_id.reset(token)


def get_engine_local_env_path(engine_id: str | None = None) -> Path:
    if engine_id is None:
        resolved = get_current_engine_id()
    else:
        engine_id_text = engine_id.strip().lower()
        resolved = engine_id_text if engine_id_text else None
    if not resolved:
        raise RuntimeError("engine_env_context_missing")
    override = _engine_path_override("env", resolved)
    if override is not None:
        return override
    path = _ENGINE_ENV_ROOT / resolved
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_engine_local_cache_path(engine_id: str | None = None) -> Path:
    override = _engine_path_override("cache", engine_id)
    if override is not None:
        return override
    path = get_engine_local_env_path(engine_id) / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_engine_local_config_path(engine_id: str | None = None) -> Path:
    override = _engine_path_override("config", engine_id)
    if override is not None:
        return override
    path = get_engine_local_env_path(engine_id) / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_engine_local_tmp_path(engine_id: str | None = None) -> Path:
    override = _engine_path_override("tmp", engine_id)
    if override is not None:
        return override
    path = get_engine_local_env_path(engine_id) / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_engine_venv_path(engine_id: str | None = None) -> Path:
    return get_engine_local_env_path(engine_id) / ".venv"


def get_engine_venv_python_path(engine_id: str | None = None) -> Path:
    venv = get_engine_venv_path(engine_id)
    if os.name == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def get_engine_venv_site_packages_path(engine_id: str | None = None) -> Path:
    venv = get_engine_venv_path(engine_id)
    if os.name == "nt":
        return venv / "Lib" / "site-packages"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    return venv / "lib" / version / "site-packages"


def set_engine_local_path_overrides(
    engine_id: str,
    *,
    env_path: str,
    cache_path: str,
    config_path: str,
    tmp_path: str,
) -> None:
    resolved = engine_id.strip().lower() if isinstance(engine_id, str) else ""
    if not resolved:
        raise RuntimeError("engine_env_context_missing")
    _ENGINE_LOCAL_PATH_OVERRIDES[resolved] = {
        "env": Path(env_path),
        "cache": Path(cache_path),
        "config": Path(config_path),
        "tmp": Path(tmp_path),
    }


def _engine_path_override(kind: str, engine_id: str | None) -> Path | None:
    if engine_id is None:
        resolved = get_current_engine_id()
    else:
        engine_id_text = engine_id.strip().lower()
        resolved = engine_id_text if engine_id_text else None
    if not resolved:
        return None
    values = _ENGINE_LOCAL_PATH_OVERRIDES.get(resolved)
    if not values:
        return None
    return values.get(kind)


def bootstrap_engine_env(engine_id: str | None = None) -> Path:
    lib_path = str(get_engine_venv_site_packages_path(engine_id))
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    return get_engine_venv_path(engine_id)


def activate_local_engine_env(engine_id: str | None = None) -> Path:
    lib_path = str(get_engine_venv_site_packages_path(engine_id))
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)
    return get_engine_venv_path(engine_id)


def isolate_engine_imports(engine_id: str | None = None) -> None:
    if engine_id is None:
        resolved = get_current_engine_id()
    else:
        engine_id_text = engine_id.strip().lower()
        resolved = engine_id_text if engine_id_text else None
    if not resolved:
        raise RuntimeError("engine_env_context_missing")
    local_root = get_engine_venv_site_packages_path(resolved)
    local_root_text = str(local_root)
    engine_cache_marker = f"{os.path.sep}engine_env_cache{os.path.sep}"
    current_marker = f"{engine_cache_marker}{resolved}{os.path.sep}"
    sys.path[:] = [
        path
        for path in sys.path
        if os.path.abspath(path) != os.path.abspath(local_root_text)
        and (
            engine_cache_marker not in os.path.abspath(path)
            or current_marker in os.path.abspath(path)
        )
    ]
    sys.path.insert(0, local_root_text)
    for name, module in list(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        resolved_origin = os.path.abspath(str(origin))
        if engine_cache_marker in resolved_origin and current_marker not in resolved_origin:
            sys.modules.pop(name, None)
            continue
        if (
            _local_engine_module_exists(local_root, name)
            and not _path_is_within(resolved_origin, local_root_text)
        ):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()


def _local_engine_module_exists(local_root: Path, module_name: str) -> bool:
    top_level = str(module_name or "").split(".", 1)[0]
    if not top_level:
        return False
    return (local_root / top_level).exists() or (
        local_root / f"{top_level}.py"
    ).exists()


def _path_is_within(path: str, root: str) -> bool:
    try:
        return os.path.commonpath(
            (os.path.abspath(path), os.path.abspath(root))
        ) == os.path.abspath(root)
    except Exception:
        return False


def _restore_modules_after_engine_context(
    previous_modules: dict[str, object],
    local_root: Path,
) -> None:
    local_root_text = str(local_root)
    affected_names: list[tuple[str, object]] = []
    for name, module in list(sys.modules.items()):
        if not _module_from_path(module, local_root_text):
            continue
        affected_names.append((name, module))
        previous = previous_modules.get(name)
        if previous is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = previous
    for name, module in sorted(affected_names, key=lambda item: item[0].count(".")):
        _restore_parent_module_attribute(name, module, previous_modules)
    importlib.invalidate_caches()


def _restore_parent_module_attribute(
    name: str,
    removed_module: object,
    previous_modules: dict[str, object],
) -> None:
    if "." not in name:
        return
    parent_name, attr_name = name.rsplit(".", 1)
    parent = sys.modules.get(parent_name)
    if parent is None:
        return
    previous = previous_modules.get(name)
    if previous is not None:
        setattr(parent, attr_name, previous)
        return
    if getattr(parent, attr_name, None) is removed_module:
        try:
            delattr(parent, attr_name)
        except Exception:
            pass


def _module_from_path(module: object, root: str) -> bool:
    origin = getattr(module, "__file__", None)
    if origin and _path_is_within(str(origin), root):
        return True
    locations = getattr(module, "__path__", None)
    if locations is None:
        return False
    try:
        return any(_path_is_within(str(path), root) for path in locations)
    except Exception:
        return False


def clear_local_engine_env(engine_id: str | None = None) -> None:
    target = get_engine_local_env_path(engine_id)
    if target.exists():
        shutil.rmtree(target)


def has_engine_env_context() -> bool:
    return get_current_engine_id() is not None
