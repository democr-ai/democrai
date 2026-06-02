from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_ITEMS = [
    {
        "title": "Realtime logs",
        "content": "Use accordion items for related sections that do not all need to stay visible.",
        "meta": "Open by default",
        "open": True,
    },
    {
        "title": "Audit notes",
        "content": "Collapsed sections keep secondary details out of the default reading path.",
        "meta": "Secondary",
        "open": False,
    },
    {
        "title": "Context details",
        "content": "Children declared in YAML are rendered into panels by item order.",
        "open": False,
    },
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/accordion"), components=True)

    builder.set_store("/components_complex/accordion/items", _ITEMS, scope="page")
    builder.set_store("/components_complex/accordion/multiple", False, scope="page")
    builder.set_store("/components_complex/accordion/collapsible", True, scope="page")
    builder.set_store("/components_complex/accordion/items", _ITEMS, scope="global")
    builder.set_store("/components_complex/accordion/multiple", False, scope="global")
    builder.set_store("/components_complex/accordion/collapsible", True, scope="global")
    builder.set_data(
        "/components_complex/accordion_model",
        {"items": _ITEMS, "multiple": False, "collapsible": True},
    )
    builder.set_data(
        "/components_complex/accordion_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "items:\n  - title: Realtime logs",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_complex/accordion/items}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_complex/accordion/items}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_complex/accordion_model/items",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/accordion_properties",
        [
            {
                "property": "items",
                "type": "list[dict]",
                "usage": sdk.i18n.t("components.complex.accordion.property.items"),
            },
            {
                "property": "multiple",
                "type": "bool",
                "usage": sdk.i18n.t("components.complex.accordion.property.multiple"),
            },
            {
                "property": "collapsible",
                "type": "bool",
                "usage": sdk.i18n.t("components.complex.accordion.property.collapsible"),
            },
            {
                "property": "children",
                "type": "list",
                "usage": sdk.i18n.t("components.complex.accordion.property.children"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_accordion_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
