from __future__ import annotations

from pathlib import Path

MODEL_STORAGE_ROOT = "models"


def normalize_model_storage_path(raw_path: str) -> str:
    path = raw_path.strip().replace("\\", "/")
    if not path:
        raise ValueError("Missing model path")

    if path.startswith("media/"):
        raise ValueError("Model paths must be stored under models/")
    if Path(path).is_absolute():
        raise ValueError("Model paths must be storage-relative")

    trimmed = path.lstrip("/")
    if trimmed.startswith(MODEL_STORAGE_ROOT + "/") or trimmed == MODEL_STORAGE_ROOT:
        storage_path = trimmed
    else:
        storage_path = f"{MODEL_STORAGE_ROOT}/{trimmed}"

    normalized_storage_path = storage_path.strip().strip("/")
    if not normalized_storage_path:
        raise ValueError("Missing model path")
    if not (
        normalized_storage_path == MODEL_STORAGE_ROOT
        or normalized_storage_path.startswith(MODEL_STORAGE_ROOT + "/")
    ):
        raise ValueError(f"Model path must stay under {MODEL_STORAGE_ROOT}/")
    return normalized_storage_path
