from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/button"), components=True)

    builder.set_data(
        "/components_forms/button_properties",
        [
            {
                "property": "label",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.label"),
            },
            {
                "property": "action",
                "type": "str | object",
                "usage": sdk.i18n.t("components.forms.button.property.action"),
            },
            {
                "property": "params",
                "type": "dict",
                "usage": sdk.i18n.t("components.forms.button.property.params"),
            },
            {
                "property": "icon",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.icon"),
            },
            {
                "property": "variant",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.variant"),
            },
            {
                "property": "mode",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.mode"),
            },
            {
                "property": "appearance",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.appearance"),
            },
            {
                "property": "btnsize",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.btnsize"),
            },
            {
                "property": "shape",
                "type": "str",
                "usage": sdk.i18n.t("components.forms.button.property.shape"),
            },
            {
                "property": "active",
                "type": "bool",
                "usage": sdk.i18n.t("components.forms.button.property.active"),
            },
            {
                "property": "collect_input_ids",
                "type": "list[str]",
                "usage": sdk.i18n.t("components.forms.button.property.collect"),
            },
            {
                "property": "track_loading",
                "type": "str | list[str]",
                "usage": sdk.i18n.t("components.forms.button.property.track_loading"),
            },
            {
                "property": "show_if, hide_if, required_permissions",
                "type": "visibility",
                "usage": sdk.i18n.t("components.forms.button.property.visibility"),
            },
            {
                "property": "capabilities",
                "type": "list[str]",
                "usage": sdk.i18n.t("components.forms.button.property.capabilities"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_form_button_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
