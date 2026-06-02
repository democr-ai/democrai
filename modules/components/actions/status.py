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


@action("status_update")
@permission_required(["components.documentation.view"])
async def status_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    values = {
        "badge_text": "Updated badge",
        "badge_variant": "success",
        "title": "Updated status",
        "description": "The status changed from the action.",
        "variant": "success",
    }

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {f"/components_content/status/{key}": value for key, value in values.items()},
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {f"/components_content/status/{key}": value for key, value in values.items()},
        )
    if mode == "data":
        return _data_update(sdk, surface_id, {"components_content": {"status_model": values}})
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_status_badge_direct",
                "text",
                values["badge_text"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_status_badge_direct",
                "variant",
                values["badge_variant"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_status_alert_direct",
                "title",
                values["title"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_status_alert_direct",
                "description",
                values["description"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_status_alert_direct",
                "variant",
                values["variant"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
