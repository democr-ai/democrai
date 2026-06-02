from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AI_MODEL_FEATURE_SCHEMAS
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.actions.engine.available_models.helpers import (
    EMBEDDING_INPUT_POLICY_KEY,
)


def _toast(
    module_sdk,
    level: str,
    title_key: str,
    message_key: str,
):
    return module_sdk.effects.notify(
        "toast",
        {
            "level": level,
            "title": module_sdk.i18n.t(title_key),
            "message": module_sdk.i18n.t(message_key),
        },
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


def _feature_config(
    payload: dict[str, Any],
    capability: str,
) -> dict[str, Any]:
    schema = AI_MODEL_FEATURE_SCHEMAS[capability]
    config = dict(schema["default"])
    config["supported"] = True
    mime_key = f"feature__{capability}__mime_types"
    if mime_key in payload:
        mime_types = _string_list(payload[mime_key])
        schema_fields = list(_dict(schema).get("fields") or [])
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
    return config


@action("system.update_catalog_model_configuration")
@permission_required(["system.engine.model.manage"])
async def update_catalog_model_configuration(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
):
    row_id = int(ctx["available_model_id"])
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

    row = module_sdk.models.available_model_registry.view(row_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    label = str(payload.get("label") or "").strip()
    if not label:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_payload",
            )
        )

    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
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

    feature_keys = [item for item in capabilities if item in AI_MODEL_FEATURE_SCHEMAS]
    try:
        features = {
            capability: _feature_config(payload, capability)
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
            "document_prefix": str(
                payload.get("embedding_document_prefix") or ""
            ),
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

    module_sdk.models.available_model_registry.update(
        row_id,
        {
            "label": label,
            "summary": str(payload.get("summary") or "").strip(),
            "capabilities": capabilities,
            "extra_config": {
                **extra_config,
                "defaults": {
                    **defaults,
                    "runtime": runtime,
                },
                "features": features,
            },
        },
    )
    return module_sdk.effects.respond(
        _toast(
            module_sdk,
            "success",
            "system.model.toast.configuration_updated_title",
            "system.model.toast.configuration_updated",
        ),
        module_sdk.effects.render(),
    )
