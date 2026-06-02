from __future__ import annotations

import json
from typing import Any

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.utils.actions.model.catalog import (
    active_catalog_download_tasks,
    catalog_entry_by_id,
    catalog_inventory_row_for_entry,
    catalog_row_with_entry_defaults,
    catalog_statuses_from_inventory,
)
from modules.system.ui.layout import shared_layout


def _route_catalog_id(params: dict) -> str:
    route_params = dict(params.get("route_params") or {})
    return str(route_params.get("id") or "").strip()


def _join(values: Any) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return ", ".join(str(value or "").strip() for value in values if str(value or "").strip())


def _pretty(value: Any) -> str:
    if value in (None, "", [], {}):
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value)


def _markdown_block(title: str, value: Any) -> str:
    return f"### {title}\n\n```json\n{_pretty(value)}\n```"


def _gb_value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{value} GB"


def _metadata_text(value: dict[str, Any]) -> str:
    if not value:
        return "-"
    parts: list[str] = []
    for key, item in value.items():
        if isinstance(item, list):
            item_text = _join(item)
        elif isinstance(item, dict):
            item_text = ", ".join(f"{nested_key}: {nested_value}" for nested_key, nested_value in item.items())
        else:
            item_text = str(item)
        if item_text:
            parts.append(f"{key}: {item_text}")
    if parts:
        return " | ".join(parts)
    return "-"


def _literal(value: str) -> dict[str, str]:
    return {"literalString": str(value or "")}


def _overview_model() -> list[dict[str, str]]:
    return [
        {"field": "status", "label": sdk.i18n.t("system.model.detail.status")},
        {"field": "format", "label": sdk.i18n.t("system.model.form.format.label")},
        {"field": "source_type", "label": sdk.i18n.t("system.model.detail.source")},
        {"field": "family", "label": sdk.i18n.t("system.model.form.family.label")},
        {"field": "source_engine", "label": sdk.i18n.t("system.model.detail.source_engine")},
        {"field": "capabilities", "label": sdk.i18n.t("system.model.form.capabilities.label")},
        {"field": "engines", "label": sdk.i18n.t("system.model.catalog.item.engines")},
    ]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _options(values: Any) -> list[dict[str, str]]:
    return [{"label": str(value), "value": str(value)} for value in _strings(values)]


def _feature_value(
    features: dict[str, Any],
    feature: str,
    field: str,
    default: Any = None,
) -> Any:
    config = _dict(features.get(feature))
    return config.get(field, default)


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


