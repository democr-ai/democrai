from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_EMPTY_VALUES = {"voice_sample": []}


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_audio_recorder"), components=True)

    builder.set_store("/components_forms/audio_recorder/page_values", _EMPTY_VALUES, scope="page")
    builder.set_store("/components_forms/audio_recorder/global_values", _EMPTY_VALUES, scope="global")
    builder.set_data("/components_forms/audio_recorder_model", {"values": _EMPTY_VALUES})
    builder.set_data(
        "/components_forms/audio_recorder_bindings",
        [
            {
                "binding": "Literal values",
                "yaml": "values: {voice_sample: []}",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_forms/audio_recorder/page_values}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_forms/audio_recorder/global_values}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_forms/audio_recorder_model/values",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_forms/audio_recorder_properties",
        [
            {
                "property": "type",
                "type": "audio_recorder",
                "usage": sdk.i18n.t("components.forms.audio_recorder.property.type"),
            },
            {
                "property": "name",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.audio_recorder.property.name"),
            },
            {
                "property": "label",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.audio_recorder.property.label"),
            },
            {
                "property": "value",
                "type": "list[dict]",
                "usage": sdk.i18n.t("components.forms.audio_recorder.property.value"),
            },
            {
                "property": "ingest",
                "type": "bool",
                "usage": sdk.i18n.t("components.forms.audio_recorder.property.ingest"),
            },
            {
                "property": "validations",
                "type": "list[dict]",
                "usage": sdk.i18n.t("components.forms.audio_recorder.property.validations"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_audio_recorder_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
