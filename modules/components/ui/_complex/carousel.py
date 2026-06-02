from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_SLIDES = [
    {
        "id": "slide_runtime",
        "eyebrow": "Release 2.4",
        "title": "Runtime hardening",
        "desc": "Sandbox checks and stream bindings are ready for review.",
        "cta": "Inspect",
    },
    {
        "id": "slide_charts",
        "eyebrow": "Telemetry",
        "title": "GPU tracking",
        "desc": "A publisher can push incremental data into chart streams.",
        "cta": "Open stream",
    },
    {
        "id": "slide_chat",
        "eyebrow": "AI",
        "title": "Component messages",
        "desc": "Chat messages can carry flat component payloads.",
        "cta": "Review",
    },
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/carousel"), components=True)

    for scope in ("page", "global"):
        builder.set_store("/components_complex/carousel/slides", _SLIDES, scope=scope)
    builder.set_data(
        "/components_complex/carousel_model",
        {"slides": _SLIDES},
    )
    builder.set_data(
        "/components_complex/carousel_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "data_source:\n  type: inline\n  data: [...]",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "data_source:\n  type: binding\n  data: {type: store, scope: page, path: /components_complex/carousel/slides}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "data_source:\n  type: binding\n  data: {type: store, scope: global, path: /components_complex/carousel/slides}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "data_source:\n  type: binding\n  data: @data/components_complex/carousel_model/slides",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/carousel_properties",
        [
            {"property": "dataSource", "type": "dict", "usage": sdk.i18n.t("components.complex.carousel.property.data_source")},
            {"property": "itemTemplate", "type": "Component", "usage": sdk.i18n.t("components.complex.carousel.property.item_template")},
            {"property": "onItemClick", "type": "ActionSpec", "usage": sdk.i18n.t("components.complex.carousel.property.on_item_click")},
            {"property": "onChange", "type": "ActionSpec", "usage": sdk.i18n.t("components.complex.carousel.property.on_change")},
            {"property": "activeIndex", "type": "int", "usage": sdk.i18n.t("components.complex.carousel.property.active_index")},
            {"property": "autoplay", "type": "bool", "usage": sdk.i18n.t("components.complex.carousel.property.autoplay")},
            {"property": "intervalMs", "type": "int", "usage": sdk.i18n.t("components.complex.carousel.property.interval_ms")},
            {"property": "showDots", "type": "bool", "usage": sdk.i18n.t("components.complex.carousel.property.show_dots")},
            {"property": "showArrows", "type": "bool", "usage": sdk.i18n.t("components.complex.carousel.property.show_arrows")},
            {"property": "loop", "type": "bool", "usage": sdk.i18n.t("components.complex.carousel.property.loop")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_carousel_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
