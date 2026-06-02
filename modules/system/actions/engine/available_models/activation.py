from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import (
    normalize_capabilities,
    runtime_config_schema_for_capabilities,
)
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.actions.engine.available_models.helpers import (
    _activated_available_items,
    _defaults_from_payload,
    _has_defaults_payload,
    _merge_options_schema,
    _refresh_available_model_catalog_runtime,
)
from modules.system.actions.engine.model_tests.configuration import (
    _feature_config,
)
from modules.system.utils.actions.engine.model_test_support import _runtime_field_names
from modules.system.utils.actions.model.catalog import compatible_with_engine
from modules.system.utils.actions.engine.bindings import (
    create_or_update_engine_binding,
    create_or_update_remote_engine_binding,
)
from modules.system.utils.ui.engine.available_models import (
    filter_available_items,
    model_filter_value,
)


def _deactivated_available_items(
    items: list[dict[str, Any]],
    *,
    model_row_id: int,
) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for item in items:
        current = dict(item)
        if current.get("model_row_id") == model_row_id:
            current["activated"] = False
            current["model_row_id"] = None
            current["icon"] = "ric.circle-line"
            current["icon_color"] = "#94A3B8"
        resolved.append(current)
    return resolved


def _runtime_model_ref(runtime: Any, model_id: str) -> str:
    if not isinstance(runtime, dict):
        return model_id
    return str(runtime.get("model_ref") or model_id).strip() or model_id


def _runtime_defaults(runtime: Any) -> dict[str, Any]:
    if not isinstance(runtime, dict):
        return {}
    defaults = (
        runtime.get("defaults") if isinstance(runtime.get("defaults"), dict) else {}
    )
    return defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}


def _runtime_options_schema(runtime: Any) -> dict[str, Any]:
    if not isinstance(runtime, dict):
        return {}
    return (
        runtime.get("options_schema")
        if isinstance(runtime.get("options_schema"), dict)
        else {}
    )


def _features_from_payload(
    *,
    payload: dict[str, Any],
    capabilities: list[str],
    feature_schemas: dict[str, Any],
) -> dict[str, Any]:
    return {
        capability: _feature_config(
            payload,
            capability,
            feature_schemas[capability],
        )
        for capability in capabilities
        if capability in feature_schemas
    }


def _defaults_payload_for_capabilities(
    payload: dict[str, Any],
    capabilities: list[str],
) -> dict[str, Any]:
    if "embedding" in capabilities:
        return payload
    filtered = dict(payload)
    for key in (
        "dim",
        "embedding_document_prefix",
        "embedding_query_prefix",
        "embedding_default_purpose",
    ):
        filtered.pop(key, None)
    return filtered


async def _validated_capabilities(module_sdk, value: Any) -> list[str]:
    constants = await module_sdk.engines.constants()
    valid_capabilities = constants.get("model_capabilities")
    if not isinstance(valid_capabilities, list):
        raise ValueError("sdk engines constants model_capabilities must be a list")
    valid_capability_set = {str(item) for item in valid_capabilities}
    capabilities = normalize_capabilities(value)
    if not capabilities or any(
        item not in valid_capability_set for item in capabilities
    ):
        return []
    return capabilities


