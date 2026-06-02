from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/progress"), components=True)

    builder.set_store("/components_content/progress/value", 25, scope="page")
    builder.set_store("/components_content/progress/maximum", 100, scope="page")
    builder.set_store("/components_content/progress/label", "Queued", scope="page")
    builder.set_store("/components_content/progress/show_label", True, scope="page")
    builder.set_store("/components_content/progress/value", 35, scope="global")
    builder.set_store("/components_content/progress/maximum", 100, scope="global")
    builder.set_store("/components_content/progress/label", "Global queued", scope="global")
    builder.set_store("/components_content/progress/show_label", True, scope="global")
    builder.set_data(
        "/components_content/progress_model",
        {
            "value": 45,
            "maximum": 100,
            "label": "Data-model progress",
            "show_label": True,
        },
    )
    builder.set_data(
        "/components_content/progress_bindings",
        [
            {
                "binding": sdk.i18n.t("components.content.binding.literal"),
                "yaml": "value: 68",
                "source": sdk.i18n.t("components.content.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.content.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_content/progress/value}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("components.content.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_content/progress/value}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("components.content.binding.data"),
                "yaml": "@data/components_content/progress_model/value",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_content/progress_properties",
        [
            {
                "property": "value",
                "type": "int | binding",
                "usage": sdk.i18n.t("components.content.progress.property.value"),
            },
            {
                "property": "maximum",
                "type": "int | binding",
                "usage": sdk.i18n.t("components.content.progress.property.maximum"),
            },
            {
                "property": "label",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.content.progress.property.label"),
            },
            {
                "property": "show_label",
                "type": "bool | binding",
                "usage": sdk.i18n.t("components.content.progress.property.show_label"),
            },
            {
                "property": "style, show_if, hide_if, required_permissions",
                "type": "layout/visibility",
                "usage": sdk.i18n.t("components.content.property.common"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_progress_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
