from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_OPTIONS = [
    {"label": "Draft", "value": "draft"},
    {"label": "Published", "value": "published"},
    {"label": "Archived", "value": "archived"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_select"), components=True)

    builder.set_store("/components_forms/select/value", "draft", scope="page")
    builder.set_store("/components_forms/select/value", "draft", scope="global")
    builder.set_data("/components_forms/select_model", {"value": "draft"})
    builder.set_data("/components_forms/select_options", _OPTIONS)
    builder.set_data(
        "/components_forms/select_bindings",
        [
            {"binding": "Literal", "yaml": "value: draft", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/select/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/select/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/select_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/select_properties",
        [
            {"property": "label", "type": "str", "usage": sdk.i18n.t("components.forms.select.property.label")},
            {"property": "options", "type": "list[dict]", "usage": sdk.i18n.t("components.forms.select.property.options")},
            {"property": "value", "type": "str | list[str] | binding", "usage": sdk.i18n.t("components.forms.select.property.value")},
            {"property": "placeholder", "type": "str", "usage": sdk.i18n.t("components.forms.select.property.placeholder")},
            {"property": "multiple, searchable, max_width", "type": "bool | int", "usage": sdk.i18n.t("components.forms.select.property.flags")},
            {"property": "action, params", "type": "action", "usage": sdk.i18n.t("components.forms.select.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_select_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
