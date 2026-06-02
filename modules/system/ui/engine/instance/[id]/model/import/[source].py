from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AIModelSourceKind
from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.engine.model_import import (
    engine_import_runtime_template,
    provider_accept_extensions,
    provider_definition,
    provider_model_capabilities,
    provider_model_formats,
    provider_supports_inventory_import,
    runtime_defaults,
    runtime_options_schema,
)


_ROUTE_SOURCE_KIND = {
    "local_file": AIModelSourceKind.UPLOAD,
    "huggingface": AIModelSourceKind.HUGGINGFACE,
}


def _field(name: str, label_key: str, field_type: str = "text", **extra: Any) -> dict:
    field = {
        "name": name,
        "label": sdk.i18n.t(label_key),
        "type": field_type,
    }
    field.update(extra)
    return field


def _required(message_key: str) -> list[dict]:
    return [{"rule": "required", "message": sdk.i18n.t(message_key)}]


def _option_label(value: str) -> str:
    return str(value or "").replace("_", " ").title()


def _options(values: list[str]) -> list[dict[str, str]]:
    return [{"label": _option_label(value), "value": value} for value in values]


def _row(*children: dict, spacing: int = 12) -> dict:
    return {"type": "row", "spacing": spacing, "children": list(children)}


def _base_fields(provider: str) -> list[dict]:
    return [
        _field(
            "name",
            "system.model.form.name.label",
            placeholder=sdk.i18n.t("system.model.form.name.placeholder"),
            validations=_required("system.model.form.name.required"),
        ),
        _field(
            "label",
            "system.model.form.label.label",
            placeholder=sdk.i18n.t("system.model.form.label.placeholder"),
            validations=_required("system.model.form.label.required"),
        ),
        _field(
            "format",
            "system.model.form.format.label",
            "select",
            options=_options(provider_model_formats(provider)),
            placeholder=sdk.i18n.t("system.model.form.format.placeholder"),
            validations=_required("system.model.form.format.required"),
        ),
        _field(
            "capabilities",
            "system.model.form.capabilities.label",
            "select",
            multiple=True,
            options=_options(provider_model_capabilities(provider)),
            placeholder=sdk.i18n.t("system.model.form.capabilities.placeholder"),
        ),
    ]


def _source_fields(source: str, provider: str) -> list[dict]:
    if source == "local_file":
        return [
            _field(
                "artifact_file",
                "system.model.form.artifact_file.label",
                "file",
                accept=provider_accept_extensions(provider),
                validations=_required("system.model.toast.upload_required"),
            )
        ]
    if source == "huggingface":
        return [
            _field(
                "hf_repo",
                "system.model.form.hf_repo.label",
                placeholder=sdk.i18n.t("system.model.form.hf_repo.placeholder"),
                validations=_required("system.model.toast.hf_required"),
            ),
            _field("hf_revision", "system.model.form.hf_revision.label", value="main"),
            _field("hf_snapshot", "system.model.form.hf_snapshot.label", "toggle", value=False),
        ]
    return []


def _runtime_fields(template: dict[str, Any]) -> list[dict]:
    defaults = runtime_defaults(template)
    fields: list[dict] = []
    for field in list(runtime_options_schema(template).get("fields") or []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        item = dict(field)
        if item.get("type") in {"boolean", "bool"}:
            item["type"] = "checkbox"
        item["value"] = defaults.get(name, item.get("default", item.get("value")))
        fields.append(item)
    return fields


def _form_model(source: str, provider: str, template: dict[str, Any]) -> list[dict]:
    fields = _base_fields(provider)
    if source == "huggingface":
        name_field, label_field, format_field, capabilities_field = fields
        hf_repo_field, hf_revision_field, hf_snapshot_field = _source_fields(source, provider)
        name_field["span"] = 1
        label_field["span"] = 1
        hf_repo_field["span"] = 2
        hf_revision_field["span"] = 1
        resolved = [
            _row(name_field, label_field),
            format_field,
            capabilities_field,
            _row(hf_repo_field, hf_revision_field),
            hf_snapshot_field,
        ]
    else:
        resolved = [*fields, *_source_fields(source, provider)]
    resolved.extend(_runtime_fields(template))
    resolved.append(
        _field(
            "summary",
            "system.model.form.summary.label",
            "textarea",
            placeholder=sdk.i18n.t("system.model.form.summary.placeholder"),
        )
    )
    return resolved


async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    source = str(route_params.get("source") or "").strip()
    instance_id = int(route_params["id"])
    engine = sdk.models.engine_registry.view(instance_id)
    provider = str((engine or {}).get("provider") or "").strip().lower()
    if source not in _ROUTE_SOURCE_KIND or not provider_supports_inventory_import(provider):
        return None

    builder = sdk.ui.load("utils/ui/yaml/engine/import/form")
    definition = provider_definition(provider)
    title_key = f"system.model.manual_import.{source}.title"
    template = await engine_import_runtime_template(
        sdk,
        provider,
        source_kind=_ROUTE_SOURCE_KIND[source],
    )
    builder.set_data(
        "/engine/model/import",
        {
            "provider_label": str(definition.get("label") or provider),
        },
    )

    title = builder.get_component("engine_model_import_title")
    if title is not None:
        title.set_property("text", sdk.i18n.t(title_key))

    form = builder.get_component("engine_model_import_form")
    if form is not None:
        form.set_property("model", _form_model(source, provider, template))
        form.set_action(
            "system.create_engine_available_model",
            {
                "engine_id": instance_id,
                "provider": provider,
                "source_kind": _ROUTE_SOURCE_KIND[source],
            },
        )

    return builder
