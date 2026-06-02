from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AI_CAPABILITIES, AI_MODEL_FORMATS, AIModelSourceKind
from democrai.sdk.client import active_sdk as sdk


_ROUTE_SOURCE_KIND = {
    "local_file": AIModelSourceKind.UPLOAD,
    "remote_url": AIModelSourceKind.URL,
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


def _options(values: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"label": _option_label(value), "value": value} for value in values]


def _row(*children: dict, spacing: int = 12) -> dict:
    return {
        "type": "row",
        "spacing": spacing,
        "children": list(children),
    }


def _base_fields() -> list[dict]:
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
            options=_options(AI_MODEL_FORMATS),
            placeholder=sdk.i18n.t("system.model.form.format.placeholder"),
            validations=_required("system.model.form.format.required"),
        ),
        _field(
            "capabilities",
            "system.model.form.capabilities.label",
            "select",
            multiple=True,
            options=_options(AI_CAPABILITIES),
            placeholder=sdk.i18n.t("system.model.form.capabilities.placeholder"),
        ),
    ]


def _source_fields(source: str) -> list[dict]:
    if source == "local_file":
        return [
            _field(
                "artifact_file",
                "system.model.form.artifact_file.label",
                "file",
                accept=".gguf,.pt,.bin,.onnx,.json",
                validations=_required("system.model.toast.upload_required"),
            )
        ]
    if source == "remote_url":
        return [
            _field(
                "remote_url",
                "system.model.form.remote_url.label",
                placeholder=sdk.i18n.t("system.model.form.remote_url.placeholder"),
                validations=_required("system.model.toast.url_required"),
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
            _field(
                "hf_revision",
                "system.model.form.hf_revision.label",
                value="main",
            ),
            _field(
                "hf_snapshot",
                "system.model.form.hf_snapshot.label",
                "toggle",
                value=False,
            ),
        ]
    return []


def _huggingface_form_model() -> list[dict]:
    name_field, label_field, format_field, capabilities_field = _base_fields()
    hf_repo_field, hf_revision_field, hf_snapshot_field = _source_fields("huggingface")
    name_field["span"] = 1
    label_field["span"] = 1
    hf_repo_field["span"] = 2
    hf_revision_field["span"] = 1
    return [
        _row(name_field, label_field),
        format_field,
        capabilities_field,
        _row(hf_repo_field, hf_revision_field),
        hf_snapshot_field,
        _field(
            "summary",
            "system.model.form.summary.label",
            "textarea",
            placeholder=sdk.i18n.t("system.model.form.summary.placeholder"),
        ),
    ]


def _form_model(source: str) -> list[dict]:
    if source == "huggingface":
        return _huggingface_form_model()

    fields = _base_fields()
    fields.extend(_source_fields(source))
    fields.append(
        _field(
            "summary",
            "system.model.form.summary.label",
            "textarea",
            placeholder=sdk.i18n.t("system.model.form.summary.placeholder"),
        )
    )
    return fields


async def render(params: dict, session: dict):

    route_params = dict(params.get("route_params") or {})
    source = str(route_params.get("source") or "").strip()
    if source not in _ROUTE_SOURCE_KIND:
        source = "local_file"

    builder = sdk.ui.load("utils/ui/yaml/models/import/form")
    title_key = f"system.model.manual_import.{source}.title"

    title = builder.get_component("system_model_import_title")
    if title is not None:
        title.set_property("text", sdk.i18n.t(title_key))

    form = builder.get_component("system_model_import_form")
    if form is not None:
        form.set_property("model", _form_model(source))
        form.set_action(
            "system.create_available_model",
            {"source_kind": _ROUTE_SOURCE_KIND[source]},
        )

    return builder
