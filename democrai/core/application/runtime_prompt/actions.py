from __future__ import annotations

from democrai.core.application.runtime_prompt.service import get_runtime_prompt_service
from democrai.core.runtime.foundation.app import req_ctx


async def runtime_prompt_response(action_ctx: dict, session: dict, sdk) -> dict:
    prompt_id = str(action_ctx.get("prompt_id") or "").strip()
    action_id = str(action_ctx.get("action") or "").strip()
    if not prompt_id or not action_id:
        return {
            "ok": False,
            "type": "error",
            "error": "runtime_prompt_response_invalid",
        }
    form_id = str(action_ctx.get("form_id") or "").strip()
    data = action_ctx.get(form_id) if form_id else {}
    if not isinstance(data, dict):
        data = {}

    try:
        current = req_ctx()
        user_id = current.user
        session_key = current.session_key
    except LookupError:
        user = session.get("user") or {}
        user_id = user.get("id")
        session_key = action_ctx.get("session_key")

    decision = await get_runtime_prompt_service().respond(
        prompt_id=prompt_id,
        action_id=action_id,
        data=data,
        user_id=user_id,
        session_key=session_key,
    )
    if not decision.ok:
        return {
            "ok": False,
            "type": "error",
            "error": decision.error or "runtime_prompt_response_failed",
        }

    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": "drawer"}},
                {"deleteSurface": {"surfaceId": "modal"}},
            ]
        )
    )
