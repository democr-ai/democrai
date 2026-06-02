from __future__ import annotations

import contextlib
import contextvars
import importlib
import os
import sys
import tempfile
from pathlib import Path

from democrai.core.runtime.dependencies.env_constants import ENVIRONMENT_CONTEXT_LOCK
from democrai.core.runtime.dependencies.env_constants import engine_runtime_command_path
from democrai.core.runtime.foundation.paths import data_dir

_EXTRACTOR_ENV_ROOT = data_dir() / "extractor_env_cache"


_current_extractor_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_extractor_id",
    default=None,
)
_current_extractor_env: contextvars.ContextVar[dict[str, str] | None] = (
    contextvars.ContextVar(
        "current_extractor_env",
        default=None,
    )
)


_EXTRACTOR_CACHE_ENV_KEYS = (
    "DOCLING_ARTIFACTS_PATH",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HF_HUB_OFFLINE",
    "HUGGINGFACE_HUB_CACHE",
    "MODELSCOPE_CACHE",
    "MPLCONFIGDIR",
    "NETRC",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
    "PATH",
    "PYTHONPATH",
    "TESSDATA_PREFIX",
    "TORCH_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
)

_EXTRACTOR_SHIELDED_ENV_KEYS = (
    "DOCLING_ARTIFACTS_PATH",
    "HF_DATASETS_CACHE",
    "HF_HOME",
    "HF_HUB_CACHE",
    "HF_HUB_OFFLINE",
    "HUGGINGFACE_HUB_CACHE",
    "MODELSCOPE_CACHE",
    "MPLCONFIGDIR",
    "NETRC",
    "TESSDATA_PREFIX",
    "TORCH_HOME",
    "TRANSFORMERS_CACHE",
    "TRANSFORMERS_OFFLINE",
    "XDG_CACHE_HOME",
    "XDG_CONFIG_HOME",
)


def get_extractor_tessdata_path(extractor_id: str | None = None) -> Path:
    path = get_extractor_local_cache_path(extractor_id) / "tessdata"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extractor_docling_artifacts_path(extractor_id: str | None = None) -> Path:
    path = get_extractor_local_cache_path(extractor_id) / "docling" / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tessdata_prefix(extractor_id: str) -> str:
    return str(get_extractor_tessdata_path(extractor_id))


def get_current_extractor_id() -> str | None:
    current = _current_extractor_id.get()
    if current is None:
        return None
    extractor_id = current.strip().lower()
    return extractor_id if extractor_id else None


def _extractor_cache_env(extractor_id: str) -> dict[str, str]:
    local_root = get_extractor_local_env_path(extractor_id)
    cache_root = get_extractor_local_cache_path(extractor_id)
    config_root = get_extractor_local_config_path(extractor_id)
    tmp_root = get_extractor_local_tmp_path(extractor_id)
    env = {
        "HF_HOME": str(cache_root / "huggingface"),
        "DOCLING_ARTIFACTS_PATH": str(get_extractor_docling_artifacts_path(extractor_id)),
        "HF_HUB_CACHE": str(cache_root / "huggingface" / "hub"),
        "HUGGINGFACE_HUB_CACHE": str(cache_root / "huggingface" / "hub"),
        "MODELSCOPE_CACHE": str(cache_root / "modelscope"),
        "MPLCONFIGDIR": str(config_root / "matplotlib"),
        "NETRC": os.devnull,
        "XDG_CACHE_HOME": str(cache_root / "xdg"),
        "XDG_CONFIG_HOME": str(config_root),
        "PATH": engine_runtime_command_path(str(local_root)),
        "PYTHONPATH": str(local_root),
        "TORCH_HOME": str(cache_root / "torch"),
        "TMPDIR": str(tmp_root),
        "TEMP": str(tmp_root),
        "TMP": str(tmp_root),
    }
    tessdata_prefix = _tessdata_prefix(extractor_id)
    if tessdata_prefix:
        env["TESSDATA_PREFIX"] = tessdata_prefix
    return env


@contextlib.contextmanager
def extractor_env_context(extractor_id: str, env: dict[str, str] | None = None):
    if extractor_id is None:
        resolved = None
    else:
        extractor_id_text = extractor_id.strip().lower()
        resolved = extractor_id_text if extractor_id_text else None
    previous_extractor = _current_extractor_id.get()
    token = _current_extractor_id.set(resolved)
    inherited_env = None
    if env is None and resolved == previous_extractor:
        inherited_env = _current_extractor_env.get()
    stale_env = {}
    if resolved != previous_extractor:
        current_env = _current_extractor_env.get()
        if current_env is not None:
            stale_env = current_env
    env_source = inherited_env if inherited_env is not None else env
    if env_source is None:
        env_source = {}
    env_overrides = {
        str(key): str(value) for key, value in dict(env_source).items()
    }
    env_token = _current_extractor_env.set(env_overrides)
    managed_keys = tuple(
        dict.fromkeys(
            (
                *_EXTRACTOR_CACHE_ENV_KEYS,
                *_EXTRACTOR_SHIELDED_ENV_KEYS,
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
        if resolved:
            for key in managed_keys:
                os.environ.pop(key, None)
            effective_env = _extractor_cache_env(resolved)
            effective_env.update(env_overrides)
            os.environ.update(effective_env)
            tempfile.tempdir = None
        try:
            yield
        finally:
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
            _current_extractor_env.reset(env_token)
            _current_extractor_id.reset(token)


def get_extractor_local_env_path(extractor_id: str | None = None) -> Path:
    if extractor_id is None:
        resolved = get_current_extractor_id()
    else:
        extractor_id_text = extractor_id.strip().lower()
        resolved = extractor_id_text if extractor_id_text else None
    if not resolved:
        raise RuntimeError("extractor_env_context_missing")
    path = _EXTRACTOR_ENV_ROOT / resolved
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extractor_local_cache_path(extractor_id: str | None = None) -> Path:
    path = get_extractor_local_env_path(extractor_id) / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extractor_local_config_path(extractor_id: str | None = None) -> Path:
    path = get_extractor_local_env_path(extractor_id) / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_extractor_local_tmp_path(extractor_id: str | None = None) -> Path:
    path = get_extractor_local_env_path(extractor_id) / "tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def isolate_extractor_imports(extractor_id: str | None = None) -> None:
    if extractor_id is None:
        resolved = get_current_extractor_id()
    else:
        extractor_id_text = extractor_id.strip().lower()
        resolved = extractor_id_text if extractor_id_text else None
    if not resolved:
        raise RuntimeError("extractor_env_context_missing")
    local_root = get_extractor_local_env_path(resolved)
    local_root_text = str(local_root)
    extractor_cache_marker = f"{os.path.sep}extractor_env_cache{os.path.sep}"
    current_marker = f"{extractor_cache_marker}{resolved}{os.path.sep}"
    sys.path[:] = [
        path
        for path in sys.path
        if os.path.abspath(path) != os.path.abspath(local_root_text)
        and (
            extractor_cache_marker not in os.path.abspath(path)
            or current_marker in os.path.abspath(path)
        )
    ]
    sys.path.insert(0, local_root_text)
    for name, module in list(sys.modules.items()):
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        resolved_origin = os.path.abspath(str(origin))
        if (
            extractor_cache_marker in resolved_origin
            and current_marker not in resolved_origin
        ):
            sys.modules.pop(name, None)
    importlib.invalidate_caches()


def has_extractor_env_context() -> bool:
    return get_current_extractor_id() is not None
