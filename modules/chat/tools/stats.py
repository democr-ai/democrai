from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk
from democrai.sdk.decorators import tool

from modules.chat.models import Attachment, ChatComponent, Conversation, Message


def _sdk(sdk):
    return sdk if sdk is not None else active_sdk


@tool(
    "runtime-stats",
    title="Runtime statistics",
    description="Return lightweight runtime and chat statistics for A2UI summaries.",
    input_schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)
def runtime_stats(
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    resolved_id = int((context or {}).get("conversation_id") or 0)
    if resolved_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    conversation = module_sdk.database.get(Conversation, str(resolved_id))
    if conversation is None:
        return {"status": "error", "error": "conversation_not_found"}
    messages_count = Message.count(filters={"conversation_id": resolved_id})
    attachments_count = Attachment.count(filters={"conversation_id": resolved_id})
    components_count = ChatComponent.count(filters={"conversation_id": resolved_id})

    user = dict(module_sdk.session.get("user") or {})
    user_id = int(user.get("id") or 0)
    organization_id = user.get("organization_id")
    tasks = module_sdk.tasks.list_user_tasks(user_id, organization_id) if user_id else []
    running_tasks = [
        item for item in tasks if str(item.get("status") or "").lower() in {"pending", "running"}
    ]
    return {
        "status": "ok",
        "conversation_id": resolved_id,
        "chat": {
            "thread": conversation.title,
            "messages": messages_count,
            "attachments": attachments_count,
            "components": components_count,
        },
        "background_tasks": {
            "total_visible": len(tasks),
            "running": len(running_tasks),
            "items": running_tasks[:10],
        },
        "knowledge": module_sdk.knowledge.get_runtime_config(),
    }
