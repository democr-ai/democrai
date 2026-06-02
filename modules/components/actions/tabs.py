from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


_PAGE_UPDATED = [
    {"id": "components_complex_tabs_page_overview", "label": "Updated overview", "icon": "ric.refresh-line"},
    {"id": "components_complex_tabs_page_activity", "label": "Updated activity", "icon": "ric.pulse-line"},
]
_GLOBAL_UPDATED = [
    {"id": "components_complex_tabs_global_overview", "label": "Global overview", "icon": "ric.global-line"},
    {"id": "components_complex_tabs_global_activity", "label": "Global activity", "icon": "ric.history-line"},
]
_DATA_UPDATED = [
    {"id": "components_complex_tabs_data_overview", "label": "Data overview", "icon": "ric.database-2-line"},
    {"id": "components_complex_tabs_data_activity", "label": "Data activity", "icon": "ric.timeline-view"},
]
_DIRECT_UPDATED = [
    {"id": "components_complex_tabs_direct_alpha", "label": "Updated alpha", "icon": "ric.number-1"},
    {"id": "components_complex_tabs_direct_beta", "label": "Updated beta", "icon": "ric.number-2"},
]
_APPENDED_TAB = {
    "id": "components_complex_tabs_direct_gamma",
    "label": "Gamma",
    "icon": "ric.number-3",
}


def _state_update(sdk, scope: str, values: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages([{"stateUpdate": {"scope": scope, "values": values}}])
    )


def _data_update(sdk, surface_id: str, data: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [sdk.ui.Builder.build_data_model_update_payload(surface_id=surface_id, data=data)]
        )
    )


def _gamma_child(sdk) -> dict:
    text = sdk.ui.Text("components_complex_tabs_direct_gamma_text", "Appended direct pane.")
    pane = sdk.ui.Column("components_complex_tabs_direct_gamma", [text])
    pane.set_property("padding", [14, 14, 14, 14])
    return pane.to_dict()


@action("tabs_update")
@permission_required(["components.documentation.view"])
async def tabs_update(ctx: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {"/components_complex/tabs/items": _PAGE_UPDATED},
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {"/components_complex/tabs/items": _GLOBAL_UPDATED},
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_complex": {"tabs_model": {"tabs": _DATA_UPDATED}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_tabs_direct",
                "tabs",
                _DIRECT_UPDATED,
                surface_id=surface_id,
            )
        )

    return sdk.effects.respond()


@action("tabs_append_direct")
@permission_required(["components.documentation.view"])
async def tabs_append_direct(ctx: dict, sdk) -> dict:
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    return sdk.effects.respond(
        sdk.effects.ui_collection_remove(
            "components_complex_tabs_direct",
            "children",
            {"id": _APPENDED_TAB["id"]},
            surface_id=surface_id,
        ),
        sdk.effects.ui_collection_remove(
            "components_complex_tabs_direct",
            "tabs",
            {"id": _APPENDED_TAB["id"]},
            surface_id=surface_id,
        ),
        sdk.effects.ui_collection_append(
            "components_complex_tabs_direct",
            "children",
            _gamma_child(sdk),
            surface_id=surface_id,
        ),
        sdk.effects.ui_collection_append(
            "components_complex_tabs_direct",
            "tabs",
            _APPENDED_TAB,
            surface_id=surface_id,
        ),
    )


@action("tabs_remove_direct")
@permission_required(["components.documentation.view"])
async def tabs_remove_direct(ctx: dict, sdk) -> dict:
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    return sdk.effects.respond(
        sdk.effects.ui_collection_remove(
            "components_complex_tabs_direct",
            "children",
            {"id": _APPENDED_TAB["id"]},
            surface_id=surface_id,
        ),
        sdk.effects.ui_collection_remove(
            "components_complex_tabs_direct",
            "tabs",
            {"id": _APPENDED_TAB["id"]},
            surface_id=surface_id,
        ),
    )


@action("tabs_toast")
@permission_required(["components.documentation.view"])
async def tabs_toast(ctx: dict, sdk) -> dict:
    source = str(ctx.get("source") or "tabs")
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Tabs action",
                "text": f"Triggered from {source}",
                "variant": "info",
                "duration": 2000,
            },
        )
    )
