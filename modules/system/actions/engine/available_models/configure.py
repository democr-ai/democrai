from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import normalize_capabilities
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.actions.engine.available_models.forms import (
    _open_activation_drawer,
)
from modules.system.actions.engine.available_models.helpers import (
    _refresh_available_model_catalog_runtime,
)
from modules.system.utils.actions.engine.bindings import (
    binding_defaults_for_available_model,
    remote_engine_binding_defaults,
)
from modules.system.utils.ui.model.configuration_form import (
    model_configuration_form_model,
    model_extra_config_for_form,
)


def _runtime_payload_defaults(runtime: Any) -> dict[str, Any]:
    if not isinstance(runtime, dict):
        return {}
    defaults = runtime.get("defaults") if isinstance(runtime.get("defaults"), dict) else {}
    if isinstance(defaults.get("runtime"), dict):
        return defaults.get("runtime")
    if isinstance(defaults.get("generation"), dict):
        return {}
    return defaults


def _runtime_options_schema(runtime: Any) -> dict[str, Any]:
    if not isinstance(runtime, dict):
        return {}
    return (
        runtime.get("options_schema")
        if isinstance(runtime.get("options_schema"), dict)
        else {}
    )


def _runtime_model_ref(runtime: Any, model_id: str) -> str:
    if not isinstance(runtime, dict):
        return model_id
    return str(runtime.get("model_ref") or model_id).strip() or model_id


async def _provider_capability_option_fields(module_sdk, provider: str) -> dict[str, Any]:
    provider_definition = await module_sdk.engines.get_provider_definition(
        provider_id=provider
    )
    if not isinstance(provider_definition, dict):
        return {}
    fields = provider_definition.get("capability_option_fields")
    return fields if isinstance(fields, dict) else {}


