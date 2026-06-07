from __future__ import annotations

import json
import os
import platform
import sys
from typing import Any

from democrai.core.platform.utils.debug import debug_engine_install_flow
from democrai.core.platform.utils.system import get_resource_monitor


RUNTIME_ENV_JSON_ENV = "DEMOCRAI_RUNTIME_ENV_JSON"


def get_gpu_info() -> dict:
    """Detect NVIDIA GPU and VRAM without spawning subprocesses."""
    try:
        resources = get_resource_monitor().get_resources()
        return {
            "has_nvidia": bool(resources.get("has_nvidia_gpu")),
            "vram_mb": int(resources.get("vram_total_mb") or 0),
            "nvidia_driver_version": str(resources.get("nvidia_driver_version") or ""),
            "cuda_driver_version": str(resources.get("cuda_driver_version") or ""),
        }
    except Exception:
        return {
            "has_nvidia": False,
            "vram_mb": 0,
            "nvidia_driver_version": "",
            "cuda_driver_version": "",
        }


def norm_arch(machine: str) -> str:
    m = machine.lower()
    if m in {"amd64", "x86_64"}:
        return "x86_64"
    if m in {"arm64", "aarch64"}:
        return "arm64"
    return m


def runtime_env() -> dict:
    pinned = _runtime_env_from_env()
    if pinned is not None:
        return pinned
    return {
        "os": platform.system().lower(),
        "arch": norm_arch(platform.machine()),
        "gpu": get_gpu_info(),
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
    }


def _runtime_env_from_env() -> dict[str, Any] | None:
    raw = str(os.environ.get(RUNTIME_ENV_JSON_ENV) or "").strip()
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return dict(payload)


def engine_support_status(
    engine_id: str,
    env: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from democrai.core.application.ai.engine.runtime import check_engine_supported_runtime

    resolved_engine_id = engine_id.strip().lower()
    if not resolved_engine_id:
        return {
            "engine_id": "",
            "supported": False,
            "reason": "engine_id is required",
        }

    effective_env = env if isinstance(env, dict) else runtime_env()
    debug_engine_install_flow(
        "engine_support_status.begin",
        engine_id=resolved_engine_id,
        env=effective_env,
    )
    try:
        payload = check_engine_supported_runtime(
            engine_id=resolved_engine_id,
            env=effective_env,
        )
    except RuntimeError as exc:
        if str(exc) == f"engine_runtime_class_not_found:{resolved_engine_id}":
            result = {
                "engine_id": resolved_engine_id,
                "supported": False,
                "reason": f"engine_class_not_found:{resolved_engine_id}",
            }
            debug_engine_install_flow(
                "engine_support_status.end",
                engine_id=resolved_engine_id,
                supported=False,
                reason=str(result["reason"]),
                source="runtime_missing_class",
            )
            return result
        raise
    if not isinstance(payload, dict):
        raise RuntimeError(f"engine_support_status_invalid:{resolved_engine_id}")
    result = {
        "engine_id": resolved_engine_id,
        "supported": bool(payload.get("supported")),
        "reason": str(payload.get("reason", "")).strip(),
    }
    debug_engine_install_flow(
        "engine_support_status.end",
        engine_id=resolved_engine_id,
        supported=bool(result.get("supported")),
        reason=str(result["reason"]),
        source="runtime_support_status",
    )
    return result


def is_engine_supported(engine_id: str, env: dict[str, Any] | None = None) -> bool:
    return bool(engine_support_status(engine_id, env).get("supported"))
