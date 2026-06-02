from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AIRuntimeMethod, methods_for_capabilities
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.engines import KGExtractionOptions

from modules.system.ui.layout import shared_layout
from democrai.sdk.ui import merge_builders
from modules.system.utils.actions.engine.model_test_support import DEFAULT_GENERATION


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _csv(values: Any) -> str:
    if not isinstance(values, list):
        values = [values] if values else []
    return ", ".join(str(item or "").strip() for item in values if str(item or "").strip())


def _strings(values: Any) -> list[str]:
    if isinstance(values, list):
        raw_values = values
    else:
        raw_values = [values] if values else []
    resolved: list[str] = []
    for item in raw_values:
        value = str(item or "").strip()
        if value and value not in resolved:
            resolved.append(value)
    return resolved


def _detail_item(label: str, value: Any) -> dict[str, str]:
    return {
        "title": str(label or "").strip(),
        "text": str(value if value not in (None, "") else "-").strip() or "-",
    }


def _test_method_tab_id(method: str) -> str:
    return f"engine_model_test_method_tab_{method}"


def _available_test_items(
    provider_methods: list[str],
    model_methods: list[str],
    capabilities: list[str],
) -> list[dict[str, Any]]:
    provider_set = set(provider_methods)
    model_set = set(model_methods)
    capability_set = set(capabilities)
    labels = {
        AIRuntimeMethod.GENERATE_COMPLETION: "Generate completion",
        AIRuntimeMethod.GENERATE_STREAM: "Generate stream",
        AIRuntimeMethod.EMBED_TEXTS: "Embeddings",
        AIRuntimeMethod.RERANK: "Rerank",
        AIRuntimeMethod.CLASSIFY: "Classify",
        AIRuntimeMethod.EXTRACT_TOKENS: "Extract tokens",
        AIRuntimeMethod.EXTRACT_TRIPLES: "Extract triples",
        AIRuntimeMethod.SYNTHESIZE: "Synthesize",
        AIRuntimeMethod.SYNTHESIZE_STREAM: "Synthesize stream",
        AIRuntimeMethod.TRANSCRIBE: "Transcribe",
        AIRuntimeMethod.DETECT: "Detect",
    }
    items = [
        {
            "id": _test_method_tab_id(method),
            "method": method,
            "label": labels[method],
            "text": labels[method],
        }
        for method in (
            AIRuntimeMethod.GENERATE_COMPLETION,
            AIRuntimeMethod.GENERATE_STREAM,
            AIRuntimeMethod.EMBED_TEXTS,
            AIRuntimeMethod.RERANK,
            AIRuntimeMethod.CLASSIFY,
            AIRuntimeMethod.EXTRACT_TOKENS,
            AIRuntimeMethod.EXTRACT_TRIPLES,
            AIRuntimeMethod.SYNTHESIZE,
            AIRuntimeMethod.SYNTHESIZE_STREAM,
            AIRuntimeMethod.TRANSCRIBE,
            AIRuntimeMethod.DETECT,
        )
        if method in provider_set and method in model_set
    ]
    return items


def _model_features(row: dict[str, Any]) -> dict[str, Any]:
    extra_config = _dict(row.get("extra_config"))
    features = _dict(extra_config.get("features"))
    return features or _dict(_available_model(row).get("features"))


