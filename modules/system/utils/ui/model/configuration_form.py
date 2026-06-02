from __future__ import annotations

from typing import Any

EMBEDDING_INPUT_POLICY_KEY = "embedding_input_policy"


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _options(values: Any) -> list[dict[str, str]]:
    return [{"label": str(value), "value": str(value)} for value in _strings(values)]


def _field_label(module_sdk, field: dict[str, Any], fallback: str) -> str:
    label_key = str(field.get("label_key") or "").strip()
    if label_key:
        return module_sdk.i18n.t(label_key)
    return str(field.get("label") or fallback)


def _form_field_type(raw_type: Any) -> str:
    field_type = str(raw_type or "text").strip().lower()
    return {"boolean": "checkbox", "bool": "checkbox"}.get(field_type, field_type)


def _schema_field(schema: dict[str, Any], name: str) -> dict[str, Any]:
    for field in list(schema.get("fields") or []):
        current = _dict(field)
        if current.get("name") == name:
            return current
    raise ValueError(f"missing_model_config_field:{name}")


def _field_options(
    field: dict[str, Any],
    option_sets: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    options_key = str(field.get("options_key") or "").strip()
    if options_key:
        return list(option_sets[options_key])
    return list(field.get("options") or [])


def _capability_show_if(capability: str) -> dict[str, Any]:
    return {
        "conditions": [
            {
                "left": "$form.capabilities",
                "op": "contains",
                "right": capability,
            }
        ]
    }


def _capabilities_show_if(capabilities: list[str]) -> dict[str, Any]:
    return {
        "mode": "OR",
        "conditions": [
            {
                "left": "$form.capabilities",
                "op": "contains",
                "right": capability,
            }
            for capability in capabilities
        ],
    }


def _all_show_if(*rules: dict[str, Any]) -> dict[str, Any]:
    conditions: list[dict[str, Any]] = []
    for rule in rules:
        conditions.extend(
            [
                dict(condition)
                for condition in list(rule.get("conditions") or [])
                if isinstance(condition, dict)
            ]
        )
    return {"conditions": conditions}


def _feature_value(
    features: dict[str, Any],
    feature: str,
    field: str,
    default: Any = None,
) -> Any:
    config = _dict(features.get(feature))
    return config.get(field, default)


def _feature_field_value(
    *,
    name: str,
    capability: str,
    schema_field: dict[str, Any],
    features: dict[str, Any],
    runtime: dict[str, Any],
    extra_config: dict[str, Any],
) -> Any:
    if name == "dim":
        return runtime.get("dim", schema_field.get("default"))
    if name == "embedding_document_prefix":
        return _dict(runtime.get(EMBEDDING_INPUT_POLICY_KEY)).get(
            "document_prefix",
            schema_field.get("default", ""),
        )
    if name == "embedding_query_prefix":
        return _dict(runtime.get(EMBEDDING_INPUT_POLICY_KEY)).get(
            "query_prefix",
            schema_field.get("default", ""),
        )
    if name == "embedding_default_purpose":
        return _dict(runtime.get(EMBEDDING_INPUT_POLICY_KEY)).get(
            "default_purpose",
            schema_field.get("default", "document"),
        )
    if capability == "reasoning" and name.startswith("feature__reasoning__activation_"):
        activation = _dict(_dict(features.get("reasoning")).get("activation"))
        if name == "feature__reasoning__activation_type":
            return activation.get("type", schema_field.get("default", "boolean"))
        if name == "feature__reasoning__activation_default_boolean":
            default = activation.get("default")
            return default if isinstance(default, bool) else schema_field.get("default")
        if name == "feature__reasoning__activation_default_value":
            default = activation.get("default")
            return "" if default is None or isinstance(default, bool) else str(default)
        if name == "feature__reasoning__activation_values":
            return _strings(activation.get("values", schema_field.get("default", [])))
    return _feature_value(
        features,
        capability,
        str(schema_field.get("name") or ""),
        schema_field.get("default"),
    )


def _context_length_value(runtime: dict[str, Any]) -> Any:
    for key in ("context_length", "n_ctx", "max_model_len", "num_ctx"):
        value = runtime.get(key)
        if value not in (None, ""):
            return value
    return None


def _context_policy_options(
    module_sdk,
    constants: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "label": module_sdk.i18n.t(
                f"system.engine.models.config.context_policy.{value}"
            ),
            "value": str(value),
        }
        for value in list(constants.get("context_policies") or [])
        if str(value or "").strip()
    ]


