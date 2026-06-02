from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_CAPABILITY_OPTIONS = [
    {"label": "Chat", "value": "chat"},
    {"label": "Tool Calling", "value": "tool_calling"},
    {"label": "Reasoning", "value": "reasoning"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/form_editable_list"), components=True)

    builder.set_store("/components_forms/editable_list/value", ["chat"], scope="page")
    builder.set_store("/components_forms/editable_list/value", ["chat"], scope="global")
    builder.set_data("/components_forms/editable_list_model", {"value": ["chat"]})
    builder.set_data("/components_forms/capability_options", _CAPABILITY_OPTIONS)
    builder.set_data(
        "/components_forms/editable_list_bindings",
        [
            {"binding": "Literal", "yaml": "value: [chat]", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_forms/editable_list/value}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_forms/editable_list/value}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_forms/editable_list_model/value", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_forms/editable_list_properties",
        [
            {"property": "value", "type": "list[str] | binding", "usage": sdk.i18n.t("components.forms.editable_list.property.value")},
            {"property": "item_label", "type": "str", "usage": sdk.i18n.t("components.forms.editable_list.property.item_label")},
            {"property": "add_label, remove_label, submit_label", "type": "str", "usage": sdk.i18n.t("components.forms.editable_list.property.labels")},
            {"property": "placeholder", "type": "str", "usage": sdk.i18n.t("components.forms.editable_list.property.placeholder")},
            {"property": "item_schema", "type": "dict", "usage": sdk.i18n.t("components.forms.editable_list.property.schema")},
            {"property": "action, params, track_loading", "type": "action", "usage": sdk.i18n.t("components.forms.editable_list.property.actions")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_forms_editable_list_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
