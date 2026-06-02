from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


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


@action("image_update")
@permission_required(["components.documentation.view"])
async def image_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main")
    values = {
        "alt": "Alternate image from runtime update",
        "url": sdk.ui.resolve_media_source(
            "assets/demo_img.png",
            component_type="Image",
            field="url",
        ),
        "width": 220,
        "height": 140,
    }

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_media/image/alt": values["alt"],
                "/components_media/image/url": values["url"],
                "/components_media/image/width": values["width"],
                "/components_media/image/height": values["height"],
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_media/image/alt": values["alt"],
                "/components_media/image/url": values["url"],
                "/components_media/image/width": values["width"],
                "/components_media/image/height": values["height"],
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_media": {"image_model": values}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_media_image_direct",
                "alt",
                values["alt"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_media_image_direct",
                "url",
                values["url"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_media_image_direct",
                "width",
                values["width"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_media_image_direct",
                "height",
                values["height"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
