from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from democrai.core.application.ai.constants import AIModelProvisioningMode
from democrai.core.application.ai.engine.manifests import (
    get_engine_manifest,
    get_engine_roots,
)


_DEFAULT_SOURCE_MODES = (AIModelProvisioningMode.CATALOG,)
_SOURCE_MODES = {
    AIModelProvisioningMode.ARTIFACT,
    AIModelProvisioningMode.CATALOG,
    AIModelProvisioningMode.DEFINITION,
}


def _verify_engine_id(engine_id: str) -> str:
    if not engine_id:
        raise ValueError("engine_id is required")
    return engine_id


def _verify_model_id(model_id: str) -> str:
    if not model_id:
        raise ValueError("model_id is required")
    return model_id


def _verify_source_mode(source_mode: str) -> str:
    if not source_mode:
        raise ValueError("model_source_mode is required")
    return source_mode


def _engine_manifest(engine_id: str) -> dict[str, Any]:
    manifest = get_engine_manifest(_verify_engine_id(engine_id))
    if not isinstance(manifest, dict) or not manifest:
        raise ValueError(f"engine_manifest_not_found:{engine_id}")
    return manifest


def _engine_dir(engine_id: str) -> Path:
    resolved_engine_id = _verify_engine_id(engine_id)
    for root in get_engine_roots():
        candidate = root / resolved_engine_id
        if candidate.exists():
            return candidate
    roots = get_engine_roots()
    if roots:
        return roots[0] / resolved_engine_id
    raise ValueError("engine_roots_not_configured")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"json_file_not_found:{path}") from exc
    except Exception as exc:
        raise ValueError(f"invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid_json_object:{path}")
    return payload


def _models_config(engine_id: str) -> dict[str, Any]:
    manifest = _engine_manifest(engine_id)
    models = manifest.get("models")
    if models is None:
        return {}
    if not isinstance(models, dict):
        raise ValueError(f"invalid_engine_models_config:{engine_id}")
    return models


def _schema_path(engine_id: str, relative_path: str) -> Path:
    if not relative_path:
        raise ValueError(f"model_schema_not_configured:{engine_id}")
    return (_engine_dir(engine_id) / relative_path).resolve()


def engine_model_source_modes(engine_id: str) -> list[str]:
    models_cfg = _models_config(engine_id)
    source_modes = models_cfg.get("source_modes")
    if not isinstance(source_modes, list) or not source_modes:
        return list(_DEFAULT_SOURCE_MODES)
    modes: list[str] = []
    for item in source_modes:
        if item not in _SOURCE_MODES:
            raise ValueError(f"invalid_model_source_mode:{engine_id}")
        if item not in modes:
            modes.append(item)
    return modes or list(_DEFAULT_SOURCE_MODES)


def get_engine_model_management(engine_id: str) -> dict[str, Any]:
    models_cfg = _models_config(engine_id)
    custom_definition = models_cfg.get("custom_definition")
    artifact_upload = models_cfg.get("artifact_upload")
    if custom_definition is None:
        custom_definition = {}
    if artifact_upload is None:
        artifact_upload = {}
    if not isinstance(custom_definition, dict):
        raise ValueError(f"invalid_engine_custom_definition_config:{engine_id}")
    if not isinstance(artifact_upload, dict):
        raise ValueError(f"invalid_engine_artifact_upload_config:{engine_id}")
    return {
        "engine_id": _verify_engine_id(engine_id),
        "source_modes": engine_model_source_modes(engine_id),
        "custom_definition": custom_definition,
        "artifact_upload": artifact_upload,
    }


def get_engine_model_schema(engine_id: str, *, source_mode: str) -> dict[str, Any]:
    management = get_engine_model_management(engine_id)
    resolved_mode = _verify_source_mode(source_mode)
    if resolved_mode == AIModelProvisioningMode.DEFINITION:
        config = management.get("custom_definition")
    elif resolved_mode == AIModelProvisioningMode.ARTIFACT:
        config = management.get("artifact_upload")
    else:
        raise ValueError(f"unsupported_model_schema_mode:{resolved_mode}")
    if not isinstance(config, dict) or config.get("enabled") is not True:
        raise ValueError(f"model_schema_disabled:{engine_id}:{resolved_mode}")
    payload = _load_json(_schema_path(engine_id, config["schema"]))
    return payload


def _catalog_path(engine_id: str) -> Path | None:
    models_cfg = _models_config(engine_id)
    catalog_cfg = models_cfg.get("catalog")
    if not isinstance(catalog_cfg, dict) or catalog_cfg.get("enabled") is not True:
        return None
    raw_path = catalog_cfg.get("path")
    if not raw_path:
        return None
    return (_engine_dir(engine_id) / raw_path).resolve()


def _catalog_payload(engine_id: str) -> dict[str, Any]:
    path = _catalog_path(engine_id)
    if path is None:
        return {"engine_id": _verify_engine_id(engine_id), "models": []}
    payload = _load_json(path)
    payload_engine_id = payload.get("engine_id", engine_id)
    if payload_engine_id != _verify_engine_id(engine_id):
        raise ValueError(
            f"engine_model_catalog_mismatch:{engine_id}:{payload_engine_id}"
        )
    return payload


