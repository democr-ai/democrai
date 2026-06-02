from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_PAGE_TABS = [
    {"id": "components_complex_tabs_page_overview", "label": "Overview", "icon": "ric.home-2-line"},
    {"id": "components_complex_tabs_page_activity", "label": "Activity", "icon": "ric.history-line"},
]
_GLOBAL_TABS = [
    {"id": "components_complex_tabs_global_overview", "label": "Overview", "icon": "ric.home-2-line"},
    {"id": "components_complex_tabs_global_activity", "label": "Activity", "icon": "ric.history-line"},
]
_DATA_TABS = [
    {"id": "components_complex_tabs_data_overview", "label": "Overview", "icon": "ric.home-2-line"},
    {"id": "components_complex_tabs_data_activity", "label": "Activity", "icon": "ric.history-line"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/tabs"), components=True)

    builder.set_store("/components_complex/tabs/items", _PAGE_TABS, scope="page")
    builder.set_store("/components_complex/tabs/items", _GLOBAL_TABS, scope="global")
    builder.set_data("/components_complex/tabs_model", {"tabs": _DATA_TABS})
    builder.set_data(
        "/components_complex/tabs_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "tabs:\n  - {id: overview, label: Overview}",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_complex/tabs/items}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_complex/tabs/items}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_complex/tabs_model/tabs",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/tabs_properties",
        [
            {
                "property": "children",
                "type": "list",
                "usage": sdk.i18n.t("components.complex.tabs.property.children"),
            },
            {
                "property": "tabs",
                "type": "list[TabDef]",
                "usage": sdk.i18n.t("components.complex.tabs.property.tabs"),
            },
            {
                "property": "stretch",
                "type": "bool",
                "usage": sdk.i18n.t("components.complex.tabs.property.stretch"),
            },
            {
                "property": "style",
                "type": "str",
                "usage": sdk.i18n.t("components.complex.tabs.property.style"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_tabs_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
