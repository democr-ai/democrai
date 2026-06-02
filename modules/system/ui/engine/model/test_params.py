from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as sdk
from modules.system.utils.ui.model.configuration_form import (
    model_configuration_form_model,
)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _int(value: Any) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _runtime_defaults(row: dict[str, Any]) -> dict[str, Any]:
    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
    return _dict(defaults.get("runtime"))


def _context_length_value(runtime_defaults: dict[str, Any]) -> Any:
    for key in ("context_length", "n_ctx", "max_model_len", "num_ctx"):
        value = runtime_defaults.get(key)
        if value not in (None, ""):
            return value
    return None


def _context_policy_options(constants: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "label": sdk.i18n.t(f"system.engine.models.config.context_policy.{value}"),
            "value": str(value),
        }
        for value in list(constants.get("context_policies") or [])
        if str(value or "").strip()
    ]


def _context_policy_value(
    runtime_defaults: dict[str, Any],
    constants: dict[str, Any],
    *,
    deployment: str | None = None,
) -> str:
    value = str(runtime_defaults.get("context_policy") or "").strip()
    if value:
        return value
    defaults = _dict(constants.get("context_policy_defaults"))
    return str(defaults.get(str(deployment or "").strip().lower()) or "")


def _options_schema(row: dict[str, Any]) -> dict[str, Any]:
    extra_config = _dict(row.get("extra_config"))
    options_schema = _dict(extra_config.get("options_schema"))
    if options_schema:
        return options_schema
    available_model = _dict(extra_config.get("available_model"))
    runtime = _dict(available_model.get("runtime"))
    options_schema = _dict(runtime.get("options_schema"))
    if options_schema:
        return options_schema
    available_model_id = row.get("available_model_id")
    if available_model_id in (None, ""):
        return {}
    available_row = sdk.models.available_model_registry.view(int(available_model_id))
    available_extra_config = _dict(_dict(available_row).get("extra_config"))
    return _dict(available_extra_config.get("options_schema"))


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _options(values: Any) -> list[dict[str, str]]:
    return [{"label": str(value), "value": str(value)} for value in _strings(values)]


def _reasoning_activation(extra_config: dict[str, Any]) -> dict[str, Any]:
    features = _dict(extra_config.get("features"))
    if not features:
        features = _dict(_dict(extra_config.get("available_model")).get("features"))
    reasoning = _dict(features.get("reasoning"))
    if not bool(reasoning.get("supported")):
        return {}
    activation = _dict(reasoning.get("activation"))
    values = [
        item
        for item in list(activation.get("values") or [])
        if item is not None and str(item).strip()
    ]
    if (
        str(activation.get("mode") or "").strip() != "extra_param"
        or not str(activation.get("param") or "").strip()
        or not values
    ):
        return {}
    return {**activation, "values": values}


def _reasoning_option_fields(
    provider_definition: dict[str, Any],
    generation_defaults: dict[str, Any],
) -> list[dict[str, Any]]:
    capability_fields = _dict(provider_definition.get("capability_option_fields"))
    extra_defaults = _dict(generation_defaults.get("extra"))
    fields: list[dict[str, Any]] = []
    for raw_field in list(capability_fields.get("reasoning") or []):
        if not isinstance(raw_field, dict):
            continue
        name = str(raw_field.get("name") or "").strip()
        if not name:
            continue
        field = dict(raw_field)
        field["name"] = f"extra.{name}"
        if "value" not in field:
            field["value"] = (
                extra_defaults[name] if name in extra_defaults else field.get("default")
            )
        if field.get("type") in {"boolean", "bool"}:
            field["type"] = "checkbox"
        fields.append(field)
    return fields