def _prepare_runtime_definition(
    engine_id: str,
    payload: dict[str, Any],
    *,
    source_mode: str,
) -> dict[str, Any]:
    resolved = copy.deepcopy(payload)
    resolved_engine_id = _verify_engine_id(engine_id)
    if "id" not in resolved:
        raise ValueError("model_id is required")
    resolved_model_id = _verify_model_id(resolved["id"])

    payload_engine_id = resolved.get("engine_id", resolved_engine_id)
    if payload_engine_id != resolved_engine_id:
        raise ValueError(
            f"engine_id mismatch: expected {resolved_engine_id}, got {payload_engine_id}"
        )

    resolved["id"] = resolved_model_id
    resolved["engine_id"] = resolved_engine_id
    resolved.setdefault("label", resolved_model_id)
    resolved.setdefault("capabilities", [])
    resolved.setdefault("extended_capabilities", [])
    resolved.setdefault("interfaces", [])
    resolved.setdefault("requirements", {})
    resolved.setdefault("artifacts", [])
    resolved.setdefault("runtime", {})
    resolved.setdefault("features", {})
    resolved.setdefault("metadata", {})
    provisioning = resolved.get("provisioning")
    if not isinstance(provisioning, dict):
        provisioning = {}
        resolved["provisioning"] = provisioning
    provisioning["mode"] = source_mode

    capabilities = resolved.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("model capabilities must be a list")
    interfaces = resolved.get("interfaces")
    if not isinstance(interfaces, list):
        raise ValueError("model interfaces must be a list")
    runtime = resolved.get("runtime")
    if not isinstance(runtime, dict):
        raise ValueError("model runtime must be an object")
    runtime.setdefault("execution_mode", "standard")
    return resolved


def list_engine_models(engine_id: str) -> list[dict[str, Any]]:
    payload = _catalog_payload(engine_id)
    models = payload.get("models")
    if not isinstance(models, list):
        raise ValueError(f"invalid_engine_model_catalog:{engine_id}")
    resolved: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            raise ValueError(f"invalid_engine_model_catalog_entry:{engine_id}")
        resolved.append(
            _prepare_runtime_definition(engine_id, item, source_mode=AIModelProvisioningMode.CATALOG)
        )
    return resolved


def get_engine_model(engine_id: str, model_id: str) -> dict[str, Any] | None:
    resolved_model_id = _verify_model_id(model_id)
    for item in list_engine_models(engine_id):
        if item["id"] == resolved_model_id:
            return item
    return None


def resolve_engine_model(
    engine_id: str,
    *,
    model_id: str | None = None,
    source_mode: str = AIModelProvisioningMode.CATALOG,
    definition: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_engine_id = _verify_engine_id(engine_id)
    allowed_source_modes = engine_model_source_modes(resolved_engine_id)
    resolved_source_mode = _verify_source_mode(source_mode)
    if resolved_source_mode not in allowed_source_modes:
        raise ValueError(
            f"unsupported_model_source_mode:{resolved_engine_id}:{resolved_source_mode}"
        )

    if resolved_source_mode == AIModelProvisioningMode.CATALOG:
        if model_id is None:
            raise ValueError("model_id is required for catalog resolution")
        resolved_model_id = _verify_model_id(model_id)
        item = get_engine_model(resolved_engine_id, resolved_model_id)
        if item is None:
            raise ValueError(
                f"engine_model_not_found:{resolved_engine_id}:{resolved_model_id}"
            )
        result = copy.deepcopy(item)
    elif resolved_source_mode == AIModelProvisioningMode.DEFINITION:
        if not isinstance(definition, dict) or not definition:
            raise ValueError("definition payload is required")
        result = _prepare_runtime_definition(
            resolved_engine_id,
            definition,
            source_mode=AIModelProvisioningMode.DEFINITION,
        )
    elif resolved_source_mode == AIModelProvisioningMode.ARTIFACT:
        base_payload = dict(definition) if isinstance(definition, dict) else {}
        artifact_payload = dict(artifact) if isinstance(artifact, dict) else {}
        uploaded_artifact = artifact_payload.get("uploaded_artifact")
        if uploaded_artifact is None:
            uploaded_artifact = artifact_payload or None
        if not isinstance(uploaded_artifact, dict) or not uploaded_artifact:
            raise ValueError("artifact payload is required")
        base_payload.setdefault(
            "id",
            _verify_model_id(model_id if model_id is not None else base_payload["id"]),
        )
        base_payload.setdefault("label", base_payload.get("id") or model_id or "artifact-model")
        base_payload.setdefault("capabilities", [])
        base_payload.setdefault("interfaces", [])
        base_payload.setdefault("runtime", {})
        base_payload.setdefault(
            "artifacts",
            [
                {
                    "id": "uploaded_artifact",
                    "kind": "model",
                    "required": True,
                    "source": dict(uploaded_artifact),
                }
            ],
        )
        runtime = base_payload.get("runtime")
        if isinstance(runtime, dict):
            runtime.setdefault("artifact_ref", "uploaded_artifact")
        result = _prepare_runtime_definition(
            resolved_engine_id,
            base_payload,
            source_mode=AIModelProvisioningMode.ARTIFACT,
        )
    else:
        raise ValueError(f"unsupported_model_source_mode:{resolved_source_mode}")

    result["source_mode"] = resolved_source_mode
    result["engine_manifest"] = _engine_manifest(resolved_engine_id)
    return result


__all__ = [
    "engine_model_source_modes",
    "get_engine_model_management",
    "get_engine_model_schema",
    "get_engine_model",
    "list_engine_models",
    "resolve_engine_model",
]
