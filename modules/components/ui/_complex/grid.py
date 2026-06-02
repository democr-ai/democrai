from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/grid"), components=True)

    builder.set_data(
        "/components_complex/grid_actions",
        [
            {
                "action": "components.add_widget",
                "payload": "{grid_id, size, row, col}",
                "usage": sdk.i18n.t("components.complex.grid.action.add"),
            },
            {
                "action": "components.move_widget",
                "payload": "{id, grid_id, row, col}",
                "usage": sdk.i18n.t("components.complex.grid.action.move"),
            },
            {
                "action": "components.remove_widget",
                "payload": "{widget_id, grid_id}",
                "usage": sdk.i18n.t("components.complex.grid.action.remove"),
            },
            {
                "action": "components.toggle_edit_mode",
                "payload": "{grid_id, checked}",
                "usage": sdk.i18n.t("components.complex.grid.action.toggle"),
            },
            {
                "action": "components.reset_grid",
                "payload": "{grid_id}",
                "usage": sdk.i18n.t("components.complex.grid.action.reset"),
            },
        ],
    )
    builder.set_data(
        "/components_complex/grid_properties",
        [
            {
                "property": "GridDropZone.columns / rows",
                "type": "int",
                "usage": sdk.i18n.t("components.complex.grid.property.columns_rows"),
            },
            {
                "property": "GridDropZone.insertable_items",
                "type": "list[{label, size}]",
                "usage": sdk.i18n.t("components.complex.grid.property.insertable_items"),
            },
            {
                "property": "GridDropZone.edit_mode",
                "type": "bool",
                "usage": sdk.i18n.t("components.complex.grid.property.edit_mode"),
            },
            {
                "property": "GridDropZone.add_action / move_action",
                "type": "str",
                "usage": sdk.i18n.t("components.complex.grid.property.actions"),
            },
            {
                "property": "GridDropZone.children",
                "type": "list[str | Component]",
                "usage": sdk.i18n.t("components.complex.grid.property.children"),
            },
            {
                "property": "DashboardWidget.size",
                "type": "square | rect_h | rect_v | large",
                "usage": sdk.i18n.t("components.complex.grid.property.size"),
            },
            {
                "property": "DashboardWidget.coords",
                "type": "[row, col]",
                "usage": sdk.i18n.t("components.complex.grid.property.coords"),
            },
            {
                "property": "DashboardWidget.title",
                "type": "str",
                "usage": sdk.i18n.t("components.complex.grid.property.title"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_complex_grid_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
