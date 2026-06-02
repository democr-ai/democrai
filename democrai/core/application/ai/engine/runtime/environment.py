from __future__ import annotations

import json
import os
import hashlib
from pathlib import Path
from typing import Any

from democrai.core.application.ai.constants import AIModelSource, normalize_token
from democrai.core.application.ai.engine.access_constants import (
    ENGINE_RUNTIME_DRIVER_LIBRARY_DIR_NAME,
    ENGINE_RUNTIME_TOOLCHAIN_BIN_DIR_NAME,
    os_key,
)
from democrai.core.application.ai.engine.manifests import get_engine_manifest
from democrai.core.application.ai.engine.runtime.toolchain import (
    ensure_engine_runtime_driver_libs,
    ensure_engine_runtime_toolchain,
)
from democrai.core.platform.utils.system import get_resource_monitor
from democrai.core.runtime.dependencies.engine_env import (
    get_engine_local_cache_path,
    get_engine_local_config_path,
    get_engine_local_env_path,
)
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.paths import is_frozen
from democrai.core.runtime.foundation.app import app_ctx


def runtime_node_id() -> str:
    ctx = app_ctx()
    configured = str(getattr(ctx, "node_id", "") or "").strip()
    if configured:
        return configured
    cfg = getattr(ctx, "config", None)
    if cfg is not None:
        configured = str(cfg.get("network.node_id", "") or "").strip()
        if configured:
            ctx.node_id = configured
            return configured
    return ""


_CONFIG_PUBLIC_KEYS = {
    "model",
    "model_path",
    "model_revision",
    "base_url",
    "context_size",
    "context_length",
    "context_policy",
    "n_ctx",
    "max_model_len",
    "num_ctx",
    "n_gpu_layers",
    "llama_kwargs",
    "cpu_offload_gb",
    "gpu_memory_utilization",
    "gpu_util",
    "kv_cache_dtype",
    "cache_dtype",
    "kv_cache_memory_bytes",
    "kv_offloading_size",
    "kv_offloading_backend",
    "execution_provider",
    "provider_options",
    "session_options",
    "max_kv_size",
    "kv_bits",
    "kv_group_size",
    "quantized_kv_start",
    "batch_size",
    "temperature",
    "top_p",
    "top_k",
    "max_tokens",
    "device",
    "dtype",
    "quantization",
    "runtime_entrypoint",
}


def runtime_config_public(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if not key.startswith("_") and key in _CONFIG_PUBLIC_KEYS
    }


