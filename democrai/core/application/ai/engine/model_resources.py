from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from democrai.core.application.ai.engine.runtime import resource_snapshot
from democrai.core.application.ai.models.storage import normalize_model_storage_path
from democrai.core.application.ai.orchestrator import model_orchestrator
from democrai.core.runtime.foundation.app import app_ctx


_MODEL_WEIGHT_SUFFIXES = (
    ".safetensors",
    ".bin",
    ".pt",
    ".pth",
    ".gguf",
)


def evaluate_model_registry_resources(
    model_registry_id: int,
    *,
    context_length: int,
    runtime_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    model = model_orchestrator.get_model_by_registry_id(model_registry_id)
    if model is None:
        raise ValueError(f"model_registry_row_not_found:{model_registry_id}")
    engine = getattr(model, "engine", None)
    provider_id = getattr(engine, "provider", "")
    if not provider_id:
        raise ValueError(f"model_registry_engine_not_found:{model_registry_id}")

    config = model_orchestrator.build_provider_config(model)
    config.update(
        {
            key: value
            for key, value in (runtime_overrides or {}).items()
            if value is not None
        }
    )
    model_orchestrator.apply_provider_runtime_aliases(provider_id, config)
    active_runtime = model_orchestrator.active_runtime_instance(
        provider_id=provider_id,
        config=config,
    )
    resources = resource_snapshot()
    ram_required_mb, declared_vram_mb = model_orchestrator.memory_requirements_mb(model)
    model_weight_vram_mb, model_weight_source, model_config = _inspect_model_files(model)
    kv_cache_mb, kv_cache_source = _estimated_kv_cache_mb(
        model_config,
        context_length,
    )
    model_vram_mb = max(declared_vram_mb, model_weight_vram_mb)
    vram_required_mb = model_vram_mb + kv_cache_mb
    effective_free_vram_mb = int(resources.get("vram_free_mb") or 0)
    if active_runtime is not None:
        effective_free_vram_mb += vram_required_mb

    ram_free_mb = int(resources.get("ram_free_mb") or 0)
    fits_ram = ram_required_mb <= 0 or ram_free_mb >= ram_required_mb
    fits_vram = vram_required_mb <= 0 or effective_free_vram_mb >= vram_required_mb
    return {
        "provider": provider_id,
        "engine_row_id": getattr(engine, "id", None),
        "model_registry_id": model.id,
        "model_name": getattr(model, "name", ""),
        "context_length": context_length,
        "ram_required_mb": ram_required_mb,
        "vram_required_mb": vram_required_mb,
        "model_vram_mb": model_vram_mb,
        "model_weight_vram_mb": model_weight_vram_mb,
        "model_weight_source": model_weight_source,
        "context_kv_cache_mb": kv_cache_mb,
        "context_kv_cache_source": kv_cache_source,
        "effective_free_vram_mb": effective_free_vram_mb,
        "active_runtime": active_runtime,
        "resources_before": resources,
        "fits": bool(fits_ram and fits_vram),
        "errors": [
            *([] if fits_ram else ["insufficient_ram"]),
            *([] if fits_vram else ["insufficient_vram"]),
        ],
    }


def _model_storage_ref(model: Any) -> str:
    available_model = getattr(model, "available_model", None)
    storage_ref = getattr(available_model, "storage_ref", "")
    if storage_ref:
        return storage_ref
    model_path = getattr(model, "model_path", "")
    return model_path if model_path.startswith("models/") else ""


def _inspect_model_files(model: Any) -> tuple[int, str, dict[str, Any]]:
    materialized = None
    try:
        storage_ref = _model_storage_ref(model)
        media = getattr(app_ctx(), "media", None)
        if storage_ref and media is not None:
            materialized = media.get_path(normalize_model_storage_path(storage_ref))
            weight_bytes, config = _inspect_path(Path(str(materialized.path)))
            source = "media_files" if weight_bytes else "missing_weight_files"
            return _bytes_to_mb(weight_bytes), source, config
        model_path = Path(str(getattr(model, "model_path", "") or "")).expanduser()
        weight_bytes, config = _inspect_path(model_path)
        source = "model_path" if weight_bytes else "missing_weight_files"
        return _bytes_to_mb(weight_bytes), source, config
    finally:
        if materialized is not None:
            materialized.cleanup()


def _inspect_path(path: Path) -> tuple[int, dict[str, Any]]:
    if path.is_file():
        weight = (
            path.stat().st_size
            if path.suffix.lower() in _MODEL_WEIGHT_SUFFIXES
            else 0
        )
        return weight, _read_config_path(path)
    if not path.is_dir():
        return 0, {}
    weight = 0
    for candidate in path.rglob("*"):
        if candidate.is_file() and candidate.suffix.lower() in _MODEL_WEIGHT_SUFFIXES:
            weight += candidate.stat().st_size
    return weight, _read_config_path(path)


def _read_config_path(path: Path) -> dict[str, Any]:
    config_path = path / "config.json" if path.is_dir() else path
    if config_path.name != "config.json" or not config_path.exists():
        return {}
    try:
        value = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _dtype_bytes(value: Any) -> int:
    text = str(value or "").strip().lower()
    if any(item in text for item in ("float32", "fp32")):
        return 4
    if any(item in text for item in ("int8", "float8", "fp8")):
        return 1
    return 2


def _estimated_kv_cache_mb(
    config: dict[str, Any],
    context_length: int,
) -> tuple[int, str]:
    try:
        layers = int(config.get("num_hidden_layers") or config.get("n_layer") or 0)
        hidden_size = int(config.get("hidden_size") or config.get("n_embd") or 0)
        attention_heads = int(
            config.get("num_attention_heads") or config.get("n_head") or 0
        )
        kv_heads = int(
            config.get("num_key_value_heads")
            or config.get("num_kv_heads")
            or attention_heads
        )
        if layers <= 0 or hidden_size <= 0 or attention_heads <= 0 or kv_heads <= 0:
            return 0, "missing_model_config"
        head_dim = int(config.get("head_dim") or (hidden_size / attention_heads))
        bytes_per_value = _dtype_bytes(config.get("torch_dtype") or config.get("dtype"))
        total_bytes = (
            2 * layers * kv_heads * head_dim * context_length * bytes_per_value
        )
        return int(total_bytes / (1024 * 1024)), "model_config"
    except Exception:
        return 0, "invalid_model_config"


def _bytes_to_mb(value: int) -> int:
    return int((value + 1024 * 1024 - 1) / (1024 * 1024))
