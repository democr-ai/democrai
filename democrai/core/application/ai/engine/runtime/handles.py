from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
from democrai.core.application.ai.models.storage import normalize_model_storage_path
from democrai.core.infrastructure.storage.media.providers.base import MaterializedMedia
from democrai.core.runtime.dependencies.engine_env import get_engine_local_tmp_path
from democrai.core.runtime.foundation.app import app_ctx


@dataclass
class EngineHandle:
    engine_id: str
    config: dict[str, Any]
    subject: EngineWorkerSubject
    model_registry_id: int
    materialized_model_path: MaterializedMedia | Path | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def close(self) -> None:
        self.subject.close()
        if self.materialized_model_path is not None:
            self.materialized_model_path.cleanup()


def create_engine_handle(
    *,
    engine_id: str,
    config: dict[str, Any],
    model_registry_id: int,
) -> EngineHandle:
    if model_registry_id <= 0:
        raise ValueError("engine_runtime_model_registry_id_required")
    engine_config = dict(config)
    materialized_model_path = None
    raw_model_path = engine_config.get("model_path")
    if raw_model_path:
        media = getattr(app_ctx(), "media", None)
        if media is None:
            raise RuntimeError("Media storage unavailable")
        materialized_model_path = media.get_path(
            normalize_model_storage_path(raw_model_path),
            destination_dir=str(get_engine_local_tmp_path(engine_id)),
        )
        engine_config["model_path"] = _runtime_model_path(
            materialized_model_path.path,
            entrypoint=engine_config.get("runtime_entrypoint", ""),
        )
        engine_config["auxiliary_paths"] = _runtime_auxiliary_paths(
            materialized_model_path.path,
            artifacts=engine_config.get("artifacts"),
            auxiliary_artifacts=engine_config.get("auxiliary_artifacts"),
        )
    try:
        subject = EngineWorkerSubject(
            engine_id=engine_id,
            config=engine_config,
        )
    except Exception:
        if materialized_model_path is not None:
            materialized_model_path.cleanup()
        raise
    return EngineHandle(
        engine_id=engine_id,
        config=dict(config),
        subject=subject,
        model_registry_id=model_registry_id,
        materialized_model_path=materialized_model_path,
    )


def _runtime_model_path(materialized_path: str, *, entrypoint: str) -> str:
    if not entrypoint:
        return materialized_path

    root = Path(materialized_path)
    if not root.is_dir():
        raise ValueError("model_entrypoint_requires_directory")

    normalized_entrypoint = entrypoint.replace("\\", "/")
    candidate = (root / normalized_entrypoint).resolve()
    resolved_root = root.resolve()
    if candidate != resolved_root and resolved_root not in candidate.parents:
        raise ValueError("model_entrypoint_escapes_directory")
    if not candidate.is_file():
        raise FileNotFoundError(str(candidate))
    return str(candidate)


def _runtime_auxiliary_paths(
    materialized_path: str,
    *,
    artifacts: Any,
    auxiliary_artifacts: Any,
) -> dict[str, str]:
    if not isinstance(auxiliary_artifacts, dict) or not auxiliary_artifacts:
        return {}
    root = Path(materialized_path)
    if not root.is_dir():
        raise ValueError("auxiliary_artifacts_require_model_directory")
    if not isinstance(artifacts, list):
        raise ValueError("auxiliary_artifacts_require_artifacts")

    by_id = {
        item["id"]: item
        for item in artifacts
        if item.get("id")
    }
    resolved: dict[str, str] = {}
    resolved_root = root.resolve()
    for role, artifact_id in auxiliary_artifacts.items():
        resolved_role = role
        resolved_artifact_id = artifact_id
        if not resolved_role or not resolved_artifact_id:
            raise ValueError("invalid_auxiliary_artifact_mapping")
        artifact = by_id.get(resolved_artifact_id)
        if artifact is None:
            raise ValueError(f"auxiliary_artifact_not_found:{resolved_artifact_id}")
        target = artifact.get("target", "").replace("\\", "/")
        if target.startswith("models/"):
            target = target[len("models/") :]
        if not target:
            raise ValueError(f"auxiliary_artifact_target_missing:{resolved_artifact_id}")
        candidate = (root / target).resolve()
        if candidate != resolved_root and resolved_root not in candidate.parents:
            raise ValueError(f"auxiliary_artifact_target_escapes_directory:{resolved_artifact_id}")
        if not candidate.is_file():
            raise FileNotFoundError(str(candidate))
        resolved[resolved_role] = str(candidate)
    return resolved
