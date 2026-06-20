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


@action("audio_update")
@permission_required(["components.documentation.view"])
async def audio_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main")
    values = {
        "source": sdk.ui.resolve_media_source(
            "assets/test2.mp3",
            component_type="Audio",
            field="source",
        ),
        "title": "test2",
    }

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_media/audio/source": values["source"],
                "/components_media/audio/title": values["title"],
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_media/audio/source": values["source"],
                "/components_media/audio/title": values["title"],
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_media": {"audio_model": values}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_media_audio_direct",
                "source",
                values["source"],
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_media_audio_direct",
                "title",
                values["title"],
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
