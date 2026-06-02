from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_OPTIONS = [
    {"label": "Small", "value": "small"},
    {"label": "Medium", "value": "medium"},
    {"label": "Large", "value": "large"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_radio"), components=True)

    builder.set_store("/components_forms/radio/value", "small", scope="page")
    builder.set_store("/components_forms/radio/value", "small", scope="global")
    builder.set_data("/components_forms/radio_model", {"value": "small"})
    builder.set_data("/components_forms/radio_options", _OPTIONS)
    builder.set_data(
        "/components_forms/radio_bindings",
        [
            {"binding": "Literal", "yaml": "value: small", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/radio/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/radio/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/radio_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/radio_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.radio.property.label")},
            {"property": "options", "type": "list[dict]", "usage": sdk.i18n.t("components.forms.radio.property.options")},
            {"property": "value", "type": "str | binding", "usage": sdk.i18n.t("components.forms.radio.property.value")},
            {"property": "action", "type": "action", "usage": sdk.i18n.t("components.forms.radio.property.actions")},
            {"property": "options_action, options_store", "type": "str | None", "usage": sdk.i18n.t("components.forms.radio.property.sources")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_radio_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
