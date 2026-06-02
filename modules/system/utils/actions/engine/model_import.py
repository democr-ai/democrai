from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AIModelSource, AIModelSourceKind, normalize_token
from democrai.sdk.engines import list_provider_definitions

from modules.system.utils.actions.engine.model_test_support import _runtime_field_names
from modules.system.utils.actions.model.catalog import first_artifact, source_type


def provider_definition(provider: str) -> dict[str, Any]:
    normalized = str(provider or "").strip().lower()
    for item in list_provider_definitions() or []:
        if str(item.get("id") or "").strip().lower() == normalized:
            return dict(item)
    return {}


def provider_supports_inventory_import(provider: str) -> bool:
    definition = provider_definition(provider)
    return (
        normalize_token(definition.get("model_source"))
        == AIModelSource.INVENTORY
    )


def provider_model_formats(provider: str) -> list[str]:
    return [
        str(item or "").strip().lower()
        for item in list(provider_definition(provider).get("accepted_model_formats") or [])
        if str(item or "").strip()
    ]


def provider_model_capabilities(provider: str) -> list[str]:
    definition = provider_definition(provider)
    return [
        str(item or "").strip().lower()
        for item in list(
            definition.get("model_capabilities") or definition.get("capabilities") or []
        )
        if str(item or "").strip()
    ]


def provider_accept_extensions(provider: str) -> str:
    extensions = []
    for item in provider_model_formats(provider):
        value = item if item.startswith(".") else f".{item}"
        if value not in extensions:
            extensions.append(value)
    return ",".join(extensions)


async def engine_import_runtime_template(
    module_sdk,
    provider: str,
    *,
    source_kind: str = AIModelSourceKind.UPLOAD,
) -> dict[str, Any]:
    normalized = str(provider or "").strip().lower()
    if not normalized:
        return {}
    try:
        models = await module_sdk.engines.list_catalog_models(engine_id=normalized)
    except Exception:
        return {}
    for model in models:
        if not isinstance(model, dict):
            continue
        artifact = first_artifact(model)
        artifact_source = (
            artifact.get("source")
            if isinstance(artifact, dict) and isinstance(artifact.get("source"), dict)
            else {}
        )
        if source_kind == AIModelSourceKind.UPLOAD:
            if source_type(model) != "local_upload":
                continue
        elif str(artifact_source.get("type") or "").strip().lower() != source_kind:
            continue
        runtime = model.get("runtime") if isinstance(model.get("runtime"), dict) else {}
        return {
            "runtime": runtime,
            "features": model.get("features") if isinstance(model.get("features"), dict) else {},
            "requirements": model.get("requirements") if isinstance(model.get("requirements"), dict) else {},
        }
    return {}


def runtime_defaults(template: dict[str, Any]) -> dict[str, Any]:
    runtime = template.get("runtime") if isinstance(template.get("runtime"), dict) else {}
    defaults = runtime.get("defaults") if isinstance(runtime.get("defaults"), dict) else {}
    runtime_values = (
        defaults.get("runtime")
        if isinstance(defaults.get("runtime"), dict)
        else {
            key: value
            for key, value in defaults.items()
            if key not in {"generation", "runtime"}
        }
    )
    return runtime_values if isinstance(runtime_values, dict) else {}


def runtime_options_schema(template: dict[str, Any]) -> dict[str, Any]:
    runtime = template.get("runtime") if isinstance(template.get("runtime"), dict) else {}
    return (
        runtime.get("options_schema")
        if isinstance(runtime.get("options_schema"), dict)
        else {}
    )


def runtime_payload_from_form(
    payload: dict[str, Any],
    options_schema: dict[str, Any],
) -> dict[str, Any]:
    runtime: dict[str, Any] = {}
    for field_name in _runtime_field_names(options_schema):
        if field_name in payload:
            runtime[field_name] = payload.get(field_name)
    return runtime


def update_imported_model_for_engine(
    module_sdk,
    row: dict[str, Any],
    *,
    provider: str,
    template: dict[str, Any],
    submitted_runtime: dict[str, Any],
) -> dict[str, Any]:
    row_id = int(row["id"])
    normalized_provider = str(provider or "").strip().lower()
    extra_config = (
        row.get("extra_config") if isinstance(row.get("extra_config"), dict) else {}
    )
    defaults = (
        extra_config.get("defaults")
        if isinstance(extra_config.get("defaults"), dict)
        else {}
    )
    generation = (
        defaults.get("generation")
        if isinstance(defaults.get("generation"), dict)
        else {}
    )
    runtime = {
        **runtime_defaults(template),
        **(
            defaults.get("runtime")
            if isinstance(defaults.get("runtime"), dict)
            else {}
        ),
        **submitted_runtime,
    }
    source_payload = (
        row.get("source_payload")
        if isinstance(row.get("source_payload"), dict)
        else {}
    )
    compatible_engines = [
        str(item or "").strip().lower()
        for item in list(source_payload.get("compatible_engines") or [])
        if str(item or "").strip()
    ]
    if normalized_provider and normalized_provider not in compatible_engines:
        compatible_engines.append(normalized_provider)
    updated = module_sdk.models.available_model_registry.update(
        row_id,
        {
            "provider_hint": normalized_provider,
            "source_payload": {
                **source_payload,
                "compatible_engines": compatible_engines,
            },
            "extra_config": {
                **extra_config,
                "defaults": {
                    **defaults,
                    "generation": generation,
                    "runtime": runtime,
                },
                "options_schema": runtime_options_schema(template),
                "features": template.get("features")
                if isinstance(template.get("features"), dict)
                else {},
                "requirements": template.get("requirements")
                if isinstance(template.get("requirements"), dict)
                else {},
            },
        },
    )
    return updated if isinstance(updated, dict) else row
