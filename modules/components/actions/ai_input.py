from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


def _compact_json(payload: dict, max_len: int = 900) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        rendered = str(payload)
    if len(rendered) <= max_len:
        return rendered
    return f"{rendered[:max_len]}..."


@action("ai_input_demo_action")
@permission_required(["components.documentation.view"])
async def ai_input_demo_action(ctx: dict, session: dict, sdk) -> dict:
    intent = str(ctx.get("intent") or "interaction").strip() or "interaction"
    summary = {
        "intent": intent,
        "value": str(ctx.get("value") or ""),
        "model": ctx.get("model"),
        "tools_selected": ctx.get("tools_selected") or [],
        "skills_selected": ctx.get("skills_selected") or [],
        "capabilities": ctx.get("capabilities") or [],
        "voice_active": bool(ctx.get("voice_active", False)),
        "attachments": ctx.get("attachments") or [],
    }
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": f"AI Input · {intent}",
                "text": _compact_json(summary),
                "variant": "info",
                "duration": 5200,
            },
        )
    )


@action("ai_input_set_model")
@permission_required(["components.documentation.view"])
async def ai_input_set_model(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_input_preview").strip()
    model = str(ctx.get("model") or "").strip()
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    if not target or not model:
        return sdk.effects.respond()
    return sdk.effects.respond(
        sdk.effects.ui_property_update(target, "model", model, surface_id=surface_id),
        sdk.effects.ui_messages(
            [{"stateUpdate": {"scope": "page", "values": {"/components_ai/input/model": model}}}]
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "AI Input · model",
                "text": f"Current model set to: {model}",
                "variant": "success",
                "duration": 2400,
            },
        ),
    )


@action("ai_input_set_capabilities")
@permission_required(["components.documentation.view"])
async def ai_input_set_capabilities(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_input_preview").strip()
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"
    raw = ctx.get("model_capabilities")
    capabilities = []
    if isinstance(raw, list):
        for item in raw:
            value = str(item or "").strip()
            if value:
                capabilities.append(value)
    return sdk.effects.respond(
        sdk.effects.ui_property_update(target, "model_capabilities", capabilities, surface_id=surface_id),
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {"/components_ai/input/model_capabilities": capabilities},
                    }
                }
            ]
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "AI Input · capabilities",
                "text": _compact_json({"capabilities": capabilities}),
                "variant": "info",
                "duration": 2600,
            },
        ),
    )
