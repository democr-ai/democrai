from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


def _audio_source(value: str) -> str:
    return sdk.ui.resolve_media_source(value, component_type="Audio", field="source")


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/audio"), components=True)

    builder.set_store(
        "/components_media/audio/source",
        _audio_source("assets/test.mp3"),
        scope="page",
    )
    builder.set_store("/components_media/audio/title", "T-Rex Roar", scope="page")
    builder.set_store(
        "/components_media/audio/source",
        _audio_source("assets/test.mp3"),
        scope="global",
    )
    builder.set_store("/components_media/audio/title", "Global T-Rex Roar", scope="global")
    builder.set_data(
        "/components_media/audio_model",
        {"source": _audio_source("assets/test.mp3"), "title": "Data T-Rex Roar"},
    )
    builder.set_data(
        "/components_media/audio_bindings",
        [
            {
                "binding": sdk.i18n.t("components.media.binding.literal"),
                "yaml": 'source: "assets/test.mp3"',
                "source": sdk.i18n.t("components.media.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.media.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_media/audio/source}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("components.media.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_media/audio/source}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("components.media.binding.data"),
                "yaml": "@data/components_media/audio_model/source",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_media/audio_properties",
        [
            {
                "property": "source",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.audio.property.source"),
            },
            {
                "property": "title",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.audio.property.title"),
            },
            {
                "property": "autoplay, muted, loop",
                "type": "bool",
                "usage": sdk.i18n.t("components.media.audio.property.flags"),
            },
            {
                "property": "poster",
                "type": "str | binding",
                "usage": sdk.i18n.t("components.media.audio.property.poster"),
            },
            {
                "property": "controls, width, height",
                "type": "bool | int",
                "usage": sdk.i18n.t("components.media.audio.property.static"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_media_audio_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
