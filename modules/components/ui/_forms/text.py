from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_textfield"), components=True)

    builder.set_store("/components_forms/textfield/value", "Page text", scope="page")
    builder.set_store("/components_forms/textfield/value", "Global text", scope="global")
    builder.set_data("/components_forms/textfield_model", {"value": "Data text"})
    builder.set_data(
        "/components_forms/textfield_bindings",
        [
            {"binding": "Literal", "yaml": 'value: "Draft title"', "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/textfield/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/textfield/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/textfield_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/textfield_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.textfield.property.label")},
            {"property": "value", "type": "str | binding", "usage": sdk.i18n.t("components.forms.textfield.property.value")},
            {"property": "placeholder", "type": "str", "usage": sdk.i18n.t("components.forms.textfield.property.placeholder")},
            {"property": "password", "type": "bool", "usage": sdk.i18n.t("components.forms.textfield.property.password")},
            {"property": "action, onChangeAction, onChangeMode", "type": "action", "usage": sdk.i18n.t("components.forms.textfield.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_textfield_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