@action("configure_available_model_for_engine")
@permission_required(["system.engine.model.manage"])
async def configure_available_model_for_engine(
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
        return module_sdk.effects.respond(module_sdk.effects.render())
    available_model = await _refresh_available_model_catalog_runtime(
        module_sdk,
        available_model,
    )

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
    defaults = binding_defaults_for_available_model(
        available_model, existing_extra_config
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
    return _open_activation_drawer(
        module_sdk,
        title=module_sdk.i18n.t(
            "system.engine.models.config.title",
            context={
                "model": str(
                    available_model.get("label") or available_model.get("name") or ""
                )
            },
        ),
        form_model=model_configuration_form_model(
            module_sdk,
            constants,
            capabilities=list(available_model.get("capabilities") or []),
            extra_config=model_extra_config_for_form(
                defaults=defaults,
                features=available_extra_config.get("features")
                if isinstance(available_extra_config.get("features"), dict)
                else {},
                options_schema=options_schema,
            ),
            capability_option_fields=await _provider_capability_option_fields(
                module_sdk,
                provider,
            ),
        ),
        action={
            "name": "system.activate_available_model_for_engine",
            "context": {
                "engine_id": engine_id,
                "available_model_id": available_model_id,
                "model_id": str(ctx["model_id"]).strip(),
                "items": ctx["items"],
                "engine_models_available_name_filter": ctx[
                    "engine_models_available_name_filter"
                ],
                "engine_models_available_capability_filter": ctx[
                    "engine_models_available_capability_filter"
                ],
            },
        },
    )


@action("configure_remote_engine_model_registration")
@permission_required(["system.engine.model.manage"])
async def configure_remote_engine_model_registration(
    ctx: dict[str, Any], session: dict, module_sdk
):
    engine_id = int(ctx["engine_id"])
    engine = module_sdk.models.engine_registry.view(engine_id)
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())
    model_id = str(ctx["model_id"]).strip()
    model_label = str(ctx["model_label"]).strip()
    provider = str(engine.get("provider") or "").strip().lower()
    if not provider or not model_id:
        return module_sdk.effects.respond(module_sdk.effects.render())

    constants = await module_sdk.engines.constants()
    valid_capabilities = constants.get("model_capabilities")
    if not isinstance(valid_capabilities, list):
        raise ValueError("sdk engines constants model_capabilities must be a list")

    return _open_activation_drawer(
        module_sdk,
        title=module_sdk.i18n.t(
            "system.engine.models.registration.title",
            context={"model": model_label},
        ),
        form_model=model_configuration_form_model(
            module_sdk,
            constants,
            capabilities=[],
            extra_config=model_extra_config_for_form(
                defaults={},
                features=ctx.get("features")
                if isinstance(ctx.get("features"), dict)
                else {},
                options_schema=_runtime_options_schema(
                    ctx.get("runtime") if isinstance(ctx.get("runtime"), dict) else {}
                ),
                runtime_model_ref=_runtime_model_ref(
                    ctx.get("runtime") if isinstance(ctx.get("runtime"), dict) else {},
                    model_id,
                ),
            ),
            capability_option_fields=await _provider_capability_option_fields(
                module_sdk,
                provider,
            ),
        ),
        submit_label=module_sdk.i18n.t("system.engine.models.registration.submit"),
        action={
            "name": "system.activate_registered_remote_engine_model",
            "context": {
                "engine_id": engine_id,
                "model_id": model_id,
                "model_label": model_label,
                "source_kind": str(ctx["source_kind"]).strip(),
                "format": str(ctx["format"]).strip(),
                "runtime": ctx.get("runtime") if isinstance(ctx.get("runtime"), dict) else {},
                "features": ctx.get("features")
                if isinstance(ctx.get("features"), dict)
                else {},
                "items": ctx["items"],
                "engine_models_available_name_filter": ctx[
                    "engine_models_available_name_filter"
                ],
                "engine_models_available_capability_filter": ctx[
                    "engine_models_available_capability_filter"
                ],
            },
        },
    )


@action("configure_remote_engine_model")
@permission_required(["system.engine.model.manage"])
async def configure_remote_engine_model(ctx: dict[str, Any], session: dict, module_sdk):
    engine_id = int(ctx["engine_id"])
    engine = module_sdk.models.engine_registry.view(engine_id)
    if not isinstance(engine, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())
    provider = str(engine.get("provider") or "").strip().lower()
    model_id = str(ctx["model_id"]).strip()
    model_label = str(ctx["model_label"]).strip()
    source_kind = str(ctx["source_kind"]).strip()
    model_format = str(ctx["format"]).strip()
    capabilities = normalize_capabilities(ctx["capabilities"])
    if not provider or not model_id:
        return module_sdk.effects.respond(module_sdk.effects.render())

    runtime = ctx.get("runtime") if isinstance(ctx.get("runtime"), dict) else {}
    runtime_defaults = _runtime_payload_defaults(runtime)
    existing_defaults = remote_engine_binding_defaults(
        module_sdk,
        engine_id=engine_id,
        model_id=model_id,
    )
    existing_runtime = (
        existing_defaults.get("runtime")
        if isinstance(existing_defaults.get("runtime"), dict)
        else {}
    )
    defaults = {
        "generation": existing_defaults.get("generation")
        if isinstance(existing_defaults.get("generation"), dict)
        else {},
        "runtime": {
            **runtime_defaults,
            **existing_runtime,
        },
    }
    options_schema = _runtime_options_schema(runtime)
    constants = await module_sdk.engines.constants()
    return _open_activation_drawer(
        module_sdk,
        title=module_sdk.i18n.t(
            "system.engine.models.config.title",
            context={"model": model_label},
        ),
        form_model=model_configuration_form_model(
            module_sdk,
            constants,
            capabilities=capabilities,
            extra_config=model_extra_config_for_form(
                defaults=defaults,
                features=ctx.get("features")
                if isinstance(ctx.get("features"), dict)
                else {},
                options_schema=options_schema,
                runtime_model_ref=_runtime_model_ref(runtime, model_id),
            ),
            capability_option_fields=await _provider_capability_option_fields(
                module_sdk,
                provider,
            ),
        ),
        action={
            "name": "system.activate_remote_engine_model",
            "context": {
                "engine_id": engine_id,
                "model_id": model_id,
                "model_label": model_label,
                "source_kind": source_kind,
                "format": model_format,
                "capabilities": capabilities,
                "runtime": runtime,
                "features": ctx.get("features")
                if isinstance(ctx.get("features"), dict)
                else {},
                "items": ctx["items"],
                "engine_models_available_name_filter": ctx[
                    "engine_models_available_name_filter"
                ],
                "engine_models_available_capability_filter": ctx[
                    "engine_models_available_capability_filter"
                ],
            },
        },
    )
