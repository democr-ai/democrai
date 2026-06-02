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


@action("progress_update")
@permission_required(["components.documentation.view"])
async def progress_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    values = {
        "value": 72,
        "maximum": 120,
        "label": "Runtime 72/120",
        "show_label": True,
    }

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_content/progress/value": values["value"],
                "/components_content/progress/maximum": values["maximum"],
                "/components_content/progress/label": values["label"],
                "/components_content/progress/show_label": values["show_label"],
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_content/progress/value": values["value"],
                "/components_content/progress/maximum": values["maximum"],
                "/components_content/progress/label": values["label"],
                "/components_content/progress/show_label": values["show_label"],
            },
        )
    if mode == "data":
        return _data_update(sdk, surface_id, {"components_content": {"progress_model": values}})
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_progress_direct",
                "value",
                values["value"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_progress_direct",
                "maximum",
                values["maximum"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_progress_direct",
                "label",
                values["label"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
