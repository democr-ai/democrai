from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


_UPDATED_ITEMS = [
    {
        "id": "updated_queue",
        "title": "Updated queue",
        "text": "Runtime update replaced the list data source.",
        "icon": "ric.refresh-line",
        "selectable": True,
    },
    {
        "id": "updated_policy",
        "title": "Updated policy check",
        "text": "Item actions and selection payloads still apply.",
        "icon": "ric.shield-check-line",
        "selectable": True,
        "active": True,
    },
]

_APPENDED_ITEM = {
    "id": "direct_appended",
    "title": "Appended direct item",
    "text": "Added through dataSource.data.append.",
    "icon": "ric.add-circle-line",
    "selectable": True,
}

_DIRECT_ACTIONS = [
    {
        "label": "Inspect updated",
        "icon": "ric.search-eye-line",
        "action": {
            "name": "components.list_event",
            "context": {"source": "direct_updated_menu", "item_id": "$item.id"},
        },
    }
]


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


@action("list_update")
@permission_required(["components.documentation.view"])
async def list_update(ctx: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {"/components_complex/list/items": _UPDATED_ITEMS},
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {"/components_complex/list/items": _UPDATED_ITEMS},
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_complex": {"list_model": {"items": _UPDATED_ITEMS}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_list_direct",
                "dataSource",
                {"type": "inline", "data": _UPDATED_ITEMS},
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_list_direct",
                "itemActions",
                _DIRECT_ACTIONS,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_list_direct",
                "selectable",
                True,
                surface_id=surface_id,
            ),
        )
    if mode == "direct_append":
        return sdk.effects.respond(
            sdk.effects.ui_collection_append(
                "components_complex_list_direct",
                "dataSource.data",
                _APPENDED_ITEM,
                surface_id=surface_id,
            )
        )

    return sdk.effects.respond()


@action("list_event")
@permission_required(["components.documentation.view"])
async def list_event(ctx: dict, sdk) -> dict:
    payload = {
        key: value
        for key, value in ctx.items()
        if not str(key).startswith("_")
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > 900:
        text = f"{text[:900]}..."
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "List event",
                "text": text,
                "variant": "info",
                "duration": 2800,
            },
        )
    )
