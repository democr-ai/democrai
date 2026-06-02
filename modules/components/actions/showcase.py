from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


@action("demo_ui_event")
@permission_required(["components.documentation.view"])
async def demo_ui_event(ctx: dict, sdk) -> dict:
    payload = {
        key: value
        for key, value in ctx.items()
        if not str(key).startswith("_") and key not in {"stream_id"}
    }
    text = json.dumps(payload, ensure_ascii=False)
    if len(text) > 700:
        text = f"{text[:700]}..."

    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Showcase event",
                "text": text,
                "variant": "info",
                "duration": 2600,
            },
        )
    )
