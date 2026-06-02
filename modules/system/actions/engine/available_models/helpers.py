from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import (
    AI_CONTEXT_POLICIES,
    runtime_config_schema_for_capabilities,
)

from modules.system.utils.actions.engine.model_test_support import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TOP_P,
    _number_value,
    _optional_int_value,
    _runtime_field_by_name,
    _runtime_schema_value,
)
from modules.system.utils.actions.model.catalog import catalog_entry_by_id


EMBEDDING_INPUT_POLICY_KEY = "embedding_input_policy"


def _embedding_policy_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    policy: dict[str, Any] = {}
    for payload_key, policy_key in (
        ("embedding_document_prefix", "document_prefix"),
        ("embedding_query_prefix", "query_prefix"),
        ("embedding_default_purpose", "default_purpose"),
    ):
        if payload_key not in payload:
            continue
        value = str(payload.get(payload_key) or "")
        if policy_key == "default_purpose":
            value = value.strip()
        policy[policy_key] = value
    return policy


def _first_upload_storage_path(value: Any) -> str:
    item: dict[str, Any] = {}
    if isinstance(value, list) and value and isinstance(value[0], dict):
        item = dict(value[0])
    elif isinstance(value, dict):
        item = dict(value)
    return str(item.get("storage_path") or item.get("path") or "").strip()


def _positive_int(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("expected_positive_int") from None
    if result <= 0:
        raise ValueError("expected_positive_int")
    return result


def _defaults_from_payload(
    payload: dict[str, Any],
    *,
    generation_field_names: list[str] | None = None,
    runtime_field_names: list[str] | None = None,
    runtime_options_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generation: dict[str, Any] = {}
    if "temperature" in list(generation_field_names or []):
        generation["temperature"] = _number_value(
            payload.get("temperature"),
            DEFAULT_TEMPERATURE,
        )
    if "top_p" in list(generation_field_names or []):
        generation["top_p"] = _number_value(
            payload.get("top_p"),
            DEFAULT_TOP_P,
        )
    if "max_tokens" in list(generation_field_names or []):
        generation["max_tokens"] = _optional_int_value(payload.get("max_tokens"))
    runtime: dict[str, Any] = {}
    context_length = _optional_int_value(payload.get("context_length"))
    n_gpu_layers = _optional_int_value(payload.get("n_gpu_layers"))
    if context_length is not None:
        runtime["context_length"] = context_length
    context_policy = str(payload.get("context_policy") or "").strip()
    if context_policy:
        if context_policy not in set(AI_CONTEXT_POLICIES):
            raise ValueError("invalid_context_policy")
        runtime["context_policy"] = context_policy
    if n_gpu_layers is not None:
        runtime["n_gpu_layers"] = n_gpu_layers
    if "dim" in payload:
        runtime["dim"] = _positive_int(payload.get("dim"))
    for field_name in list(runtime_field_names or []):
        if field_name in payload:
            include_value, runtime_value = _runtime_schema_value(
                _runtime_field_by_name(runtime_options_schema or {}, field_name),
                payload.get(field_name),
            )
            if include_value:
                runtime[field_name] = runtime_value
    voice_clone_ref_audio = _first_upload_storage_path(runtime.get("voice_clone_ref_audio"))
    if voice_clone_ref_audio:
        runtime["voice_clone_ref_audio_storage_path"] = voice_clone_ref_audio
    embedding_policy = _embedding_policy_from_payload(payload)
    if embedding_policy:
        runtime[EMBEDDING_INPUT_POLICY_KEY] = embedding_policy
    return {"generation": generation, "runtime": runtime}


def _has_defaults_payload(
    payload: dict[str, Any],
    *,
    generation_field_names: list[str] | None = None,
    runtime_field_names: list[str] | None = None,
) -> bool:
    return any(
        key in payload
        for key in (
            *list(generation_field_names or []),
            "context_length",
            "context_policy",
            "n_gpu_layers",
            "dim",
            "embedding_document_prefix",
            "embedding_query_prefix",
            "embedding_default_purpose",
            *list(runtime_field_names or []),
        )
    )


def _merge_options_schema(
    standard_schema: dict[str, Any] | None,
    override_schema: dict[str, Any] | None,
) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    for schema in (standard_schema, override_schema):
        for field in list((schema or {}).get("fields") or []):
            if not isinstance(field, dict):
                continue
            name = str(field.get("name") or "").strip()
            if not name:
                continue
            fields[name] = dict(field)
    return {"fields": list(fields.values())}


async def _refresh_available_model_catalog_runtime(
    module_sdk,
    available_model: dict[str, Any],
) -> dict[str, Any]:
    catalog_id = str(available_model.get("catalog_model_id") or "").strip()
    if not catalog_id:
        return available_model
    entry = await catalog_entry_by_id(module_sdk, catalog_id)
    if not isinstance(entry, dict):
        return available_model
    runtime = entry.get("runtime") if isinstance(entry.get("runtime"), dict) else {}
    runtime_defaults = (
        runtime.get("defaults") if isinstance(runtime.get("defaults"), dict) else {}
    )
    options_schema = (
        runtime.get("options_schema")
        if isinstance(runtime.get("options_schema"), dict)
        else {}
    )
    features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
    capabilities = list(entry.get("capabilities") or [])
    interfaces = list(entry.get("interfaces") or [])
    if not runtime_defaults and not options_schema and not features and not capabilities:
        return available_model
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
    generation_defaults = (
        defaults.get("generation")
        if isinstance(defaults.get("generation"), dict)
        else standard_generation
    )
    runtime_default_values = (
        runtime_defaults.get("runtime")
        if isinstance(runtime_defaults.get("runtime"), dict)
        else (
            runtime_defaults
            if not isinstance(runtime_defaults.get("generation"), dict)
            else {}
        )
    )
    updated_extra_config = {
        **extra_config,
        "defaults": {
            "generation": generation_defaults,
            "runtime": {
                **standard_runtime,
                **runtime_default_values,
            },
        },
        "options_schema": _merge_options_schema(
            standard_schema.get("options_schema"),
            options_schema,
        ),
        "features": features,
    }
    update_payload: dict[str, Any] = {"extra_config": updated_extra_config}
    if capabilities:
        update_payload["capabilities"] = capabilities
    if interfaces:
        update_payload["interfaces"] = interfaces
    updated = module_sdk.models.available_model_registry.update(
        int(available_model["id"]),
        update_payload,
    )
    if isinstance(updated, dict):
        return updated
    return {**available_model, **update_payload}


def _has_capability(capabilities: Any, capability: str) -> bool:
    return capability in {
        str(item or "").strip().lower()
        for item in list(capabilities or [])
        if str(item or "").strip()
    }


def _activated_available_items(
    items: list[dict[str, Any]],
    *,
    model_id: str,
    model_row_id: int,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in items:
        current = dict(item)
        if str(current.get("model_id") or current.get("id") or "").strip() == model_id:
            current["activated"] = True
            current["model_row_id"] = model_row_id
            current["icon"] = "ric.checkbox-circle-line"
            current["icon_color"] = "#22C55E"
        resolved.append(current)
    return resolved
