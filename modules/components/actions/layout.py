from __future__ import annotations

from democrai.sdk.auth import permission_required
from uuid import uuid4

from democrai.sdk.decorators import action


def _badge(sdk, component_id: str, text: str, variant: str = "info") -> dict:
    return sdk.ui.Badge(component_id, text, variant=variant).to_dict()


def _state_update(sdk, scope: str, values: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [{"stateUpdate": {"scope": scope, "values": values}}]
        )
    )


def _data_update(sdk, surface_id: str, data: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                sdk.ui.Builder.build_data_model_update_payload(
                    surface_id=surface_id,
                    data=data,
                )
            ]
        )
    )


def _row_child(sdk, component_id: str, text: str, variant: str = "warning") -> dict:
    return _badge(sdk, component_id, text, variant)


def _header_slot_item(sdk, component_id: str, slot: str, strategy: str) -> dict:
    text = sdk.i18n.t(f"components.layout.header.slot_{slot}")
    if slot == "left":
        return _badge(sdk, component_id, f"{strategy} {text}", "info")
    if slot == "center":
        return sdk.ui.Text(component_id, f"{strategy} {text}").to_dict()
    return _badge(sdk, component_id, f"{strategy} {text}", "success")


def _header_slot_items(sdk, slot: str, strategy: str) -> list[dict]:
    return [
        _badge(
            sdk,
            f"components_layout_header_{strategy.lower()}_{slot}_initial",
            sdk.i18n.t(f"components.layout.header.slot_{slot}"),
            "secondary",
        ),
        _header_slot_item(
            sdk,
            f"components_layout_header_{strategy.lower()}_{slot}_added",
            slot,
            strategy,
        ),
    ]


