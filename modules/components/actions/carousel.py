from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


_UPDATED_SLIDES = [
    {
        "id": "slide_update_security",
        "eyebrow": "Updated",
        "title": "Policy checks",
        "desc": "Runtime update replaced the carousel data source.",
        "cta": "Open",
    },
    {
        "id": "slide_update_streams",
        "eyebrow": "Updated",
        "title": "Stream publisher",
        "desc": "Long running tasks can publish UI events through streams.",
        "cta": "Inspect",
    },
    {
        "id": "slide_update_ui",
        "eyebrow": "Updated",
        "title": "Component showcase",
        "desc": "Binding, template and action payloads stay visible.",
        "cta": "Review",
    },
]

_APPENDED_SLIDE = {
    "id": "slide_direct_appended",
    "eyebrow": "Append",
    "title": "Appended slide",
    "desc": "This slide was appended through dataSource.data.append.",
    "cta": "Done",
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


@action("carousel_update")
@permission_required(["components.documentation.view"])
async def carousel_update(ctx: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {"/components_complex/carousel/slides": _UPDATED_SLIDES},
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {"/components_complex/carousel/slides": _UPDATED_SLIDES},
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {"components_complex": {"carousel_model": {"slides": _UPDATED_SLIDES}}},
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "dataSource",
                {"type": "inline", "data": _UPDATED_SLIDES},
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "activeIndex",
                1,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "autoplay",
                False,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "intervalMs",
                1200,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "showDots",
                True,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "showArrows",
                True,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_carousel_direct",
                "loop",
                False,
                surface_id=surface_id,
            ),
        )
    if mode == "direct_append":
        return sdk.effects.respond(
            sdk.effects.ui_collection_append(
                "components_complex_carousel_direct",
                "dataSource.data",
                _APPENDED_SLIDE,
                surface_id=surface_id,
            )
        )

    return sdk.effects.respond()


@action("carousel_event")
@permission_required(["components.documentation.view"])
async def carousel_event(ctx: dict, sdk) -> dict:
    payload = {
        key: value
        for key, value in ctx.items()
        if not str(key).startswith("_")
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > 700:
        text = f"{text[:700]}..."

    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Carousel event",
                "text": text,
                "variant": "info",
                "duration": 2600,
            },
        )
    )
