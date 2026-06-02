from __future__ import annotations

from datetime import datetime
import json
from uuid import uuid4

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from ..utils.ai_chat import component_message, seed_messages


def _compact_json(payload: dict, max_len: int = 900) -> str:
    try:
        rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    except Exception:
        rendered = str(payload)
    if len(rendered) <= max_len:
        return rendered
    return f"{rendered[:max_len]}..."


def _surface_id(ctx: dict) -> str:
    return str(ctx.get("_surface_id") or "main").strip() or "main"


def _created_at() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _messages_state_patch(sdk, action: str, value) -> dict:
    return sdk.effects.ui_messages(
        [
            sdk.effects.ui_state_patch(
                "/components_ai_chat/messages",
                action,
                value,
                scope="page",
            )
        ]
    )


@action("ai_chat_select_thread")
@permission_required(["components.documentation.view"])
async def ai_chat_select_thread(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_chat_thread_list").strip()
    thread_id = str(ctx.get("thread_id") or ctx.get("id") or "").strip()
    if not target or not thread_id:
        return sdk.effects.respond()
    return sdk.effects.respond(
        sdk.effects.ui_property_update(
            target,
            "active_thread_id",
            thread_id,
            surface_id=_surface_id(ctx),
        )
    )


@action("ai_chat_apply_suggestion")
@permission_required(["components.documentation.view"])
async def ai_chat_apply_suggestion(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_chat_composer").strip()
    prompt = str(ctx.get("prompt") or "").strip()
    if not target or not prompt:
        return sdk.effects.respond()
    return sdk.effects.respond(
        sdk.effects.ui_property_update(target, "value", prompt, surface_id=_surface_id(ctx))
    )


@action("ai_chat_send_message")
@permission_required(["components.documentation.view"])
async def ai_chat_send_message(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_chat_messages").strip()
    composer = str(ctx.get("composer") or "components_ai_chat_composer").strip()
    value = str(ctx.get("value") or "").strip()
    if not target or not value:
        return sdk.effects.respond()

    message_id = f"chat_u_{uuid4().hex[:8]}"
    message = {
        "id": message_id,
        "role": "user",
        "kind": "text",
        "status": "completed",
        "content": {"text": value},
        "created_at": _created_at(),
    }
    return sdk.effects.respond(
        _messages_state_patch(sdk, "append", message),
        sdk.effects.ui_property_update(composer, "value", "", surface_id=_surface_id(ctx)),
    )


@action("ai_chat_append_message")
@permission_required(["components.documentation.view"])
async def ai_chat_append_message(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_chat_messages").strip()
    message_id = f"chat_a_{uuid4().hex[:8]}"
    message = {
        "id": message_id,
        "role": "assistant",
        "kind": "text",
        "status": "completed",
        "content": {
            "text": "Runtime message appended without rebuilding the page.",
            "reasoning": "The action appends one message to the MessageList collection.",
        },
        "created_at": _created_at(),
    }
    return sdk.effects.respond(_messages_state_patch(sdk, "append", message))


@action("ai_chat_prepend_messages")
@permission_required(["components.documentation.view"])
async def ai_chat_prepend_messages(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_chat_messages").strip()
    if not target:
        return sdk.effects.respond()

    batch_id = uuid4().hex[:6]
    messages = [
        {
            "id": f"chat_history_{batch_id}_1",
            "role": "assistant",
            "kind": "text",
            "status": "completed",
            "content": {"text": "Historical context loaded before the visible thread."},
            "created_at": _created_at(),
        },
        {
            "id": f"chat_history_{batch_id}_2",
            "role": "user",
            "kind": "text",
            "status": "completed",
            "content": {"text": "Can we inspect the previous release risks first?"},
            "created_at": _created_at(),
        },
    ]
    return sdk.effects.respond(_messages_state_patch(sdk, "prepend", messages))


@action("ai_chat_append_surface")
@permission_required(["components.documentation.view"])
async def ai_chat_append_surface(ctx: dict, session: dict, sdk) -> dict:
    target = str(ctx.get("target") or "components_ai_chat_messages").strip()
    kind = str(ctx.get("kind") or "accordion").strip().lower()

    if not target:
        return sdk.effects.respond()

    message_id = f"chat_component_{uuid4().hex[:8]}"

    return sdk.effects.respond(
        _messages_state_patch(
            sdk,
            "append",
            component_message(message_id, kind, created_at=_created_at()),
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "AI Chat · surface append",
                "text": _compact_json({"message_id": message_id, "kind": kind}),
                "variant": "success",
                "duration": 2800,
            },
        ),
    )


@action("ai_chat_reset_preview")
@permission_required(["components.documentation.view"])
async def ai_chat_reset_preview(ctx: dict, session: dict, sdk) -> dict:
    return sdk.effects.respond(_messages_state_patch(sdk, "set", seed_messages()))


@action("ai_chat_toolbar_action")
@permission_required(["components.documentation.view"])
async def ai_chat_toolbar_action(ctx: dict, session: dict, sdk) -> dict:
    payload = {
        "source": str(ctx.get("source") or ""),
        "command": str(ctx.get("command") or ""),
        "target": str(ctx.get("target") or ""),
    }
    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "AI Chat · toolbar payload",
                "text": _compact_json(payload),
                "variant": "info",
                "duration": 4200,
            },
        )
    )


@action("ai_chat_open_attachment_drawer")
@permission_required(["components.documentation.view"])
async def ai_chat_open_attachment_drawer(ctx: dict, session: dict, sdk) -> dict:
    raw_url = str(ctx.get("url") or "").strip()
    if raw_url.startswith("data:"):
        raw_url = ""

    payload = {
        "message_id": str(ctx.get("message_id") or ""),
        "message_role": str(ctx.get("message_role") or ""),
        "name": str(ctx.get("name") or ""),
        "mime_type": str(ctx.get("mime_type") or "").strip().lower(),
        "storage_path": str(ctx.get("storage_path") or "").strip(),
        "file_id": str(ctx.get("file_id") or ""),
        "url": raw_url,
    }

    return sdk.effects.respond(
        sdk.effects.notify(
            "toast",
            {
                "title": "AI Chat · attachment payload",
                "text": _compact_json(payload),
                "variant": "info",
                "duration": 4200,
            },
        )
    )