def _image_to_text_feature(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(_model_features(row).get("image_to_text"))


def _detection_feature(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(_model_features(row).get("detection"))


def _supports_attachments(row: dict[str, Any]) -> bool:
    return bool(_image_to_text_feature(row).get("supported"))


def _attachment_accept(row: dict[str, Any]) -> str:
    mime_types = _image_to_text_feature(row).get("mime_types") or []
    return ",".join(mime_types)


def _detection_attachment_accept(row: dict[str, Any]) -> str:
    mime_types = _detection_feature(row).get("mime_types") or []
    return ",".join(mime_types)


def _option(id_value: Any, label_value: Any = "") -> dict[str, str]:
    option_id = str(id_value or "").strip()
    option_label = str(label_value or option_id).strip() or option_id
    return {"id": option_id, "name": option_label}


def _tool_options(module_sdk) -> list[dict[str, str]]:
    tools = [
        *module_sdk.ai.list_tools(module_name="core"),
        *module_sdk.ai.list_tools(module_name="system"),
    ]
    agents = [
        *module_sdk.ai.list_agents(module_name="core"),
        *module_sdk.ai.list_agents(module_name="system"),
    ]
    return [
        *(_option(tool.name, tool.title or tool.name) for tool in tools),
        *(_option(f"agent.{agent.name}", agent.title or agent.name) for agent in agents),
    ]


def _skill_options(module_sdk) -> list[dict[str, str]]:
    return [
        _option(
            skill.metadata.name,
            skill.metadata.title or skill.metadata.name,
        )
        for skill in module_sdk.ai.list_skills(module_name="system")
    ]


def _mcp_options(module_sdk) -> list[dict[str, str]]:
    return [
        _option(server.name, server.name)
        for server in module_sdk.ai.list_mcp_servers()
    ]


def _model_capabilities(row: dict[str, Any], capabilities: list[str]) -> list[str]:
    resolved = _strings(capabilities)
    features = _model_features(row)
    for name, config in features.items():
        if isinstance(config, dict) and bool(config.get("supported")):
            feature = str(name or "").strip()
            if feature and feature not in resolved:
                resolved.append(feature)
    return resolved


def _generate_completion_form_model(row: dict[str, Any]) -> list[dict[str, Any]]:
    extra_config = _dict(row.get("extra_config"))
    test_config = _dict(extra_config.get("test_config"))
    return [
        {
            "name": "prompt",
            "label": "prompt",
            "type": "textarea",
            "value": str(
                test_config.get("prompt")
                or sdk.i18n.t("system.engine.model.test.default_prompt")
            ),
            "validations": [{"rule": "required"}],
        },
    ]


def _textarea_field(name: str, label: str, value: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "textarea",
        "value": value,
        "validations": [{"rule": "required"}],
    }


def _text_field(
    name: str,
    label: str,
    value: str = "",
    *,
    required: bool = False,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "name": name,
        "label": label,
        "type": "text",
        "value": value,
    }
    if required:
        field["validations"] = [{"rule": "required"}]
    return field


def _attachment_field(
    name: str,
    label: str,
    accept: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "name": name,
        "label": label,
        "type": "attachment",
        "accept": accept,
        "multiple": False,
    }
    if required:
        field["validations"] = [{"rule": "required"}]
    return field


def _audio_recorder_field(name: str, label: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": label,
        "type": "audio_recorder",
        "ingest": True,
        "validations": [{"rule": "required"}],
    }


def _available_model(row: dict[str, Any]) -> dict[str, Any]:
    return _dict(_dict(row.get("extra_config")).get("available_model"))


def _available_registry_model(row: dict[str, Any]) -> dict[str, Any]:
    available_model_id = row.get("available_model_id")
    if available_model_id in (None, ""):
        return {}
    available_model = sdk.models.available_model_registry.view(int(available_model_id))
    return _dict(available_model)


def _runtime_defaults(row: dict[str, Any]) -> dict[str, Any]:
    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
    runtime = _dict(defaults.get("runtime"))
    if runtime:
        return runtime
    available_runtime = _dict(_available_model(row).get("runtime"))
    available_defaults = _dict(available_runtime.get("defaults"))
    return _dict(available_defaults.get("runtime") or available_defaults)


def _runtime_option_fields(row: dict[str, Any]) -> list[dict[str, Any]]:
    extra_config = _dict(row.get("extra_config"))
    available_runtime = _dict(_available_model(row).get("runtime"))
    available_extra_config = _dict(_available_registry_model(row).get("extra_config"))
    fields: dict[str, dict[str, Any]] = {}
    for options_schema in (
        _dict(extra_config.get("options_schema")),
        _dict(available_extra_config.get("options_schema")),
        _dict(available_runtime.get("options_schema")),
    ):
        for item in list(options_schema.get("fields") or []):
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if name:
                fields[name] = dict(item)
    return list(fields.values())


def _completion_option_fields(
    row: dict[str, Any],
    composer: dict[str, Any],
) -> list[dict[str, Any]]:
    options = _completion_options(
        _dict(_dict(row.get("extra_config")).get("defaults")),
        composer,
    )
    fields: list[dict[str, Any]] = [
        {
            "name": "temperature",
            "label": sdk.i18n.t("system.engine.models.config.temperature"),
            "type": "number",
            "value": options.get("temperature"),
        },
        {
            "name": "top_p",
            "label": sdk.i18n.t("system.engine.models.config.top_p"),
            "type": "number",
            "value": options.get("top_p"),
        },
        {
            "name": "max_tokens",
            "label": sdk.i18n.t("system.engine.models.config.max_tokens"),
            "type": "integer",
            "value": options.get("max_tokens"),
        },
    ]
    if "top_k" in options:
        fields.append(
            {
                "name": "top_k",
                "label": "Top K",
                "type": "integer",
                "value": options.get("top_k"),
            }
        )
    field_names = {str(field.get("name") or "") for field in fields}
    for field in _runtime_option_fields(row):
        name = str(field.get("name") or "").strip()
        if name and name not in field_names:
            fields.append(field)
            field_names.add(name)
    composer_schema = _dict(composer.get("options_schema"))
    for raw_field in list(composer_schema.get("fields") or []):
        if not isinstance(raw_field, dict):
            continue
        name = str(raw_field.get("name") or "").strip()
        if name and name not in field_names:
            fields.append(dict(raw_field))
            field_names.add(name)
    return fields


def _completion_options(
    defaults: dict[str, Any],
    composer: dict[str, Any],
) -> dict[str, Any]:
    generation = _dict(defaults.get("generation"))
    options = {
        **dict(DEFAULT_GENERATION),
        **generation,
    }
    extra = _dict(options.pop("extra", None))
    for key, value in extra.items():
        options[f"extra.{key}"] = value
    options.update(_dict(composer.get("options")))
    return options


def _field_default(row: dict[str, Any], field: dict[str, Any]) -> Any:
    name = str(field.get("name") or "").strip()
    runtime_defaults = _runtime_defaults(row)
    if name and runtime_defaults.get(name) not in (None, ""):
        return runtime_defaults.get(name)
    return field.get("default", field.get("value", ""))


def _option_schema_form_fields(
    row: dict[str, Any],
    *,
    allowed_names: set[str] | None = None,
) -> list[dict[str, Any]]:
    fields: list[dict[str, Any]] = []
    for raw_field in _runtime_option_fields(row):
        name = str(raw_field.get("name") or "").strip()
        if not name or (allowed_names is not None and name not in allowed_names):
            continue
        field_type = str(raw_field.get("type") or "text").strip().lower()
        form_type = {
            "boolean": "checkbox",
            "bool": "checkbox",
            "string": "text",
        }.get(field_type, field_type)
        item: dict[str, Any] = {
            "name": name,
            "label": str(raw_field.get("label") or name),
            "type": form_type,
            "value": _field_default(row, raw_field),
        }
        if isinstance(raw_field.get("options"), list):
            item["options"] = list(raw_field.get("options") or [])
        for key in ("min", "max", "step", "placeholder"):
            if key in raw_field:
                item[key] = raw_field.get(key)
        fields.append(item)
    return fields


def _prompt_form_model(row: dict[str, Any]) -> list[dict[str, Any]]:
    extra_config = _dict(row.get("extra_config"))
    test_config = _dict(extra_config.get("test_config"))
    return [
        _textarea_field(
            "prompt",
            "prompt",
            str(
                test_config.get("prompt")
                or sdk.i18n.t("system.engine.model.test.default_prompt")
            ),
        )
    ]


def _synthesize_form_model(row: dict[str, Any]) -> list[dict[str, Any]]:
    option_fields = _option_schema_form_fields(
        row,
        allowed_names={"voice", "wpm", "pitch", "amplitude", "word_gap"},
    )
    return [
        *_prompt_form_model(row),
        *option_fields,
    ]


def _detect_form_model(row: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _attachment_field("media", "media", _detection_attachment_accept(row)),
        *_option_schema_form_fields(row),
        {
            "name": "frame_index",
            "label": "frame_index",
            "type": "number",
            "value": 0,
        },
    ]


def _kg_option_default(row: dict[str, Any], name: str) -> Any:
    runtime_defaults = _runtime_defaults(row)
    schema_defaults = KGExtractionOptions().model_dump()
    if runtime_defaults.get(name) not in (None, ""):
        return runtime_defaults.get(name)
    return schema_defaults.get(name)


def _extract_triples_form_model(row: dict[str, Any]) -> list[dict[str, Any]]:
    fields = [
        _text_field("kind", "kind", "document", required=True),
        _text_field("title", "title"),
        {"name": "summary", "label": "summary", "type": "textarea", "value": ""},
        _textarea_field(
            "content",
            "content",
            "Alice founded Example Corp in Rome. Example Corp acquired Beta Labs.",
        ),
        {
            "name": "max_entities",
            "label": "max entities",
            "type": "integer",
            "value": _kg_option_default(row, "max_entities"),
            "min": 1,
        },
        {
            "name": "max_relations",
            "label": "max relations",
            "type": "integer",
            "value": _kg_option_default(row, "max_relations"),
            "min": 1,
        },
        {
            "name": "max_tokens",
            "label": "max tokens",
            "type": "integer",
            "value": _kg_option_default(row, "max_tokens"),
            "min": 1,
        },
        {
            "name": "temperature",
            "label": "temperature",
            "type": "number",
            "value": _kg_option_default(row, "temperature"),
            "min": 0,
            "max": 2,
            "step": 0.01,
        },
        {
            "name": "threshold",
            "label": "threshold",
            "type": "number",
            "value": _kg_option_default(row, "threshold"),
            "min": 0,
            "max": 1,
            "step": 0.05,
        },
        {
            "name": "top_k",
            "label": "top k",
            "type": "integer",
            "value": _kg_option_default(row, "top_k"),
            "min": 1,
        },
        {
            "name": "entity_labels",
            "label": "entity labels",
            "type": "tags",
            "value": _kg_option_default(row, "entity_labels"),
            "item_schema": {"type": "text"},
        },
        {
            "name": "relation_labels",
            "label": "relation labels",
            "type": "tags",
            "value": _kg_option_default(row, "relation_labels"),
            "item_schema": {"type": "text"},
        },
    ]
    field_names = {str(field.get("name") or "") for field in fields}
    for field in _option_schema_form_fields(row):
        name = str(field.get("name") or "").strip()
        if name and name not in field_names:
            fields.append(field)
            field_names.add(name)
    return fields


def _forms_model(row: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    return {
        AIRuntimeMethod.GENERATE_COMPLETION: _generate_completion_form_model(row),
        AIRuntimeMethod.GENERATE_STREAM: _prompt_form_model(row),
        AIRuntimeMethod.EMBED_TEXTS: [
            _textarea_field(
                "texts",
                "texts",
                "Local model embeddings\nSecond embedding input",
            )
        ],
        AIRuntimeMethod.RERANK: [
            _textarea_field("prompt", "query", "capital of France"),
            _textarea_field(
                "texts",
                "texts",
                "Paris is the capital of France.\nThe sky is blue.",
            ),
        ],
        AIRuntimeMethod.CLASSIFY: [
            _textarea_field("texts", "texts", "I like this result.")
        ],
        AIRuntimeMethod.EXTRACT_TOKENS: [
            _textarea_field(
                "prompt",
                "text",
                "Alice works at Example Corp in Rome.",
            )
        ],
        AIRuntimeMethod.EXTRACT_TRIPLES: _extract_triples_form_model(row),
        AIRuntimeMethod.SYNTHESIZE: _synthesize_form_model(row),
        AIRuntimeMethod.SYNTHESIZE_STREAM: _synthesize_form_model(row),
        AIRuntimeMethod.TRANSCRIBE: [
            _audio_recorder_field("audio", "audio"),
            *_option_schema_form_fields(row, allowed_names={"language"}),
        ],
        AIRuntimeMethod.DETECT: _detect_form_model(row),
        "tool_calling": [
            _textarea_field(
                "prompt",
                "prompt",
                "Use the available tool to get the temperature in Rome.",
            ),
            {
                "name": "tool_choice",
                "label": "tool_choice",
                "type": "select",
                "value": "auto",
                "options": [
                    {"label": "auto", "value": "auto"},
                    {"label": "required", "value": "required"},
                ],
            },
        ],
        "multimodal": [
            _textarea_field("prompt", "prompt", "Describe the attached media."),
            _attachment_field("media", "media", "image/*,audio/*,video/*"),
        ],
    }


async def render(params: dict, session: dict):
    route_params = params.get("route_params")
    row_id = (
        int(route_params["id"])
        if isinstance(route_params, dict) and "id" in route_params
        else None
    )

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/models/engine_model_detail")
    merge_builders(builder, page_builder)
    root_id = "engine_model_detail_page"
    row = sdk.models.model_registry.view(row_id) if row_id is not None else None
    if isinstance(row, dict):
        extra_config = _dict(row.get("extra_config"))
        defaults = _dict(extra_config.get("defaults"))
        test_config = _dict(extra_config.get("test_config"))
        binding_label = str(
            extra_config.get("binding_label") or row.get("name") or ""
        ).strip()
        runtime_model_ref = str(
            extra_config.get("runtime_model_ref") or row.get("name") or ""
        ).strip()
        available_model = _dict(extra_config.get("available_model"))
        capabilities = _model_capabilities(row, list(row.get("capabilities") or []))
        composer = sdk.ai.get_composer_options_by_model_registry_id(int(row["id"]))
        composer_capabilities = list(composer.get("model_capabilities") or [])
        if not composer_capabilities:
            composer_capabilities = capabilities

        engine_id = int(row["engine_id"])
        engine = sdk.models.engine_registry.view(engine_id)
        engine_name = str(
            (engine or {}).get("name") or (engine or {}).get("provider") or ""
        )
        provider = str((engine or {}).get("provider") or "").strip().lower()
        provider_definition = (
            await sdk.engines.get_provider_definition(provider_id=provider)
            if provider
            else None
        )
        provider_methods = _strings((provider_definition or {}).get("runtime_methods"))
        model_methods = _strings(
            row.get("runtime_methods") or methods_for_capabilities(capabilities)
        )
        test_items = _available_test_items(
            provider_methods,
            model_methods,
            capabilities,
        )
        test_child_ids = [str(item["id"]) for item in test_items]
        title = binding_label or runtime_model_ref
        summary_lines = [
            f"Binding: {binding_label}",
            f"Runtime ref: {runtime_model_ref}",
            f"Engine ID: {row.get('engine_id')}",
            f"Engine: {engine_name}",
            f"Available model ID: {row.get('available_model_id')}",
            f"Capabilities: {_csv(capabilities)}",
            f"Runtime methods: {_csv(model_methods)}",
            f"Path: {row.get('model_path')}",
            f"Format: {available_model.get('format')}",
            f"Source: {available_model.get('source_kind')}",
        ]
        store_payload = {
            "model_row_id": int(row["id"]),
            "current_model_id": str(row.get("id") or ""),
            "current_models": [
                {
                    "id": str(row.get("id") or ""),
                    "name": title,
                }
            ],
            "runtime_params_drawer_path": f"/system/engine/model/test_params?id={int(row['id'])}",
            "default_params_drawer_path": f"/system/engine/model/default_params?id={int(row['id'])}",
            "title": title,
            "engine_name": engine_name or "-",
            "format": str(available_model.get("format") or "-"),
            "source": str(available_model.get("source_kind") or "-"),
            "capabilities_text": _csv(capabilities) or "-",
            "capabilities": capabilities,
            "model_capabilities": composer_capabilities,
            "runtime_methods_text": _csv(model_methods) or "-",
            "generate_completion_prompt": str(
                test_config.get("prompt")
                or sdk.i18n.t("system.engine.model.test.default_prompt")
            ),
            "generate_completion_current_request": "",
            "generate_completion_options": _completion_options(defaults, composer),
            "generate_completion_options_schema": {
                "fields": _completion_option_fields(row, composer),
            },
            "generate_completion_options_editable": True,
            "generate_stream_prompt": str(
                test_config.get("prompt")
                or sdk.i18n.t("system.engine.model.test.default_prompt")
            ),
            "generate_stream_current_request": "",
            "generate_stream_options": _completion_options(defaults, composer),
            "generate_stream_options_schema": {
                "fields": _completion_option_fields(row, composer),
            },
            "generate_stream_options_editable": True,
            "available_tools": (
                _tool_options(sdk)
                if "tool_calling" in set(composer_capabilities)
                else []
            ),
            "available_skills": _skill_options(sdk),
            "available_mcp": _mcp_options(sdk),
            "selected_tools": [],
            "selected_skills": [],
            "selected_mcp": [],
            "supports_attachments": _supports_attachments(row),
            "attachment_accept": _attachment_accept(row),
            "supports_audio_input": "audio" in set(capabilities),
            "detail_items": [
                _detail_item("Binding", binding_label),
                _detail_item("Runtime ref", runtime_model_ref),
                _detail_item("Engine ID", row.get("engine_id")),
                _detail_item("Available model ID", row.get("available_model_id")),
                _detail_item("Path", row.get("model_path")),
            ],
            "summary": {"literalString": "\n".join(summary_lines)},
            "breadcrumb_segments": [
                {
                    "label": sdk.i18n.t("system.engine.list.title"),
                    "path": "/system/engine/list",
                },
                {
                    "label": engine_name or sdk.i18n.t("system.engine.models.title"),
                    "path": f"/system/engine/instance/{row.get('engine_id')}/view",
                },
                {"label": title, "current": True},
            ],
            "valid": True,
            "tests": test_items,
            "available_tests": {str(item["method"]): True for item in test_items},
            "tests_available": bool(test_items),
            "forms": _forms_model(row),
            "last_status": "",
            "last_result": {
                "output": sdk.i18n.t("system.engine.model.test.result_empty"),
                "metrics": "",
            },
        }
    else:
        test_child_ids = []
        store_payload = {
            "model_row_id": row_id,
            "current_model_id": "",
            "current_models": [],
            "runtime_params_drawer_path": "",
            "default_params_drawer_path": "",
            "title": sdk.i18n.t("system.engine.model.detail.title"),
            "engine_name": "-",
            "format": "-",
            "source": "-",
            "capabilities_text": "-",
            "capabilities": [],
            "model_capabilities": [],
            "runtime_methods_text": "-",
            "generate_completion_prompt": "",
            "generate_completion_current_request": "",
            "generate_completion_options": {},
            "generate_completion_options_schema": {"fields": []},
            "generate_stream_prompt": "",
            "generate_stream_current_request": "",
            "generate_stream_options": {},
            "generate_stream_options_schema": {"fields": []},
            "available_tools": [],
            "available_skills": [],
            "available_mcp": [],
            "selected_tools": [],
            "selected_skills": [],
            "selected_mcp": [],
            "supports_attachments": False,
            "attachment_accept": "",
            "supports_audio_input": False,
            "detail_items": [],
            "summary": sdk.i18n.t(
                "system.engine.model.detail.placeholder",
                context={"id": str(row_id or "-")},
            ),
            "breadcrumb_segments": [
                {
                    "label": sdk.i18n.t("system.engine.list.title"),
                    "path": "/system/engine/list",
                },
                {
                    "label": sdk.i18n.t("system.engine.model.detail.title"),
                    "current": True,
                },
            ],
            "valid": False,
            "tests": [],
            "available_tests": {},
            "tests_available": False,
            "forms": {},
            "last_status": "",
            "last_result": {"output": "", "metrics": ""},
        }
    builder.set_store("/engine_model_test", store_payload, scope="page")
    tabs_component = builder.get_component("engine_model_test_method_tabs")
    if tabs_component is not None:
        tabs_component.set_children(test_child_ids)

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children([root_id])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
