from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_RUNTIME = {
    "variant": "outlined",
    "padding": [18, 18, 18, 18],
    "title": "Runtime card",
    "body": "This card reads visual props and child text from a binding source.",
}


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/card"), components=True)

    builder.set_store("/components_complex/card/variant", _RUNTIME["variant"], scope="page")
    builder.set_store("/components_complex/card/padding", _RUNTIME["padding"], scope="page")
    builder.set_store("/components_complex/card/title", _RUNTIME["title"], scope="page")
    builder.set_store("/components_complex/card/body", _RUNTIME["body"], scope="page")
    builder.set_store("/components_complex/card/variant", _RUNTIME["variant"], scope="global")
    builder.set_store("/components_complex/card/padding", _RUNTIME["padding"], scope="global")
    builder.set_store("/components_complex/card/title", _RUNTIME["title"], scope="global")
    builder.set_store("/components_complex/card/body", _RUNTIME["body"], scope="global")
    builder.set_data("/components_complex/card_model", _RUNTIME)
    builder.set_data(
        "/components_complex/card_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "variant: outlined\npadding: [18, 18, 18, 18]",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_complex/card/variant}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_complex/card/variant}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_complex/card_model/variant",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/card_properties",
        [
            {
                "property": "children",
                "type": "list[str | Component]",
                "usage": sdk.i18n.t("components.complex.card.property.children"),
            },
            {
                "property": "variant",
                "type": "elevated | outlined | flat",
                "usage": sdk.i18n.t("components.complex.card.property.variant"),
            },
            {
                "property": "background_image",
                "type": "str",
                "usage": sdk.i18n.t("components.complex.card.property.background_image"),
            },
            {
                "property": "itemActions",
                "type": "list[dict]",
                "usage": sdk.i18n.t("components.complex.card.property.item_actions"),
            },
            {
                "property": "data",
                "type": "dict",
                "usage": sdk.i18n.t("components.complex.card.property.data"),
            },
            {
                "property": "padding",
                "type": "[top, right, bottom, left]",
                "usage": sdk.i18n.t("components.complex.card.property.padding"),
            },
            {
                "property": "visible",
                "type": "bool",
                "usage": sdk.i18n.t("components.complex.card.property.visible"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_card_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
