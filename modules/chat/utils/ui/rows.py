from __future__ import annotations

from typing import Any

from modules.chat.models import ChatComponent, Conversation, Message


def _iso(value: Any) -> str:
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat()) if callable(isoformat) else ""


def component_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row["payload"]
    return {
        "id": f"component_{row['id']}",
        "role": "assistant",
        "kind": "component",
        "status": "completed",
        "content": {"components": payload["components"]},
        "meta": _iso(row.get("created_at")),
    }


def component_model_row(component: ChatComponent) -> dict[str, Any]:
    return {
        "id": f"component_{component.id}",
        "role": "assistant",
        "kind": "component",
        "status": "completed",
        "content": {"components": component.payload["components"]},
        "meta": _iso(getattr(component, "created_at", None)),
    }


def thread_row(
    conversation: dict[str, Any], last_message: dict[str, Any] | None = None
) -> dict[str, Any]:
    preview = ""
    if last_message is not None:
        preview = last_message["content"].get("text", "")
    conversation_id = conversation["id"]
    title = conversation["title"]
    return {
        "id": str(conversation_id),
        "title": title,
        "text": title,
        "snippet": preview[:120],
        "preview": preview[:120],
        "path": f"/chat/thread/{conversation_id}",
    }


def thread_model_row(
    conversation: Conversation, last_message: Message | None = None
) -> dict[str, Any]:
    preview = ""
    if last_message is not None:
        preview = last_message.content.get("text", "")
    title = conversation.title
    return {
        "id": str(conversation.id),
        "title": title,
        "text": title,
        "snippet": preview[:120],
        "preview": preview[:120],
        "path": f"/chat/thread/{conversation.id}",
    }