@action("activate_available_model_for_engine")
@permission_required(["system.engine.model.manage"])
async def activate_available_model_for_engine(
    ctx: dict[str, Any], session: dict, module_sdk
):
    engine_id = int(ctx["engine_id"])
    engine = module_sdk.models.engine_registry.view(engine_id)
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())
    provider = str(engine.get("provider") or "").strip().lower()
    if not provider:
        return module_sdk.effects.respond(module_sdk.effects.render())

    available_model_id = int(ctx["available_model_id"])
    available_model = module_sdk.models.available_model_registry.view(
        available_model_id
    )
    if not isinstance(available_model, dict):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.engine.models.available.not_found"
                    ),
                },
            )
        )
    available_model = await _refresh_available_model_catalog_runtime(
        module_sdk,
        available_model,
    )

    provider_hint = str(available_model.get("provider_hint") or "").strip().lower()
    is_provider_model = bool(provider_hint) and provider_hint == provider
    source_payload = (
        available_model.get("source_payload")
        if isinstance(available_model.get("source_payload"), dict)
        else {}
    )
    explicit_engines = [
        str(item or "").strip().lower()
        for item in (source_payload.get("compatible_engines") or [])
        if str(item or "").strip()
    ]
    if not is_provider_model and not compatible_with_engine(
        provider,
        model_format=str(available_model.get("format") or ""),
        capabilities=list(available_model.get("capabilities") or []),
    ):
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.engine.models.available.incompatible"
                    ),
                },
            )
        )
    if explicit_engines and provider not in explicit_engines:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.engine.models.available.incompatible"
                    ),
                },
            )
        )

    payload = dict(ctx[str(ctx["form_id"])])
    capabilities = await _validated_capabilities(
        module_sdk, payload.get("capabilities")
    )
    if not capabilities:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.model.toast.invalid_capabilities"
                    ),
                },
            )
        )

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
    constants = await module_sdk.engines.constants()
    feature_schemas = (
        constants.get("model_feature_schemas")
        if isinstance(constants.get("model_feature_schemas"), dict)
        else {}
    )
    standard_schema = runtime_config_schema_for_capabilities(capabilities)
    generation_schema = (
        standard_schema.get("generation_schema")
        if isinstance(standard_schema.get("generation_schema"), dict)
        else {}
    )
    generation_fields = _runtime_field_names(generation_schema)
    runtime_options_schema = _merge_options_schema(
        standard_schema.get("options_schema"),
        options_schema,
    )
    runtime_fields = _runtime_field_names(runtime_options_schema)
    try:
        defaults_payload = _defaults_payload_for_capabilities(payload, capabilities)
        submitted_defaults = (
            _defaults_from_payload(
                defaults_payload,
                generation_field_names=generation_fields,
                runtime_field_names=runtime_fields,
                runtime_options_schema=runtime_options_schema,
            )
            if _has_defaults_payload(
                defaults_payload,
                generation_field_names=generation_fields,
                runtime_field_names=runtime_fields,
            )
            else None
        )
        features = _features_from_payload(
            payload=payload,
            capabilities=capabilities,
            feature_schemas=feature_schemas,
        )
    except ValueError:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.model.toast.invalid_model_configuration"
                    ),
                },
            )
        )
    available_model = {
        **available_model,
        "capabilities": capabilities,
        "extra_config": {
            **available_extra_config,
            "features": features,
            "options_schema": _merge_options_schema(
                standard_schema.get("options_schema"),
                options_schema,
            ),
        },
    }
    row = create_or_update_engine_binding(
        module_sdk,
        engine=engine,
        available_model=available_model,
        defaults=submitted_defaults,
    )
    model_id = str(ctx["model_id"]).strip()
    model_row_id = int(row["id"])
    items = _activated_available_items(
        ctx["items"],
        model_id=model_id,
        model_row_id=model_row_id,
    )
    name = model_filter_value(ctx, "engine_models_available_name_filter")
    capability = model_filter_value(ctx, "engine_models_available_capability_filter")
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": "drawer"}},
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_models_available/all": items,
                            "/engine_models_available/filtered": filter_available_items(
                                items,
                                name=name,
                                capability=capability,
                            ),
                            "/engine_models_available/filters/name": name,
                            "/engine_models_available/filters/capability": capability,
                        },
                    }
                },
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": module_sdk.i18n.t(
                    "system.engine.models.available.activated",
                    context={
                        "model": str(
                            available_model.get("label")
                            or available_model.get("name")
                            or ""
                        )
                    },
                ),
            },
        ),
    )


