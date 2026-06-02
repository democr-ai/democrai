from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/qrcode"), components=True)

    builder.set_store(
        "/components_content/qrcode/content",
        "https://democrai.example/page",
        scope="page",
    )
    builder.set_store(
        "/components_content/qrcode/content",
        "https://democrai.example/global",
        scope="global",
    )
    builder.set_data(
        "/components_content/qrcode_model",
        {"content": "https://democrai.example/data"},
    )
    builder.set_data(
        "/components_content/qrcode_bindings",
        [
            {
                "binding": sdk.i18n.t("components.content.binding.literal"),
                "yaml": 'content: "https://democrai.example"',
                "source": sdk.i18n.t("components.content.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.content.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_content/qrcode/content}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("components.content.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_content/qrcode/content}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("components.content.binding.data"),
                "yaml": "@data/components_content/qrcode_model/content",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_content/qrcode_properties",
        [
            {
                "property": "content",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.content.qrcode.property.content"),
            },
            {
                "property": "size",
                "type": "int",
                "usage": sdk.i18n.t("components.content.qrcode.property.size"),
            },
            {
                "property": "border",
                "type": "int",
                "usage": sdk.i18n.t("components.content.qrcode.property.border"),
            },
            {
                "property": "fill_color, back_color",
                "type": "str",
                "usage": sdk.i18n.t("components.content.qrcode.property.colors"),
            },
            {
                "property": "style, show_if, hide_if, required_permissions",
                "type": "layout/visibility",
                "usage": sdk.i18n.t("components.content.property.common"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_qrcode_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
