from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


def _image_source(value: str) -> str:
    return sdk.ui.resolve_media_source(value, component_type="Image", field="url")


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/image"), components=True)

    builder.set_store("/components_media/image/alt", "Mountain lake", scope="page")
    builder.set_store(
        "/components_media/image/url",
        _image_source("assets/demo-image.png"),
        scope="page",
    )
    builder.set_store("/components_media/image/width", 280, scope="page")
    builder.set_store("/components_media/image/height", 180, scope="page")
    builder.set_store("/components_media/image/alt", "Global mountain lake", scope="global")
    builder.set_store(
        "/components_media/image/url",
        _image_source("assets/demo-image.png"),
        scope="global",
    )
    builder.set_store("/components_media/image/width", 280, scope="global")
    builder.set_store("/components_media/image/height", 180, scope="global")
    builder.set_data(
        "/components_media/image_model",
        {
            "alt": "Data mountain lake",
            "url": _image_source("assets/demo-image.png"),
            "width": 280,
            "height": 180,
        },
    )
    builder.set_data(
        "/components_media/image_bindings",
        [
            {
                "binding": sdk.i18n.t("components.media.binding.literal"),
                "yaml": 'url: "assets/demo-image.png"',
                "source": sdk.i18n.t("components.media.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.media.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_media/image/url}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("components.media.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_media/image/url}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("components.media.binding.data"),
                "yaml": "@data/components_media/image_model/url",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_media/image_properties",
        [
            {
                "property": "alt",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.image.property.alt"),
            },
            {
                "property": "url",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.image.property.url"),
            },
            {
                "property": "width, height",
                "type": "int | binding",
                "usage": sdk.i18n.t("components.media.image.property.size"),
            },
            {
                "property": "lazy",
                "type": "bool",
                "usage": sdk.i18n.t("components.media.image.property.lazy"),
            },
            {
                "property": "fit",
                "type": "str",
                "usage": sdk.i18n.t("components.media.image.property.fit"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_media_image_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
