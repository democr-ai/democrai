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


@action("video_update")
@permission_required(["components.documentation.view"])
async def video_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main")
    values = {
        "source": sdk.ui.resolve_media_source(
            "assets/test2.mp4",
            component_type="Video",
            field="source",
        ),
        "title": "test2",
        "poster": sdk.ui.resolve_media_source(
            "assets/demo_img.png",
            component_type="Video",
            field="poster",
        ),
    }

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_media/video/source": values["source"],
                "/components_media/video/title": values["title"],
                "/components_media/video/poster": values["poster"],
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_media/video/source": values["source"],
                "/components_media/video/title": values["title"],
                "/components_media/video/poster": values["poster"],
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_media": {"video_model": values}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_media_video_direct",
                "source",
                values["source"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_media_video_direct",
                "title",
                values["title"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_media_video_direct",
                "poster",
                values["poster"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