def _config_form_model(
    row: dict[str, Any],
    constants: dict[str, Any],
) -> list[dict[str, Any]]:
    capabilities = _strings(row.get("capabilities"))
    capability_set = set(capabilities)
    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
    runtime = _dict(defaults.get("runtime"))
    features = _dict(extra_config.get("features"))
    output_parsers = _strings(constants.get("output_parsers"))
    chat_templates = _strings(constants.get("chat_templates"))
    feature_schemas = _dict(constants.get("model_feature_schemas"))
    formatting_schema = _dict(constants.get("model_runtime_formatting_schema"))
    parser_options = _options(output_parsers)
    optional_parser_options = [{"label": "-", "value": ""}, *parser_options]
    template_options = _options(chat_templates)
    optional_template_options = [{"label": "-", "value": ""}, *template_options]
    option_sets = {
        "chat_templates": template_options,
        "chat_templates_optional": optional_template_options,
        "output_parsers": parser_options,
        "output_parsers_optional": optional_parser_options,
    }
    fields: list[dict[str, Any]] = [
        {
            "name": "label",
            "label": sdk.i18n.t("system.model.form.label.label"),
            "type": "text",
            "value": str(row.get("label") or ""),
        },
        {
            "name": "summary",
            "label": sdk.i18n.t("system.model.form.summary.label"),
            "type": "textarea",
            "value": str(row.get("summary") or ""),
        },
        {
            "name": "capabilities",
            "label": sdk.i18n.t("system.model.form.capabilities.label"),
            "type": "tags",
            "value": capabilities,
            "item_schema": {
                "type": "select",
                "options": _options(constants.get("model_capabilities")),
            },
        },
    ]

    if "chat" in capability_set:
        output_parser_field = _schema_field(formatting_schema, "output_parser")
        fields.append(
            {
                "name": "output_parser",
                "label": sdk.i18n.t("system.model.detail.config.output_parser"),
                "type": output_parser_field.get("type"),
                "value": str(
                    runtime.get("output_parser") or output_parser_field.get("default")
                ),
                "options": _field_options(output_parser_field, option_sets),
            }
        )

    if "reasoning" in capability_set or "reasoning" in features:
        reasoning_parser_field = _schema_field(formatting_schema, "reasoning_parser")
        reasoning_mode_field = _schema_field(
            _dict(feature_schemas.get("reasoning")),
            "mode",
        )
        fields.extend(
            [
                {
                    "name": "reasoning_parser",
                    "label": sdk.i18n.t(
                        "system.model.detail.config.reasoning_parser"
                    ),
                    "type": reasoning_parser_field.get("type"),
                    "value": str(
                        runtime.get("reasoning_parser")
                        or reasoning_parser_field.get("default")
                    ),
                    "options": _field_options(reasoning_parser_field, option_sets),
                },
                {
                    "name": "feature__reasoning__mode",
                    "label": sdk.i18n.t("system.model.detail.config.reasoning_mode"),
                    "type": reasoning_mode_field.get("type"),
                    "value": str(
                        _feature_value(
                            features,
                            "reasoning",
                            "mode",
                            reasoning_mode_field.get("default"),
                        )
                    ),
                    "options": _field_options(reasoning_mode_field, option_sets),
                },
            ]
        )

    for feature in ("image_to_text", "stt", "detection"):
        if feature not in capability_set and feature not in features:
            continue
        schema = _dict(feature_schemas.get(feature))
        mime_field = _schema_field(schema, "mime_types")
        fields.append(
            {
                "name": f"feature__{feature}__mime_types",
                "label": f"{schema.get('label') or feature} mime types",
                "type": mime_field.get("type"),
                "value": _strings(_feature_value(features, feature, "mime_types", [])),
                "item_schema": mime_field.get("item_schema"),
            }
        )

    if "embedding" in capability_set or "embedding" in features:
        policy = _dict(runtime.get("embedding_input_policy"))
        embedding_schema = _dict(feature_schemas.get("embedding"))
        dim_field = _schema_field(embedding_schema, "dim")
        default_purpose_field = _schema_field(embedding_schema, "default_purpose")
        fields.extend(
            [
                {
                    "name": "dim",
                    "label": sdk.i18n.t(
                        "system.engine.models.config.embedding_dim"
                    ),
                    "type": dim_field.get("type"),
                    "value": runtime.get("dim"),
                },
                {
                    "name": "embedding_document_prefix",
                    "label": sdk.i18n.t(
                        "system.engine.models.config.embedding_document_prefix"
                    ),
                    "type": "text",
                    "value": str(policy.get("document_prefix") or ""),
                },
                {
                    "name": "embedding_query_prefix",
                    "label": sdk.i18n.t(
                        "system.engine.models.config.embedding_query_prefix"
                    ),
                    "type": "text",
                    "value": str(policy.get("query_prefix") or ""),
                },
                {
                    "name": "embedding_default_purpose",
                    "label": sdk.i18n.t(
                        "system.engine.models.config.embedding_default_purpose"
                    ),
                    "type": default_purpose_field.get("type"),
                    "value": str(
                        policy.get("default_purpose")
                        or default_purpose_field.get("default")
                    ),
                    "options": _field_options(default_purpose_field, option_sets),
                },
            ]
        )

    return fields


