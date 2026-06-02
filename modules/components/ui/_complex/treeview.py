from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_NODES = [
    {
        "id": "workspace",
        "label": "Workspace",
        "expanded": True,
        "selectable": False,
        "children": [
            {
                "id": "overview",
                "type": "nav",
                "label": "Overview",
                "path": "/components/index",
                "icon": "ric.home-2-line",
                "value": "overview",
            },
            {
                "id": "treeview",
                "type": "nav",
                "label": "TreeView",
                "path": "/components/_complex/treeview",
                "icon": "ric.node-tree",
                "value": "treeview",
            },
            {"id": "locked", "label": "Locked branch", "selectable": False},
            {"id": "disabled", "label": "Disabled item", "disabled": True},
        ],
    }
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/treeview"), components=True)

    for scope in ("page", "global"):
        builder.set_store("/components_complex/treeview/nodes", _NODES, scope=scope)
        builder.set_store("/components_complex/treeview/active_id", "treeview", scope=scope)
        builder.set_store("/components_complex/treeview/expand_all", False, scope=scope)
        builder.set_store("/components_complex/treeview/click_mode", "single", scope=scope)
        builder.set_store("/components_complex/treeview/selection_mode", "single", scope=scope)
    builder.set_store("/components_complex/treeview/selected", "No selection yet", scope="page")
    builder.set_data(
        "/components_complex/treeview_model",
        {
            "nodes": _NODES,
            "active_id": "treeview",
            "expand_all": False,
            "click_mode": "single",
            "selection_mode": "single",
        },
    )
    builder.set_data(
        "/components_complex/treeview_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "nodes:\n  - id: workspace\n    children: [...]",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_complex/treeview/nodes}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_complex/treeview/nodes}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_complex/treeview_model/nodes",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/treeview_properties",
        [
            {"property": "nodes", "type": "list[dict]", "usage": sdk.i18n.t("components.complex.treeview.property.nodes")},
            {"property": "click_action", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.treeview.property.click_action")},
            {"property": "select_action", "type": "str | ActionSpec", "usage": sdk.i18n.t("components.complex.treeview.property.select_action")},
            {"property": "params", "type": "dict", "usage": sdk.i18n.t("components.complex.treeview.property.params")},
            {"property": "expand_all", "type": "bool", "usage": sdk.i18n.t("components.complex.treeview.property.expand_all")},
            {"property": "click_mode", "type": "single | double | none", "usage": sdk.i18n.t("components.complex.treeview.property.click_mode")},
            {"property": "selection_mode", "type": "single | multiple | none", "usage": sdk.i18n.t("components.complex.treeview.property.selection_mode")},
            {"property": "active_id", "type": "str | list[str]", "usage": sdk.i18n.t("components.complex.treeview.property.active_id")},
            {"property": "active_as_selection", "type": "bool", "usage": sdk.i18n.t("components.complex.treeview.property.active_as_selection")},
            {"property": "min_height", "type": "int", "usage": sdk.i18n.t("components.complex.treeview.property.min_height")},
            {"property": "full_height", "type": "bool", "usage": sdk.i18n.t("components.complex.treeview.property.full_height")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_treeview_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