@action("activate_registered_remote_engine_model")
@permission_required(["system.engine.model.manage"])
async def activate_registered_remote_engine_model(
    ctx: dict[str, Any], session: dict, module_sdk
):
    engine_id = int(ctx["engine_id"])
    engine = module_sdk.models.engine_registry.view(engine_id)
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())
    provider = str(engine.get("provider") or "").strip().lower()
    model_id = str(ctx["model_id"]).strip()
    model_label = str(ctx["model_label"]).strip()
    source_kind = str(ctx["source_kind"]).strip()
    model_format = str(ctx["format"]).strip()
    if not provider or not model_id:
        return module_sdk.effects.respond(module_sdk.effects.render())

    payload = dict(ctx[str(ctx["form_id"])])
    capabilities = await _validated_capabilities(
        module_sdk, payload.get("capabilities")
    )
    if not capabilities:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.model.toast.invalid_capabilities"
                    ),
                },
            )
        )

    runtime = ctx.get("runtime") if isinstance(ctx.get("runtime"), dict) else {}
    runtime_options_schema = _runtime_options_schema(runtime)
    standard_schema = runtime_config_schema_for_capabilities(capabilities)
    generation_schema = (
        standard_schema.get("generation_schema")
        if isinstance(standard_schema.get("generation_schema"), dict)
        else {}
    )
    generation_fields = _runtime_field_names(generation_schema)
    merged_runtime_options_schema = _merge_options_schema(
        standard_schema.get("options_schema"),
        runtime_options_schema,
    )
    runtime_fields = _runtime_field_names(merged_runtime_options_schema)
    constants = await module_sdk.engines.constants()
    feature_schemas = (
        constants.get("model_feature_schemas")
        if isinstance(constants.get("model_feature_schemas"), dict)
        else {}
    )
    try:
        defaults_payload = _defaults_payload_for_capabilities(payload, capabilities)
        submitted_defaults = _defaults_from_payload(
            defaults_payload,
            generation_field_names=generation_fields,
            runtime_field_names=runtime_fields,
            runtime_options_schema=merged_runtime_options_schema,
        )
        features = _features_from_payload(
            payload=payload,
            capabilities=capabilities,
            feature_schemas=feature_schemas,
        )
    except ValueError:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.model.toast.invalid_model_configuration"
                    ),
                },
            )
        )
    saved_row = create_or_update_remote_engine_binding(
        module_sdk,
        engine_id=engine_id,
        model_id=model_id,
        model_label=model_label,
        source_kind=source_kind,
        model_format=model_format,
        capabilities=capabilities,
        defaults=submitted_defaults,
        runtime_model_ref=_runtime_model_ref(runtime, model_id),
        runtime_defaults=_runtime_defaults(runtime),
        runtime_options_schema=runtime_options_schema,
        features=features,
    )

    model_row_id = int(saved_row["id"])
    items = _activated_available_items(
        ctx["items"],
        model_id=model_id,
        model_row_id=model_row_id,
    )
    name = model_filter_value(ctx, "engine_models_available_name_filter")
    capability = model_filter_value(ctx, "engine_models_available_capability_filter")

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": "drawer"}},
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_models_available/all": items,
                            "/engine_models_available/filtered": filter_available_items(
                                items,
                                name=name,
                                capability=capability,
                            ),
                            "/engine_models_available/filters/name": name,
                            "/engine_models_available/filters/capability": capability,
                        },
                    }
                },
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": module_sdk.i18n.t(
                    "system.engine.models.available.activated",
                    context={"model": model_label},
                ),
            },
        ),
    )