async def render(params: dict, session: dict):

    catalog_id = _route_catalog_id(params)
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    page_builder = sdk.ui.load("utils/ui/yaml/models/catalog_detail")
    merge_builders(builder, page_builder)

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["system_model_catalog_detail_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    entry = await catalog_entry_by_id(sdk, catalog_id)

    if not isinstance(entry, dict):
        title = builder.get_component("system_model_catalog_detail_title")
        if title is not None:
            title.set_property("text", sdk.i18n.t("system.model.toast.catalog_not_found"))
        return builder

    existing_rows = (
        sdk.models.available_model_registry.all(
            sort={"field": "label", "direction": "asc"},
        ).get("rows")
        or []
    )
    existing_row = catalog_inventory_row_for_entry(entry, list(existing_rows))
    if isinstance(existing_row, dict):
        existing_row = catalog_row_with_entry_defaults(existing_row, entry)
    catalog_statuses = catalog_statuses_from_inventory(sdk, list(existing_rows), [entry])
    status = str(catalog_statuses.get(catalog_id) or "catalog_available").strip().lower()
    downloaded = status == "available"
    downloading = status == "downloading"
    can_download = not downloaded and not downloading
    builder.set_store("/system/model/catalog_detail/imported", downloaded, scope="page")
    builder.set_store(
        "/system/model/catalog_detail/can_download",
        can_download,
        scope="page",
    )
    builder.set_store("/system/model/catalog_detail/downloading", downloading, scope="page")
    builder.set_store(
        "/system/model/catalog_detail/available_model_id",
        int(existing_row["id"]) if isinstance(existing_row, dict) else None,
        scope="page",
    )
    builder.set_store(
        "/system/model/catalog_detail/capabilities",
        list((existing_row or {}).get("capabilities") or []),
        scope="page",
    )
    constants = await sdk.engines.constants()
    builder.set_store(
        "/system/model/catalog_detail/config_form",
        _config_form_model(existing_row, constants) if isinstance(existing_row, dict) else [],
        scope="page",
    )

    title = builder.get_component("system_model_catalog_detail_title")
    if title is not None:
        title.set_property("text", str(entry.get("label") or ""))

    summary = builder.get_component("system_model_catalog_detail_summary")
    if summary is not None:
        summary.set_property("text", str(entry.get("summary") or ""))

    overview = builder.get_component("system_model_catalog_detail_overview")
    if overview is not None:
        overview.set_property("model", _overview_model())
        overview.set_property(
            "data",
            {
                "status": sdk.i18n.t(
                    {
                        "available": "system.model.catalog.status.imported",
                        "downloading": "system.model.catalog.status.downloading",
                        "failed": "system.model.catalog.status.failed",
                    }.get(status, "system.model.catalog.status.available")
                ),
                "format": str(entry.get("format") or ""),
                "source_type": str(entry.get("source_type") or ""),
                "family": str(entry.get("family") or ""),
                "source_engine": _join(list(entry.get("source_engines") or [entry.get("source_engine")])),
                "capabilities": _join(list(entry.get("capabilities") or [])),
                "engines": _join(list(entry.get("source_engines") or [entry.get("source_engine")])),
            },
        )

    requirements_data = dict(entry.get("requirements") or {})
    metadata_data = dict(entry.get("metadata") or {})
    artifacts_data = list(entry.get("artifacts") or [])

    ram_value = builder.get_component("system_model_catalog_detail_ram_value")
    if ram_value is not None:
        ram_value.set_property("text", _gb_value(requirements_data.get("ram_gb")))

    storage_value = builder.get_component("system_model_catalog_detail_storage_value")
    if storage_value is not None:
        storage_value.set_property("text", _gb_value(requirements_data.get("storage_gb")))

    metadata = builder.get_component("system_model_catalog_detail_metadata")
    if metadata is not None:
        metadata.set_property("text", _metadata_text(metadata_data))

    artifacts = builder.get_component("system_model_catalog_detail_artifacts")
    if artifacts is not None:
        artifacts.set_property(
            "text",
            _markdown_block(
                sdk.i18n.t("system.model.detail.artifacts"),
                artifacts_data,
            ),
        )

    download = builder.get_component("system_model_catalog_detail_download")
    if download is not None:
        download.set_property("label", _literal(sdk.i18n.t("system.model.catalog.action.download")))
        download.set_property(
            "params",
            {
                "catalog_id": catalog_id,
                "task_mount_id": "system_model_catalog_detail_tasks",
            },
        )
        if status == "failed":
            download.set_property("label", _literal(sdk.i18n.t("system.model.catalog.action.retry")))

    tasks_container = builder.get_component("system_model_catalog_detail_tasks")
    if tasks_container is not None:
        tasks_container.allow("children.append")
        active_task = active_catalog_download_tasks(sdk).get(catalog_id)
        task_id = str(
            (active_task or {}).get("id")
            or (active_task or {}).get("task_id")
            or (active_task or {}).get("taskId")
            or ""
        ).strip()
        if task_id:
            task_card_id = f"system_model_catalog_detail_task_{task_id}"
            builder.add(sdk.ui.BackgroundTask(task_card_id, task_id))
            tasks_container.set_children([task_card_id])

    return builder