async def _form_model(
    row_id: int,
    row: dict[str, Any],
    constants: dict[str, Any],
) -> list[dict[str, Any]]:
    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
    generation_defaults = _dict(defaults.get("generation"))
    runtime_defaults = _dict(defaults.get("runtime"))
    capabilities = set(_strings(row.get("capabilities")))
    options_schema = _options_schema(row)
    if "chat" not in capabilities:
        fields: list[dict[str, Any]] = []
        for raw_field in list(options_schema.get("fields") or []):
            if not isinstance(raw_field, dict):
                continue
            name = str(raw_field.get("name") or "").strip()
            if not name:
                continue
            field = dict(raw_field)
            if field.get("type") in {"boolean", "bool"}:
                field["type"] = "checkbox"
            field["value"] = runtime_defaults.get(name, field.get("value"))
            fields.append(field)
        return fields
    deployment = ""
    provider_definition: dict[str, Any] = {}
    engine_id = row.get("engine_id")
    if engine_id not in (None, ""):
        engine = sdk.models.engine_registry.view(int(engine_id))
        provider = str(_dict(engine).get("provider") or "").strip()
        if provider:
            provider_definition = await sdk.engines.get_provider_definition(
                provider_id=provider
            )
            deployment = str(_dict(provider_definition).get("deployment") or "").strip()
    context_length_field: dict[str, Any] = {
        "name": "context_length",
        "label": sdk.i18n.t("system.engine.models.config.context_length"),
        "type": "number",
        "value": _context_length_value(runtime_defaults),
        "min": 1,
    }
    context_policy_options = _context_policy_options(constants)
    fields = [
        {
            "name": "max_tokens",
            "label": "max tokens",
            "type": "number",
            "value": generation_defaults.get("max_tokens"),
        },
        context_length_field,
        {
            "name": "context_policy",
            "label": sdk.i18n.t("system.engine.models.config.context_policy"),
            "type": "select",
            "value": _context_policy_value(
                runtime_defaults,
                constants,
                deployment=deployment,
            ),
            "options": context_policy_options,
        },
        {
            "name": "temperature",
            "label": "temperature",
            "type": "number",
            "value": generation_defaults.get("temperature", 0.7),
        },
        {
            "name": "top_p",
            "label": "top p",
            "type": "number",
            "value": generation_defaults.get("top_p", 0.9),
        },
    ]
    if "top_k" in generation_defaults:
        fields.append(
            {
                "name": "top_k",
                "label": "top k",
                "type": "number",
                "value": generation_defaults.get("top_k"),
            }
        )
    for raw_field in list(options_schema.get("fields") or []):
        if not isinstance(raw_field, dict):
            continue
        name = str(raw_field.get("name") or "").strip()
        if not name:
            continue
        field = dict(raw_field)
        if field.get("type") in {"boolean", "bool"}:
            field["type"] = "checkbox"
        field["value"] = runtime_defaults.get(name, field.get("value"))
        fields.append(field)
    reasoning_activation = _reasoning_activation(extra_config)
    if reasoning_activation:
        values = list(reasoning_activation.get("values") or [])
        param = str(reasoning_activation.get("param") or "").strip()
        field_type = str(reasoning_activation.get("type") or "select").strip().lower()
        extra_defaults = _dict(generation_defaults.get("extra"))
        field = {
            "name": f"extra.{param}",
            "label": param,
            "type": "checkbox" if field_type in {"boolean", "bool"} else "select",
            "value": extra_defaults.get(param)
            if param in extra_defaults
            else reasoning_activation.get("default"),
        }
        if field["type"] == "select":
            field["options"] = [{"label": str(item), "value": item} for item in values]
        fields.append(field)
        fields.extend(_reasoning_option_fields(provider_definition, generation_defaults))
    return fields


async def _config_form_model(
    row: dict[str, Any], constants: dict[str, Any]
) -> list[dict[str, Any]]:
    provider_definition: dict[str, Any] = {}
    engine_id = row.get("engine_id")
    if engine_id not in (None, ""):
        engine = sdk.models.engine_registry.view(int(engine_id))
        provider = str(_dict(engine).get("provider") or "").strip()
        if provider:
            provider_definition = await sdk.engines.get_provider_definition(
                provider_id=provider
            )
    return model_configuration_form_model(
        sdk,
        constants,
        capabilities=_strings(row.get("capabilities")),
        extra_config=_dict(row.get("extra_config")),
        capability_option_fields=_dict(
            provider_definition.get("capability_option_fields")
        ),
    )


async def render(params: dict, session: dict):
    row_id = int(params["id"])
    row = sdk.models.model_registry.view(row_id)
    constants = await sdk.engines.constants()
    builder = sdk.ui.load("utils/ui/yaml/models/engine_model_test_params")
    builder.set_store(
        "/engine_model_test_params",
        {
            "model_row_id": row_id,
            "form_model": (
                await _form_model(row_id, row, constants)
                if isinstance(row, dict)
                else []
            ),
            "config_form_model": (
                await _config_form_model(row, constants) if isinstance(row, dict) else []
            ),
        },
        scope="page",
    )
    return builder