def _context_policy_value(
    runtime: dict[str, Any],
    constants: dict[str, Any],
) -> str:
    value = str(runtime.get("context_policy") or "").strip()
    if value:
        return value
    defaults = _dict(constants.get("context_policy_defaults"))
    return str(defaults.get("local") or "")


def _option_sets(constants: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    output_parsers = _options(constants.get("output_parsers"))
    chat_templates = _options(constants.get("chat_templates"))
    return {
        "model_capabilities": _options(constants.get("model_capabilities")),
        "chat_templates": chat_templates,
        "chat_templates_optional": [{"label": "-", "value": ""}, *chat_templates],
        "output_parsers": output_parsers,
        "output_parsers_optional": [{"label": "-", "value": ""}, *output_parsers],
    }


def model_configuration_form_model(
    module_sdk,
    constants: dict[str, Any],
    *,
    capabilities: list[str] | None = None,
    extra_config: dict[str, Any] | None = None,
    capability_option_fields: dict[str, Any] | None = None,
    leading_fields: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    schema = _dict(constants.get("model_configuration_form_schema"))
    option_sets = _option_sets(constants)
    selected_capabilities = _strings(capabilities or [])
    extra = _dict(extra_config)
    defaults = _dict(extra.get("defaults"))
    generation = _dict(defaults.get("generation"))
    runtime = _dict(defaults.get("runtime"))
    features = _dict(extra.get("features"))
    fields: list[dict[str, Any]] = list(leading_fields or [])

    capabilities_field = _dict(schema.get("capabilities"))
    item_schema = _dict(capabilities_field.get("item_schema"))
    item_options_key = str(item_schema.get("options_key") or "").strip()
    fields.append(
        {
            "name": str(capabilities_field.get("name") or "capabilities"),
            "label": _field_label(module_sdk, capabilities_field, "capabilities"),
            "type": str(capabilities_field.get("type") or "tags"),
            "value": selected_capabilities,
            "item_schema": {
                "type": str(item_schema.get("type") or "select"),
                "options": option_sets[item_options_key],
            },
        }
    )

    context_length = _context_length_value(runtime)
    if "chat" in selected_capabilities and context_length not in (None, ""):
        fields.append(
            {
                "name": "context_length",
                "label": module_sdk.i18n.t(
                    "system.engine.models.config.context_length"
                ),
                "type": "number",
                "value": context_length,
                "min": 1,
            }
        )
        fields.append(
            {
                "name": "context_policy",
                "label": module_sdk.i18n.t(
                    "system.engine.models.config.context_policy"
                ),
                "type": "select",
                "value": _context_policy_value(runtime, constants),
                "options": _context_policy_options(module_sdk, constants),
            }
        )

    formatting_schema = _dict(constants.get("model_runtime_formatting_schema"))
    for spec in list(schema.get("formatting") or []):
        if not isinstance(spec, dict):
            continue
        name = str(spec.get("name") or "").strip()
        schema_field = _schema_field(
            formatting_schema,
            str(spec.get("schema_field") or name),
        )
        capabilities_for_field = _strings(spec.get("capabilities"))
        field = {
            "name": name,
            "label": _field_label(module_sdk, spec, name),
            "type": _form_field_type(schema_field.get("type")),
            "value": runtime.get(name, schema_field.get("default")),
            "options": _field_options({**schema_field, **spec}, option_sets),
            "show_if": _capabilities_show_if(capabilities_for_field),
        }
        fields.append(field)

    feature_schemas = _dict(constants.get("model_feature_schemas"))
    for spec in list(schema.get("features") or []):
        if not isinstance(spec, dict):
            continue
        capability = str(spec.get("capability") or "").strip()
        feature_schema = _dict(feature_schemas.get(capability))
        schema_field = _schema_field(feature_schema, str(spec.get("schema_field") or ""))
        name = str(spec.get("name") or "").strip()
        show_if = _capability_show_if(capability)
        show_when = _dict(spec.get("show_when"))
        if show_when:
            show_if = _all_show_if(
                show_if,
                {
                    "conditions": [
                        {
                            "left": f"$form.{show_when.get('field')}",
                            "op": "==",
                            "right": show_when.get("equals"),
                        }
                    ]
                },
            )
        field: dict[str, Any] = {
            "name": name,
            "label": _field_label(module_sdk, spec, name),
            "type": _form_field_type(schema_field.get("type")),
            "value": _feature_field_value(
                name=name,
                capability=capability,
                schema_field=schema_field,
                features=features,
                runtime=runtime,
                extra_config=extra,
            ),
            "show_if": show_if,
        }
        if isinstance(schema_field.get("options"), list):
            field["options"] = list(schema_field.get("options") or [])
        if isinstance(schema_field.get("item_schema"), dict):
            field["item_schema"] = dict(schema_field.get("item_schema") or {})
        for key in ("min", "max", "step", "placeholder"):
            if key in schema_field:
                field[key] = schema_field.get(key)
        fields.append(field)

    capability_fields = _dict(capability_option_fields)
    generation_extra = _dict(generation.get("extra"))
    existing_feature_names = {str(field.get("name") or "") for field in fields}
    for capability, raw_fields in capability_fields.items():
        capability_name = str(capability or "").strip()
        if not capability_name:
            continue
        for raw_field in list(raw_fields or []):
            if not isinstance(raw_field, dict):
                continue
            name = str(raw_field.get("name") or "").strip()
            if not name:
                continue
            field_name = f"extra.{name}"
            if field_name in existing_feature_names:
                continue
            field = dict(raw_field)
            field["name"] = field_name
            field["type"] = _form_field_type(field.get("type"))
            field["value"] = (
                generation_extra[name]
                if name in generation_extra
                else field.get("default")
            )
            field["show_if"] = _capability_show_if(capability_name)
            fields.append(field)
            existing_feature_names.add(field_name)

    runtime_schemas = _dict(constants.get("model_runtime_config_schemas"))
    merged_runtime_fields: dict[str, dict[str, Any]] = {}
    for capability, runtime_schema in runtime_schemas.items():
        option_schema = _dict(_dict(runtime_schema).get("options_schema"))
        for raw_field in list(option_schema.get("fields") or []):
            if not isinstance(raw_field, dict):
                continue
            name = str(raw_field.get("name") or "").strip()
            if not name or any(str(field.get("name") or "") == name for field in fields):
                continue
            current = merged_runtime_fields.setdefault(
                name,
                {"field": dict(raw_field), "capabilities": []},
            )
            current["capabilities"].append(str(capability))
            if capability in selected_capabilities:
                current["field"] = dict(raw_field)

    for name, config in merged_runtime_fields.items():
        raw_field = _dict(config.get("field"))
        capabilities_for_field = _strings(config.get("capabilities"))
        field: dict[str, Any] = {
            "name": name,
            "label": _field_label(module_sdk, raw_field, name),
            "type": _form_field_type(raw_field.get("type")),
            "value": runtime.get(name, raw_field.get("default")),
            "show_if": _capabilities_show_if(capabilities_for_field),
        }
        if isinstance(raw_field.get("options"), list):
            field["options"] = list(raw_field.get("options") or [])
        if isinstance(raw_field.get("item_schema"), dict):
            field["item_schema"] = dict(raw_field.get("item_schema") or {})
        for key in ("min", "max", "step", "placeholder"):
            if key in raw_field:
                field[key] = raw_field.get(key)
        fields.append(field)

    custom_options_schema = _dict(extra.get("options_schema"))
    existing_names = {str(field.get("name") or "") for field in fields}
    for raw_field in list(custom_options_schema.get("fields") or []):
        if not isinstance(raw_field, dict):
            continue
        name = str(raw_field.get("name") or "").strip()
        if not name or name in existing_names:
            continue
        field: dict[str, Any] = {
            "name": name,
            "label": _field_label(module_sdk, raw_field, name),
            "type": _form_field_type(raw_field.get("type")),
            "value": runtime.get(name, raw_field.get("default")),
        }
        if isinstance(raw_field.get("options"), list):
            field["options"] = list(raw_field.get("options") or [])
        if isinstance(raw_field.get("item_schema"), dict):
            field["item_schema"] = dict(raw_field.get("item_schema") or {})
        for key in ("min", "max", "step", "placeholder"):
            if key in raw_field:
                field[key] = raw_field.get(key)
        fields.append(field)
        existing_names.add(name)

    return fields


def model_extra_config_for_form(
    *,
    defaults: dict[str, Any] | None = None,
    features: dict[str, Any] | None = None,
    options_schema: dict[str, Any] | None = None,
    runtime_model_ref: str | None = None,
) -> dict[str, Any]:
    extra: dict[str, Any] = {
        "defaults": defaults if isinstance(defaults, dict) else {},
        "features": features if isinstance(features, dict) else {},
    }
    if isinstance(options_schema, dict):
        extra["options_schema"] = options_schema
    if runtime_model_ref:
        extra["runtime_model_ref"] = str(runtime_model_ref)
    return extra
