from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_checkbox"), components=True)

    builder.set_store("/components_forms/checkbox/checked", False, scope="page")
    builder.set_store("/components_forms/checkbox/checked", False, scope="global")
    builder.set_data("/components_forms/checkbox_model", {"checked": False})
    builder.set_data(
        "/components_forms/checkbox_bindings",
        [
            {"binding": "Literal", "yaml": "checked: false", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/checkbox/checked}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/checkbox/checked}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/checkbox_model/checked", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/checkbox_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.checkbox.property.label")},
            {"property": "checked", "type": "bool | binding", "usage": sdk.i18n.t("components.forms.checkbox.property.checked")},
            {"property": "action, params", "type": "action", "usage": sdk.i18n.t("components.forms.checkbox.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_checkbox_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
