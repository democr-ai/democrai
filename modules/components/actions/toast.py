from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import action


@action("show_overlay_toast")
@permission_required(["components.documentation.view"])
async def show_overlay_toast(ctx: dict, session: dict, sdk) -> dict:
    variant = str(ctx.get("variant") or ctx.get("type") or "success")
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "Components Preview",
                "text": f"Sample toast variant: {variant}",
                "variant": variant,
                "duration": 2400,
            },
        )
    )
