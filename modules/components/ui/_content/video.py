from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


def _video_source(value: str) -> str:
    return sdk.ui.resolve_media_source(value, component_type="Video", field="source")


def _video_poster(value: str) -> str:
    return sdk.ui.resolve_media_source(value, component_type="Video", field="poster")


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/video"), components=True)

    builder.set_store(
        "/components_media/video/source",
        _video_source("assets/test.mp4"),
        scope="page",
    )
    builder.set_store("/components_media/video/title", "Flower MP4", scope="page")
    builder.set_store(
        "/components_media/video/poster",
        _video_poster("assets/demo-image.png"),
        scope="page",
    )
    builder.set_store(
        "/components_media/video/source",
        _video_source("assets/test.mp4"),
        scope="global",
    )
    builder.set_store("/components_media/video/title", "Global Flower MP4", scope="global")
    builder.set_store(
        "/components_media/video/poster",
        _video_poster("assets/demo-image.png"),
        scope="global",
    )
    builder.set_data(
        "/components_media/video_model",
        {
            "source": _video_source("assets/test.mp4"),
            "title": "Data Flower MP4",
            "poster": _video_poster("assets/demo-image.png"),
        },
    )
    builder.set_data(
        "/components_media/video_bindings",
        [
            {
                "binding": sdk.i18n.t("components.media.binding.literal"),
                "yaml": 'source: "assets/test.mp4"',
                "source": sdk.i18n.t("components.media.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.media.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_media/video/source}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("components.media.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_media/video/source}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("components.media.binding.data"),
                "yaml": "@data/components_media/video_model/source",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_media/video_properties",
        [
            {
                "property": "source",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.video.property.source"),
            },
            {
                "property": "title",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.video.property.title"),
            },
            {
                "property": "poster",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.video.property.poster"),
            },
            {
                "property": "autoplay, muted, loop",
                "type": "bool",
                "usage": sdk.i18n.t("components.media.video.property.flags"),
            },
            {
                "property": "controls, width, height",
                "type": "bool | int",
                "usage": sdk.i18n.t("components.media.video.property.static"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_media_video_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
