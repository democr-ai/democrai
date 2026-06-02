from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


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


_ACCORDION_ITEMS = [
    {
        "title": "Updated incident summary",
        "content": "The runtime update replaced the accordion datasource.",
        "meta": "Open",
        "open": True,
    },
    {
        "title": "Follow-up actions",
        "content": "Multiple sections can stay open when multiple is true.",
        "meta": "Review",
        "open": True,
    },
    {
        "title": "Audit note",
        "content": "Collapsible false keeps a single panel from closing to an empty state.",
        "open": False,
    },
]


@action("accordion_update")
@permission_required(["components.documentation.view"])
async def accordion_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_complex/accordion/items": _ACCORDION_ITEMS,
                "/components_complex/accordion/multiple": True,
                "/components_complex/accordion/collapsible": False,
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_complex/accordion/items": _ACCORDION_ITEMS,
                "/components_complex/accordion/multiple": True,
                "/components_complex/accordion/collapsible": False,
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_complex": {
                    "accordion_model": {
                        "items": _ACCORDION_ITEMS,
                        "multiple": True,
                        "collapsible": False,
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_accordion_direct",
                "items",
                _ACCORDION_ITEMS,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_accordion_direct",
                "multiple",
                True,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_accordion_direct",
                "collapsible",
                False,
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
