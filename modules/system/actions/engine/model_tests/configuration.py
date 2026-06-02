from __future__ import annotations

from typing import Any

from democrai.sdk.auth import permission_required
from democrai.sdk.ai_constants import (
    AI_CONTEXT_POLICIES,
    runtime_config_schema_for_capabilities,
)
from democrai.sdk.decorators import action

from modules.system.actions.engine.available_models.helpers import (
    EMBEDDING_INPUT_POLICY_KEY,
)
from modules.system.utils.actions.engine.model_test_support import (
    _nested_payload_value,
    _payload_has_path,
    _runtime_field_by_name,
    _runtime_field_names,
    _runtime_schema_value,
    _set_nested_value,
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected_string_list")
    return [str(item).strip() for item in value if str(item).strip()]


def _positive_int(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("expected_positive_int") from None
    if result <= 0:
        raise ValueError("expected_positive_int")
    return result


def _context_policy(value: Any) -> str:
    policy = str(value or "").strip()
    if policy and policy not in set(AI_CONTEXT_POLICIES):
        raise ValueError("invalid_context_policy")
    return policy


def _schema_field(schema: dict[str, Any], name: str) -> dict[str, Any]:
    for field in list(schema.get("fields") or []):
        current = _dict(field)
        if current.get("name") == name:
            return current
    return {}


def _option_values(field: dict[str, Any]) -> set[str]:
    return {
        str(option.get("value") or "").strip()
        for option in list(field.get("options") or [])
        if isinstance(option, dict)
    }


def _boolean_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("expected_boolean")


def _toast(module_sdk, level: str, title_key: str, message_key: str):
    return module_sdk.effects.notify(
        "toast",
        {
            "level": level,
            "title": module_sdk.i18n.t(title_key),
            "message": module_sdk.i18n.t(message_key),
        },
    )


def _feature_config(
    payload: dict[str, Any],
    capability: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    config = dict(_dict(schema.get("default")))
    config["supported"] = True
    mime_key = f"feature__{capability}__mime_types"
    if mime_key in payload:
        mime_types = _string_list(payload[mime_key])
        schema_fields = list(schema.get("fields") or [])
        mime_field = next(
            (
                _dict(field)
                for field in schema_fields
                if _dict(field).get("name") == "mime_types"
            ),
            {},
        )
        item_schema = _dict(mime_field.get("item_schema"))
        valid_values = {
            str(option.get("value") or "").strip()
            for option in list(item_schema.get("options") or [])
            if isinstance(option, dict)
        }
        if valid_values and any(item not in valid_values for item in mime_types):
            raise ValueError("invalid_mime_types")
        config["mime_types"] = mime_types
    if capability == "reasoning" and "feature__reasoning__mode" in payload:
        config["mode"] = str(payload["feature__reasoning__mode"] or "").strip()
    if capability == "reasoning" and "feature__reasoning__activation_type" in payload:
        activation_type = str(
            payload["feature__reasoning__activation_type"] or ""
        ).strip()
        activation_type_field = _schema_field(schema, "activation_type")
        if activation_type not in _option_values(activation_type_field):
            raise ValueError("invalid_reasoning_activation_type")
        if activation_type == "boolean":
            activation_default: Any = _boolean_value(
                payload.get("feature__reasoning__activation_default_boolean")
            )
            activation_values: list[Any] = [True, False]
        else:
            activation_values = _string_list(
                payload.get("feature__reasoning__activation_values")
            )
            activation_default = str(
                payload.get("feature__reasoning__activation_default_value") or ""
            ).strip()
            if not activation_values or activation_default not in activation_values:
                raise ValueError("invalid_reasoning_activation_values")
        config["activation"] = {
            "mode": "extra_param",
            "param": "reasoning",
            "type": activation_type,
            "default": activation_default,
            "values": activation_values,
        }
    return config


@action("save_engine_model_registry_configuration")
@permission_required(["system.engine.model.manage"])
async def save_engine_model_registry_configuration(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
):
    row_id = int(ctx["model_row_id"])
    payload = dict(ctx[str(ctx["form_id"])])
    constants = await module_sdk.engines.constants()

    valid_capabilities = constants.get("model_capabilities")
    if not isinstance(valid_capabilities, list):
        raise ValueError("sdk engines constants model_capabilities must be a list")
    valid_capability_set = {str(item) for item in valid_capabilities}
    try:
        capabilities = _string_list(payload.get("capabilities"))
    except ValueError:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_capabilities",
            )
        )
    if any(item not in valid_capability_set for item in capabilities):
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_capabilities",
            )
        )

    row = module_sdk.models.model_registry.view(row_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
    generation = _dict(defaults.get("generation"))
    runtime = _dict(defaults.get("runtime"))
    output_parsers = constants.get("output_parsers")
    if not isinstance(output_parsers, list):
        raise ValueError("sdk engines constants output_parsers must be a list")
    if "chat" in capabilities:
        output_parser = str(payload.get("output_parser") or "generic").strip()
        if output_parser not in output_parsers:
            return module_sdk.effects.respond(
                _toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        runtime["output_parser"] = output_parser
    else:
        runtime.pop("output_parser", None)
    if "reasoning" in capabilities:
        reasoning_parser = str(payload.get("reasoning_parser") or "").strip()
        if reasoning_parser and reasoning_parser not in output_parsers:
            return module_sdk.effects.respond(
                _toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        if reasoning_parser:
            runtime["reasoning_parser"] = reasoning_parser
        else:
            runtime.pop("reasoning_parser", None)
    else:
        runtime.pop("reasoning_parser", None)

    feature_schemas = _dict(constants.get("model_feature_schemas"))
    feature_keys = [item for item in capabilities if item in feature_schemas]
    try:
        features = {
            capability: _feature_config(
                payload,
                capability,
                _dict(feature_schemas.get(capability)),
            )
            for capability in feature_keys
        }
    except ValueError:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_model_configuration",
            )
        )
    if "embedding" in feature_keys:
        try:
            dim = _positive_int(payload.get("dim"))
        except ValueError:
            return module_sdk.effects.respond(
                _toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        policy = {
            "document_prefix": str(payload.get("embedding_document_prefix") or ""),
            "query_prefix": str(payload.get("embedding_query_prefix") or ""),
            "default_purpose": str(
                payload.get("embedding_default_purpose") or "document"
            ).strip(),
        }
        runtime[EMBEDDING_INPUT_POLICY_KEY] = policy
        features["embedding"]["input_policy"] = policy
        runtime["dim"] = dim
    elif EMBEDDING_INPUT_POLICY_KEY in runtime:
        runtime.pop(EMBEDDING_INPUT_POLICY_KEY)
        runtime.pop("dim", None)

    all_runtime_schema = runtime_config_schema_for_capabilities(valid_capability_set)
    runtime_schema = runtime_config_schema_for_capabilities(capabilities)
    active_runtime_fields = set(
        _runtime_field_names(_dict(runtime_schema.get("options_schema")))
    )
    for field_name in (
        set(_runtime_field_names(_dict(all_runtime_schema.get("options_schema"))))
        - active_runtime_fields
    ):
        runtime.pop(field_name, None)
    for field_name in active_runtime_fields:
        if _payload_has_path(payload, field_name):
            include_value, runtime_value = _runtime_schema_value(
                _runtime_field_by_name(
                    _dict(runtime_schema.get("options_schema")),
                    field_name,
                ),
                _nested_payload_value(payload, field_name),
            )
            if include_value:
                runtime[field_name] = runtime_value
            else:
                runtime.pop(field_name, None)
    if "context_length" in payload:
        runtime["context_length"] = _positive_int(payload.get("context_length"))
        runtime.pop("n_ctx", None)
        runtime.pop("max_model_len", None)
        runtime.pop("num_ctx", None)
    if "context_policy" in payload:
        policy = _context_policy(payload.get("context_policy"))
        if policy:
            runtime["context_policy"] = policy
        else:
            runtime.pop("context_policy", None)
    for key, value in payload.items():
        if str(key).startswith("extra."):
            _set_nested_value(generation, str(key), value)
    if "reasoning" not in capabilities:
        generation_extra = generation.get("extra")
        if isinstance(generation_extra, dict):
            for key in (
                "reasoning",
                "reasoning_budget",
                "reasoning_param_name",
            ):
                generation_extra.pop(key, None)
            if not generation_extra:
                generation.pop("extra", None)

    module_sdk.models.model_registry.update(
        row_id,
        {
            "capabilities": capabilities,
            "extra_config": {
                **extra_config,
                "defaults": {
                    **defaults,
                    "generation": generation,
                    "runtime": runtime,
                },
                "features": features,
            },
        },
    )
    engine_id = row.get("engine_id")
    if engine_id is not None:
        await module_sdk.engines.unload_loaded_model(
            engine_registry_id=int(engine_id),
            model_registry_id=row_id,
        )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
        _toast(
            module_sdk,
            "success",
            "system.model.toast.configuration_updated_title",
            "system.engine.models.config.registry_updated",
        ),
        module_sdk.effects.render(),
    )