@action("activate_remote_engine_model")
@permission_required(["system.engine.model.manage"])
async def activate_remote_engine_model(ctx: dict[str, Any], session: dict, module_sdk):
    engine_id = int(ctx["engine_id"])
    engine = module_sdk.models.engine_registry.view(engine_id)
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())
    provider = str(engine.get("provider") or "").strip().lower()
    model_id = str(ctx["model_id"]).strip()
    model_label = str(ctx["model_label"]).strip()
    source_kind = str(ctx["source_kind"]).strip()
    model_format = str(ctx["format"]).strip()
    if not provider or not model_id:
        return module_sdk.effects.respond(module_sdk.effects.render())

    payload = dict(ctx[str(ctx["form_id"])])
    capabilities = await _validated_capabilities(
        module_sdk, payload.get("capabilities")
    )
    if not capabilities:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.model.toast.invalid_capabilities"
                    ),
                },
            )
        )

    runtime = ctx.get("runtime") if isinstance(ctx.get("runtime"), dict) else {}
    runtime_options_schema = _runtime_options_schema(runtime)
    standard_schema = runtime_config_schema_for_capabilities(capabilities)
    generation_schema = (
        standard_schema.get("generation_schema")
        if isinstance(standard_schema.get("generation_schema"), dict)
        else {}
    )
    generation_fields = _runtime_field_names(generation_schema)
    merged_runtime_options_schema = _merge_options_schema(
        standard_schema.get("options_schema"),
        runtime_options_schema,
    )
    runtime_fields = _runtime_field_names(merged_runtime_options_schema)
    constants = await module_sdk.engines.constants()
    feature_schemas = (
        constants.get("model_feature_schemas")
        if isinstance(constants.get("model_feature_schemas"), dict)
        else {}
    )
    try:
        defaults_payload = _defaults_payload_for_capabilities(payload, capabilities)
        submitted_defaults = _defaults_from_payload(
            defaults_payload,
            generation_field_names=generation_fields,
            runtime_field_names=runtime_fields,
            runtime_options_schema=merged_runtime_options_schema,
        )
        features = _features_from_payload(
            payload=payload,
            capabilities=capabilities,
            feature_schemas=feature_schemas,
        )
    except ValueError as exc:
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.model.toast.invalid_model_configuration"
                    ),
                },
            )
        )
    saved_row = create_or_update_remote_engine_binding(
        module_sdk,
        engine_id=engine_id,
        model_id=model_id,
        model_label=model_label,
        source_kind=source_kind,
        model_format=model_format,
        capabilities=capabilities,
        defaults=submitted_defaults,
        runtime_model_ref=_runtime_model_ref(runtime, model_id),
        runtime_defaults=_runtime_defaults(runtime),
        runtime_options_schema=runtime_options_schema,
        features=features,
    )

    model_row_id = int(saved_row["id"])
    items = _activated_available_items(
        ctx["items"],
        model_id=model_id,
        model_row_id=model_row_id,
    )
    name = model_filter_value(ctx, "engine_models_available_name_filter")
    capability = model_filter_value(ctx, "engine_models_available_capability_filter")

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": "drawer"}},
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_models_available/all": items,
                            "/engine_models_available/filtered": filter_available_items(
                                items,
                                name=name,
                                capability=capability,
                            ),
                            "/engine_models_available/filters/name": name,
                            "/engine_models_available/filters/capability": capability,
                        },
                    }
                },
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": module_sdk.i18n.t(
                    "system.engine.models.available.activated",
                    context={"model": model_label},
                ),
            },
        ),
    )


@action("deactivate_engine_model")
@permission_required(["system.engine.model.manage"])
async def deactivate_engine_model(ctx: dict[str, Any], session: dict, module_sdk):
    row_id = int(ctx["model_row_id"])
    try:
        row = module_sdk.models.model_registry.view(row_id)
        if not isinstance(row, dict):
            raise ValueError("model_not_found")
        module_sdk.models.model_registry.update(row_id, {"status": "available"})
    except Exception as exc:
        module_sdk.system.log(
            f"[engine.available_models] deactivate failed model_row_id={row_id}: {exc}",
            "error",
        )
        return module_sdk.effects.respond(
            module_sdk.effects.notify(
                "toast",
                {
                    "level": "error",
                    "message": module_sdk.i18n.t(
                        "system.engine.models.available.deactivate_error"
                    ),
                },
            ),
            module_sdk.effects.render(),
        )

    items = _deactivated_available_items(
        ctx["items"],
        model_row_id=row_id,
    )
    name = model_filter_value(ctx, "engine_models_available_name_filter")
    capability = model_filter_value(ctx, "engine_models_available_capability_filter")
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_models_available/all": items,
                            "/engine_models_available/filtered": filter_available_items(
                                items,
                                name=name,
                                capability=capability,
                            ),
                            "/engine_models_available/filters/name": name,
                            "/engine_models_available/filters/capability": capability,
                        },
                    }
                }
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success",
                "message": module_sdk.i18n.t(
                    "system.engine.models.available.deactivated"
                ),
            },
        ),
    )
