from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


@action("yaml_demo_increment")
@permission_required(["components.documentation.view"])
async def yaml_demo_increment(ctx: dict, sdk) -> dict:
    scope = ctx.get("scope", "page")
    key = str(
        ctx.get("key")
        or ("/local_counter" if scope == "page" else "/global_counter")
    )

    current = 0 if ctx.get("current_value") is None else ctx.get("current_value")
    if isinstance(current, dict):
        current = 0
    current = int(current)

    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": scope,
                        "values": {key: current + 1},
                    }
                }
            ]
        )
    )