def runtime_config_fingerprint(config: dict[str, Any]) -> str:
    payload = json.dumps(runtime_config_public(config), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def runtime_config_signature(config: dict[str, Any]) -> str:
    return runtime_config_fingerprint(config)


def resource_snapshot() -> dict[str, int | bool]:
    try:
        resources = get_resource_monitor().get_resources()
    except Exception:
        resources = {}
    ram_total_mb = int(resources.get("ram_total_mb") or 0)
    ram_free_mb = int(resources.get("ram_free_mb") or 0)
    vram_total_mb = int(resources.get("vram_total_mb") or 0)
    vram_free_mb = int(resources.get("vram_free_mb") or 0)
    return {
        "ram_total_mb": ram_total_mb,
        "ram_free_mb": ram_free_mb,
        "ram_used_mb": max(0, ram_total_mb - ram_free_mb),
        "vram_total_mb": vram_total_mb,
        "vram_free_mb": vram_free_mb,
        "vram_used_mb": max(0, vram_total_mb - vram_free_mb),
        "has_nvidia_gpu": bool(resources.get("has_nvidia_gpu")),
    }


def engine_phase_section(engine_id: str, phase: str) -> dict[str, Any]:
    manifest = get_engine_manifest(engine_id) or {}
    section = manifest.get(phase)
    return section if isinstance(section, dict) else {}


def engine_path_tokens(engine_id: str) -> dict[str, str]:
    local_root = get_engine_local_env_path(engine_id).resolve()
    cache_root = get_engine_local_cache_path(engine_id).resolve()
    config_root = get_engine_local_config_path(engine_id).resolve()
    driver_lib_root = local_root / ENGINE_RUNTIME_DRIVER_LIBRARY_DIR_NAME
    toolchain_bin_root = local_root / ENGINE_RUNTIME_TOOLCHAIN_BIN_DIR_NAME
    return {
        "engine_env": str(local_root),
        "engine_cache": str(cache_root),
        "engine_config": str(config_root),
        "engine_bin": str(local_root / "bin"),
        "engine_driver_libs": str(driver_lib_root),
        "engine_toolchain_bin": str(toolchain_bin_root),
    }


def resolve_engine_template(value: Any, tokens: dict[str, str]) -> Any:
    if not isinstance(value, str):
        return value
    resolved = value
    for key, token_value in tokens.items():
        resolved = resolved.replace("{" + key + "}", token_value)
    return resolved


def _engine_phase_env(engine_id: str, phase: str) -> dict[str, str]:
    section = engine_phase_section(engine_id, phase).copy()
    raw_env = section.get("env")
    env: dict[str, Any] = raw_env if isinstance(raw_env, dict) else {}
    raw_env_by_os = section.get("env_by_os")
    if isinstance(raw_env_by_os, dict):
        os_env = raw_env_by_os.get(os_key())
        if isinstance(os_env, dict):
            env.update(os_env)
    tokens = engine_path_tokens(engine_id)
    return {
        key: resolve_engine_template(value, tokens)
        for key, value in env.items()
        if key
    }


def get_engine_runtime_env(engine_id: str) -> dict[str, str]:
    env = _engine_phase_env(engine_id, "runtime")
    driver_lib_path, _ = ensure_engine_runtime_driver_libs(engine_id)
    if driver_lib_path is not None:
        driver_lib_value = str(driver_lib_path)
        env.setdefault("TRITON_LIBCUDA_PATH", driver_lib_value)
        env.setdefault("LD_LIBRARY_PATH", driver_lib_value)
    compiler_path, compiler_targets = ensure_engine_runtime_toolchain(engine_id)
    if compiler_path is not None:
        compiler_target = compiler_targets[0] if compiler_targets else compiler_path
        env.setdefault("CC", str(compiler_target))
        toolchain_bin_value = str(compiler_path.parent)
        existing_path = env.get("PATH", "")
        tokens = engine_path_tokens(engine_id)
        default_path = os.pathsep.join(
            (
                toolchain_bin_value,
                tokens["engine_bin"],
                tokens["engine_env"],
            )
        )
        env["PATH"] = (
            default_path
            if not existing_path
            else os.pathsep.join((toolchain_bin_value, existing_path))
        )
    return env


def get_engine_install_env(engine_id: str) -> dict[str, str]:
    return _engine_phase_env(engine_id, "install")


def get_engine_allowed_subprocess_commands(engine_id: str, phase: str) -> list[str]:
    section = engine_phase_section(engine_id, phase)
    return [
        item
        for item in section.get("allowed_subprocess_commands", [])
        if item
    ]


def _engine_requires_bound_model(engine_id: str) -> bool:
    manifest = get_engine_manifest(engine_id) or {}
    provider = manifest.get("provider") if isinstance(manifest.get("provider"), dict) else {}
    return normalize_token(provider.get("model_source")) in {
        AIModelSource.ENGINE_CATALOG,
        AIModelSource.INVENTORY,
    }


def engine_phase_access_section(engine_id: str, phase: str) -> dict[str, Any]:
    section = engine_phase_section(engine_id, phase)
    tokens = engine_path_tokens(engine_id)
    access = [
        item
        for item in section.get("access", [])
    ]
    raw_access_by_os = section.get("access_by_os")
    if isinstance(raw_access_by_os, dict):
        os_access = raw_access_by_os.get(os_key())
        if isinstance(os_access, list):
                access.extend(os_access)
    resolved_access: list[dict[str, Any]] = []
    for item in access:
        resolved = item.copy()
        if "target" in resolved:
            resolved["target"] = resolve_engine_template(resolved["target"], tokens)
        resolved_access.append(resolved)
    section["access"] = resolved_access
    return section


def application_root() -> str:
    if is_frozen():
        return str(Path(get_base_dir()).resolve())
    return str(Path(get_base_dir()).resolve().parent)
