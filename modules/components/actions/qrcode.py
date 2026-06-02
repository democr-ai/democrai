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


@action("qrcode_update")
@permission_required(["components.documentation.view"])
async def qrcode_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    content = "WIFI:S:Democrai Demo;T:WPA;P:demo-password;;"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {"/components_content/qrcode/content": content},
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {"/components_content/qrcode/content": content},
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_content": {"qrcode_model": {"content": content}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_qrcode_direct",
                "content",
                content,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_qrcode_direct",
                "size",
                180,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_qrcode_direct",
                "border",
                2,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_qrcode_direct",
                "fill_color",
                "#047857",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_qrcode_direct",
                "back_color",
                "#ffffff",
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
