from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


_UPDATED = {
    "variant": "flat",
    "padding": [24, 24, 24, 24],
    "title": "Updated card",
    "body": "The card visual props and child text were updated from the selected runtime strategy.",
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


@action("card_update")
@permission_required(["components.documentation.view"])
async def card_update(ctx: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_complex/card/variant": _UPDATED["variant"],
                "/components_complex/card/padding": _UPDATED["padding"],
                "/components_complex/card/title": _UPDATED["title"],
                "/components_complex/card/body": _UPDATED["body"],
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_complex/card/variant": _UPDATED["variant"],
                "/components_complex/card/padding": _UPDATED["padding"],
                "/components_complex/card/title": _UPDATED["title"],
                "/components_complex/card/body": _UPDATED["body"],
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_complex": {"card_model": _UPDATED}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_card_direct",
                "variant",
                _UPDATED["variant"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_card_direct",
                "padding",
                _UPDATED["padding"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_card_direct_title",
                "text",
                _UPDATED["title"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_card_direct_text",
                "text",
                _UPDATED["body"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()


@action("card_action_event")
@permission_required(["components.documentation.view"])
async def card_action_event(ctx: dict, sdk) -> dict:
    source = str(ctx.get("source") or "card_action")
    payload = {key: value for key, value in ctx.items() if not str(key).startswith("_")}
    text = ", ".join(f"{key}: {value}" for key, value in payload.items()) or source
    variant = "destructive" if source.endswith("delete") else "default"

    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Card action",
                "text": text,
                "variant": variant,
                "duration": 2500,
            },
        )
    )
