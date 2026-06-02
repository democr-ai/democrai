from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import (
    AIModelSource,
    methods_for_capabilities,
    runtime_config_schema_for_capabilities,
)

from modules.system.utils.actions.engine.models import sanitize_name
from modules.system.utils.actions.engine.model_test_support import DEFAULT_GENERATION


def build_binding_name(*, engine_id: int, available_name: str) -> str:
    return sanitize_name(f"engine_{engine_id}__{available_name}")


def build_binding_label(available_model: dict[str, Any]) -> str:
    return str(
        available_model.get("label")
        or available_model.get("name")
        or available_model.get("catalog_model_id")
        or "model"
    ).strip()


def _runtime_model_ref(available_model: dict[str, Any]) -> str:
    extra_config = (
        available_model.get("extra_config")
        if isinstance(available_model.get("extra_config"), dict)
        else {}
    )
    runtime_model_ref = str(extra_config.get("runtime_model_ref") or "").strip()
    return runtime_model_ref or str(available_model.get("name") or "").strip()


def _generation_defaults(source: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = source if isinstance(source, dict) else {}
    return {
        "temperature": defaults.get("temperature", 0.7),
        "top_p": defaults.get("top_p", 0.9),
        "top_k": defaults.get("top_k"),
        "max_tokens": defaults.get("max_tokens"),
    }


def _has_generation_config(capabilities: Any) -> bool:
    schema = runtime_config_schema_for_capabilities(capabilities)
    generation_schema = (
        schema.get("generation_schema")
        if isinstance(schema.get("generation_schema"), dict)
        else {}
    )
    return any(
        isinstance(field, dict) and str(field.get("name") or "").strip()
        for field in list(generation_schema.get("fields") or [])
    )


def _available_model_defaults(available_model: dict[str, Any]) -> dict[str, Any]:
    standard_schema = runtime_config_schema_for_capabilities(
        available_model.get("capabilities")
    )
    standard_defaults = (
        standard_schema.get("defaults")
        if isinstance(standard_schema.get("defaults"), dict)
        else {}
    )
    standard_generation = (
        standard_defaults.get("generation")
        if isinstance(standard_defaults.get("generation"), dict)
        else {}
    )
    standard_runtime = (
        standard_defaults.get("runtime")
        if isinstance(standard_defaults.get("runtime"), dict)
        else {}
    )
    extra_config = (
        available_model.get("extra_config")
        if isinstance(available_model.get("extra_config"), dict)
        else {}
    )
    defaults = (
        extra_config.get("defaults")
        if isinstance(extra_config.get("defaults"), dict)
        else {}
    )
    runtime = (
        defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    )
    generation = {}
    if _has_generation_config(available_model.get("capabilities")):
        generation = {
            **standard_generation,
            **(
                _generation_defaults(defaults.get("generation"))
                if isinstance(defaults.get("generation"), dict)
                else {}
            ),
        }
    return {
        "generation": generation,
        "runtime": {
            **standard_runtime,
            **runtime,
        },
    }


def binding_defaults_for_available_model(
    available_model: dict[str, Any],
    current: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = _available_model_defaults(available_model)
    existing = current if isinstance(current, dict) else {}
    existing_defaults = (
        existing.get("defaults") if isinstance(existing.get("defaults"), dict) else {}
    )
    existing_generation = (
        existing_defaults.get("generation")
        if isinstance(existing_defaults.get("generation"), dict)
        else {}
    )
    existing_runtime = (
        existing_defaults.get("runtime")
        if isinstance(existing_defaults.get("runtime"), dict)
        else {}
    )
    include_generation = _has_generation_config(available_model.get("capabilities"))
    generation_defaults = {}
    if include_generation:
        generation_defaults = {
            **base["generation"],
            **existing_generation,
        }
    return {
        "generation": generation_defaults,
        "runtime": {
            **base["runtime"],
            **existing_runtime,
        },
    }


def create_or_update_engine_binding(
    module_sdk,
    *,
    engine: dict[str, Any],
    available_model: dict[str, Any],
    defaults: dict[str, Any] | None = None,
    model_extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    engine_id = int(engine["id"])
    available_model_id = int(available_model["id"])
    binding_name = build_binding_name(
        engine_id=engine_id,
        available_name=str(available_model.get("name") or ""),
    )
    runtime_model_ref = _runtime_model_ref(available_model)
    model_path = str(available_model.get("storage_ref") or "").strip() or str(
        available_model.get("remote_url") or ""
    ).strip()
    existing_rows = (
        module_sdk.models.model_registry.all(
            filters={
                "engine_id": engine_id,
                "available_model_id": available_model_id,
            }
        ).get("rows")
        or []
    )
    existing_extra_config = (
        existing_rows[0].get("extra_config")
        if existing_rows and isinstance(existing_rows[0].get("extra_config"), dict)
        else {}
    )
    resolved_defaults = binding_defaults_for_available_model(
        available_model,
        existing_extra_config,
    )
    if isinstance(defaults, dict):
        submitted_generation = (
            defaults.get("generation")
            if isinstance(defaults.get("generation"), dict)
            else {}
        )
        submitted_runtime = (
            defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
        )
        include_generation = _has_generation_config(available_model.get("capabilities"))
        generation_defaults = {}
        if include_generation:
            generation_defaults = {
                **resolved_defaults["generation"],
                **submitted_generation,
            }
        resolved_defaults = {
            "generation": generation_defaults,
            "runtime": {
                **resolved_defaults["runtime"],
                **submitted_runtime,
            },
        }
    available_extra_config = (
        available_model.get("extra_config")
        if isinstance(available_model.get("extra_config"), dict)
        else {}
    )
    options_schema = (
        available_extra_config.get("options_schema")
        if isinstance(available_extra_config.get("options_schema"), dict)
        else {}
    )
    features = (
        available_extra_config.get("features")
        if isinstance(available_extra_config.get("features"), dict)
        else {}
    )
    runtime_entrypoint = str(
        available_extra_config.get("runtime_entrypoint") or ""
    ).strip()
    auxiliary_artifacts = (
        available_extra_config.get("auxiliary_artifacts")
        if isinstance(available_extra_config.get("auxiliary_artifacts"), dict)
        else {}
    )
    extra_config = {
        **existing_extra_config,
        "binding_label": build_binding_label(available_model),
        "runtime_entrypoint": runtime_entrypoint,
        "runtime_model_ref": runtime_model_ref,
        "auxiliary_artifacts": auxiliary_artifacts,
        "defaults": resolved_defaults,
        "options_schema": options_schema,
        "features": features,
        "available_model": {
            "id": available_model_id,
            "name": str(available_model.get("name") or "").strip(),
            "label": build_binding_label(available_model),
            "format": str(available_model.get("format") or "").strip(),
            "source_kind": str(available_model.get("source_kind") or "").strip(),
            "features": features,
        },
    }
    if isinstance(model_extra_config, dict):
        extra_config.update(model_extra_config)
    payload = {
        "name": binding_name,
        "engine_id": engine_id,
        "available_model_id": available_model_id,
        "model_path": model_path,
        "remote_url": str(available_model.get("remote_url") or "").strip() or None,
        "version": str(available_model.get("version") or "").strip() or None,
        "capabilities": list(available_model.get("capabilities") or []),
        "status": "active",
        "is_downloaded": 1
        if str(available_model.get("storage_ref") or "").strip()
        else 0,
        "extra_config": extra_config,
    }
    if existing_rows:
        row_id = int(existing_rows[0]["id"])
        return module_sdk.models.model_registry.update(row_id, payload) or existing_rows[0]
    return module_sdk.models.model_registry.create(payload)


def create_or_update_remote_engine_binding(
    module_sdk,
    *,
    engine_id: int,
    model_id: str,
    model_label: str,
    source_kind: str,
    model_format: str,
    capabilities: list[str],
    defaults: dict[str, Any],
    runtime_model_ref: str | None = None,
    runtime_defaults: dict[str, Any] | None = None,
    runtime_options_schema: dict[str, Any] | None = None,
    features: dict[str, Any] | None = None,
    model_extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    binding_name = build_binding_name(engine_id=engine_id, available_name=model_id)
    resolved_runtime_model_ref = str(runtime_model_ref or "").strip() or model_id
    existing_rows = (
        module_sdk.models.model_registry.all(filters={"engine_id": engine_id}).get(
            "rows"
        )
        or []
    )
    existing_row = None
    for item in existing_rows:
        if str(item.get("name") or "").strip() == binding_name:
            existing_row = item
            break
    existing_extra_config = (
        existing_row.get("extra_config")
        if isinstance(existing_row, dict)
        and isinstance(existing_row.get("extra_config"), dict)
        else {}
    )
    existing_defaults = (
        existing_extra_config.get("defaults")
        if isinstance(existing_extra_config.get("defaults"), dict)
        else {}
    )
    existing_generation = (
        existing_defaults.get("generation")
        if isinstance(existing_defaults.get("generation"), dict)
        else {}
    )
    existing_runtime = (
        existing_defaults.get("runtime")
        if isinstance(existing_defaults.get("runtime"), dict)
        else {}
    )
    submitted_generation = (
        defaults.get("generation") if isinstance(defaults.get("generation"), dict) else {}
    )
    submitted_runtime = (
        defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    )
    catalog_runtime = runtime_defaults if isinstance(runtime_defaults, dict) else {}
    standard_schema = runtime_config_schema_for_capabilities(capabilities)
    standard_defaults = (
        standard_schema.get("defaults")
        if isinstance(standard_schema.get("defaults"), dict)
        else {}
    )
    standard_generation = (
        standard_defaults.get("generation")
        if isinstance(standard_defaults.get("generation"), dict)
        else {}
    )
    standard_runtime = (
        standard_defaults.get("runtime")
        if isinstance(standard_defaults.get("runtime"), dict)
        else {}
    )
    include_generation = _has_generation_config(capabilities)
    generation_defaults = {}
    if include_generation:
        generation_defaults = {
            **standard_generation,
            **existing_generation,
            **submitted_generation,
        }
    options_schema = (
        runtime_options_schema if isinstance(runtime_options_schema, dict) else {}
    )
    resolved_features = features if isinstance(features, dict) else {}
    available_runtime = {
        "model_ref": resolved_runtime_model_ref,
        "defaults": {"runtime": catalog_runtime},
        "options_schema": options_schema,
    }
    resolved_source_kind = str(source_kind or "").strip().lower()
    resolved_model_path = (
        None
        if resolved_source_kind in {AIModelSource.ENGINE_CATALOG, AIModelSource.PROVIDER_API}
        else model_id
    )
    extra_config = {
        **existing_extra_config,
        "binding_label": model_label,
        "runtime_model_ref": resolved_runtime_model_ref,
        "defaults": {
            "generation": generation_defaults,
            "runtime": {
                **standard_runtime,
                **catalog_runtime,
                **existing_runtime,
                **submitted_runtime,
            },
        },
        "options_schema": options_schema,
        "features": resolved_features,
        "available_model": {
            "id": None,
            "name": model_id,
            "label": model_label,
            "format": model_format,
            "source_kind": source_kind,
            "runtime": available_runtime,
            "features": resolved_features,
        },
    }
    if isinstance(model_extra_config, dict):
        extra_config.update(model_extra_config)
    payload = {
        "name": binding_name,
        "engine_id": engine_id,
        "model_path": resolved_model_path,
        "remote_url": None,
        "version": None,
        "capabilities": list(capabilities or []),
        "runtime_methods": methods_for_capabilities(capabilities),
        "status": "active",
        "is_downloaded": 0,
        "extra_config": extra_config,
    }
    if isinstance(existing_row, dict):
        return module_sdk.models.model_registry.update(int(existing_row["id"]), payload)
    return module_sdk.models.model_registry.create(payload)


def remote_engine_binding_defaults(
    module_sdk,
    *,
    engine_id: int,
    model_id: str,
) -> dict[str, Any]:
    binding_name = build_binding_name(engine_id=engine_id, available_name=model_id)
    existing_rows = (
        module_sdk.models.model_registry.all(filters={"engine_id": engine_id}).get(
            "rows"
        )
        or []
    )
    for item in existing_rows:
        if str(item.get("name") or "").strip() != binding_name:
            continue
        extra_config = (
            item.get("extra_config") if isinstance(item.get("extra_config"), dict) else {}
        )
        defaults = (
            extra_config.get("defaults")
            if isinstance(extra_config.get("defaults"), dict)
            else {}
        )
        if defaults:
            return defaults
        break
    return {"generation": dict(DEFAULT_GENERATION), "runtime": {}}
