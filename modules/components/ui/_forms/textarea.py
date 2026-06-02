from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_textarea"), components=True)

    builder.set_store("/components_forms/textarea/value", "Page notes", scope="page")
    builder.set_store("/components_forms/textarea/value", "Global notes", scope="global")
    builder.set_data("/components_forms/textarea_model", {"value": "Data notes"})
    builder.set_data(
        "/components_forms/textarea_bindings",
        [
            {"binding": "Literal", "yaml": 'value: "Initial notes"', "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/textarea/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/textarea/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/textarea_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/textarea_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.textarea.property.label")},
            {"property": "value", "type": "str | binding", "usage": sdk.i18n.t("components.forms.textarea.property.value")},
            {"property": "placeholder", "type": "str", "usage": sdk.i18n.t("components.forms.textarea.property.placeholder")},
            {"property": "auto_resize", "type": "bool", "usage": sdk.i18n.t("components.forms.textarea.property.auto_resize")},
            {"property": "rows, disabled", "type": "int | bool", "usage": sdk.i18n.t("components.forms.textarea.property.layout")},
            {"property": "onChangeAction", "type": "action", "usage": sdk.i18n.t("components.forms.textarea.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_textarea_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
