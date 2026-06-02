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


_SEGMENTS = [
    {"label": "Components", "path": "/components/index"},
    {"label": "Updated content", "path": "/components/_content/text"},
    {"label": "Breadcrumb runtime", "current": True},
]


@action("breadcrumb_update")
@permission_required(["components.documentation.view"])
async def breadcrumb_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {"/components_content/breadcrumb/segments": _SEGMENTS},
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {"/components_content/breadcrumb/segments": _SEGMENTS},
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_content": {"breadcrumb_model": {"segments": _SEGMENTS}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_breadcrumb_direct",
                "segments",
                _SEGMENTS,
                surface_id=surface_id,
            )
        )

    return sdk.effects.respond()
