from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_ITEMS = [
    {
        "id": "task_pipeline",
        "title": "Nightly pipeline",
        "text": "Check the latest execution report.",
        "icon": "ric.task-line",
        "status": "ready",
        "owner": "Runtime",
        "selectable": True,
        "show_badge": True,
    },
    {
        "id": "task_permissions",
        "title": "Permission sync",
        "text": "Validate module permission rules.",
        "icon": "ric.shield-check-line",
        "status": "review",
        "owner": "Security",
        "selectable": True,
        "show_badge": True,
        "active": True,
    },
    {
        "id": "task_locked",
        "title": "Locked item",
        "text": "Visible but not selectable.",
        "icon": "ric.lock-line",
        "status": "locked",
        "owner": "System",
        "selectable": False,
        "show_badge": False,
    },
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/list"), components=True)

    for scope in ("page", "global"):
        builder.set_store("/components_complex/list/items", _ITEMS, scope=scope)
    builder.set_data(
        "/components_complex/list_model",
        {"items": _ITEMS},
    )
    builder.set_data(
        "/components_complex/list_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "data_source:\n  type: inline\n  data: [...]",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "data_source:\n  type: binding\n  data: {type: store, scope: page, path: /components_complex/list/items}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "data_source:\n  type: binding\n  data: {type: store, scope: global, path: /components_complex/list/items}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "data_source:\n  type: binding\n  data: @data/components_complex/list_model/items",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_complex/list_properties",
        [
            {"property": "dataSource", "type": "dict", "usage": sdk.i18n.t("components.complex.list.property.data_source")},
            {"property": "itemTemplate", "type": "Component", "usage": sdk.i18n.t("components.complex.list.property.item_template")},
            {"property": "template", "type": "text | title_text | custom", "usage": sdk.i18n.t("components.complex.list.property.template")},
            {"property": "orientation", "type": "vertical | horizontal", "usage": sdk.i18n.t("components.complex.list.property.orientation")},
            {"property": "selectable", "type": "bool | rule", "usage": sdk.i18n.t("components.complex.list.property.selectable")},
            {"property": "onItemClick", "type": "ActionSpec", "usage": sdk.i18n.t("components.complex.list.property.on_item_click")},
            {"property": "itemActions", "type": "list[ActionDef]", "usage": sdk.i18n.t("components.complex.list.property.item_actions")},
            {"property": "selectedItemsAction", "type": "ActionSpec", "usage": sdk.i18n.t("components.complex.list.property.selected_items_action")},
            {"property": "selectedItemsActionLabel", "type": "str", "usage": sdk.i18n.t("components.complex.list.property.selected_items_action_label")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_list_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