@action("layout_update")
@permission_required(["components.documentation.view"])
async def layout_update(ctx: dict, session: dict, sdk) -> dict:
    component = str(ctx.get("component") or "")
    mode = str(ctx.get("mode") or "")
    prop = str(ctx.get("prop") or "")
    slot = str(ctx.get("slot") or "")
    surface_id = str(ctx.get("_surface_id") or "main")

    if component == "row":
        if prop == "children":
            if mode == "direct":
                item_id = f"components_layout_row_direct_added_{uuid4().hex}"
                return sdk.effects.respond(
                    sdk.effects.ui_collection_append(
                        "components_layout_row_children_direct",
                        "children",
                        _row_child(
                            sdk,
                            item_id,
                            sdk.i18n.t("components.layout.item.direct_added"),
                            "warning",
                        ),
                        surface_id=surface_id,
                    )
                )

        if prop == "align":
            if mode == "page_store":
                return _state_update(
                    sdk, "page", {"/components_layout/row_align": "center"}
                )
            if mode == "global_store":
                return _state_update(
                    sdk, "global", {"/components_layout/row_align": "right"}
                )
            if mode == "data":
                return _data_update(
                    sdk,
                    surface_id,
                    {"components_layout": {"row_model": {"align": "center"}}},
                )

        if mode == "store":
            return _state_update(sdk, "page", {"/components_layout/row_spacing": 22})
        if mode == "data":
            return _data_update(
                sdk,
                surface_id,
                {"components_layout": {"row_model": {"spacing": 30}}},
            )
        if mode == "direct":
            return sdk.effects.respond(
                sdk.effects.ui_property_update(
                    "components_layout_row_direct", "spacing", 26, surface_id=surface_id
                )
            )

    if component == "column":
        style = "padding: 14px; border: 1px solid #4f7cff; border-radius: 6px;"
        if prop == "children" and mode == "direct":
            item_id = f"components_layout_column_direct_added_{uuid4().hex}"
            return sdk.effects.respond(
                sdk.effects.ui_collection_append(
                    "components_layout_column_children_direct",
                    "children",
                    _badge(
                        sdk,
                        item_id,
                        sdk.i18n.t("components.layout.item.direct_added"),
                        "warning",
                    ),
                    surface_id=surface_id,
                )
            )
        if mode == "store":
            return _state_update(sdk, "page", {"/components_layout/column_style": style})
        if mode == "global_store":
            return _state_update(sdk, "global", {"/components_layout/column_style": style})
        if mode == "data":
            return _data_update(
                sdk,
                surface_id,
                {"components_layout": {"column_model": {"style": style}}},
            )
        if mode == "direct":
            return sdk.effects.respond(
                sdk.effects.ui_property_update(
                    "components_layout_column_direct", "style", style, surface_id=surface_id
                )
            )

    if component == "flex":
        style = "padding: 14px; border: 1px solid #4f7cff; border-radius: 6px;"
        if prop == "children" and mode == "direct":
            item_id = f"components_layout_flex_direct_added_{uuid4().hex}"
            return sdk.effects.respond(
                sdk.effects.ui_collection_append(
                    "components_layout_flex_children_direct",
                    "children",
                    _badge(
                        sdk,
                        item_id,
                        sdk.i18n.t("components.layout.item.direct_added"),
                        "warning",
                    ),
                    surface_id=surface_id,
                )
            )
        if mode == "store":
            return _state_update(sdk, "page", {"/components_layout/flex_style": style})
        if mode == "global_store":
            return _state_update(sdk, "global", {"/components_layout/flex_style": style})
        if mode == "data":
            return _data_update(
                sdk,
                surface_id,
                {"components_layout": {"flex_model": {"style": style}}},
            )
        if mode == "direct":
            return sdk.effects.respond(
                sdk.effects.ui_property_update(
                    "components_layout_flex_direct", "style", style, surface_id=surface_id
                )
            )

    if component == "header":
        if prop in {"left", "center", "right"}:
            if prop:
                slot = prop
            strategy_label = {
                "page_store": sdk.i18n.t("components.layout.strategy.page"),
                "global_store": sdk.i18n.t("components.layout.strategy.global"),
                "data": sdk.i18n.t("components.layout.strategy.data"),
                "direct": sdk.i18n.t("components.layout.strategy.direct"),
            }.get(mode, "")
            if mode == "page_store":
                return _state_update(
                    sdk,
                    "page",
                    {
                        f"/components_layout/header_{slot}": _header_slot_items(
                            sdk, slot, strategy_label
                        ),
                    },
                )
            if mode == "global_store":
                return _state_update(
                    sdk,
                    "global",
                    {
                        f"/components_layout/header_{slot}": _header_slot_items(
                            sdk, slot, strategy_label
                        ),
                    },
                )
            if mode == "data":
                return _data_update(
                    sdk,
                    surface_id,
                    {
                        "components_layout": {
                            "header_model": {
                                slot: _header_slot_items(sdk, slot, strategy_label)
                            }
                        }
                    },
                )
            if mode == "direct":
                item_id = f"components_layout_header_direct_{slot}_{uuid4().hex}"
                return sdk.effects.respond(
                    sdk.effects.ui_collection_append(
                        "components_layout_header_slots_direct",
                        slot,
                        _header_slot_item(sdk, item_id, slot, strategy_label),
                        surface_id=surface_id,
                    )
                )

        if mode == "store":
            return _state_update(
                sdk,
                "page",
                {
                    "/components_layout/header_right": [
                        _badge(
                            sdk,
                            "components_layout_header_store_badge",
                            sdk.i18n.t("components.layout.badge.store"),
                            "success",
                        )
                    ]
                },
            )
        if mode == "data":
            return _data_update(
                sdk,
                surface_id,
                {
                    "components_layout": {
                        "header_model": {
                            "right": [
                                _badge(
                                    sdk,
                                    "components_layout_header_data_badge",
                                    sdk.i18n.t("components.layout.badge.data"),
                                    "warning",
                                )
                            ]
                        }
                    }
                },
            )
        if mode == "direct":
            return sdk.effects.respond(
                sdk.effects.ui_property_update(
                    "components_layout_header_direct",
                    "right",
                    [
                        _badge(
                            sdk,
                            "components_layout_header_direct_badge",
                            sdk.i18n.t("components.layout.badge.direct"),
                            "info",
                        )
                    ],
                    action="set",
                    surface_id=surface_id,
                )
            )

    if component == "sidebar":
        width = 280
        if prop == "children" and mode == "direct":
            item_id = f"components_layout_sidebar_direct_added_{uuid4().hex}"
            return sdk.effects.respond(
                sdk.effects.ui_collection_append(
                    "components_layout_sidebar_dynamic_nav",
                    "children",
                    _badge(
                        sdk,
                        item_id,
                        sdk.i18n.t("components.layout.item.direct_added"),
                        "warning",
                    ),
                    surface_id=surface_id,
                )
            )
        if mode == "store":
            return _state_update(sdk, "page", {"/components_layout/sidebar_width": width})
        if mode == "global_store":
            return _state_update(sdk, "global", {"/components_layout/sidebar_width": width})
        if mode == "data":
            return _data_update(
                sdk,
                surface_id,
                {"components_layout": {"sidebar_model": {"width": width}}},
            )
        if mode == "direct":
            return sdk.effects.respond(
                sdk.effects.ui_property_update(
                    "components_layout_sidebar_direct",
                    "width",
                    width,
                    surface_id=surface_id,
                ),
                sdk.effects.ui_property_update(
                    "components_layout_sidebar_direct",
                    "max_width",
                    width,
                    surface_id=surface_id,
                ),
            )

    return sdk.effects.respond()
