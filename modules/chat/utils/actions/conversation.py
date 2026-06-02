from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from modules.chat.models import Conversation, Message
from modules.chat.utils.actions.attachments import create_attachments
from modules.chat.utils.actions.messages import next_sequence

COMPOSER_ID = "chat_composer"


def composer_payload(ctx: dict[str, Any]) -> dict[str, Any]:
    payload = ctx.get(COMPOSER_ID)
    if isinstance(payload, dict):
        return payload
    return ctx


def _submitted_text(ctx: dict[str, Any]) -> str:
    payload = composer_payload(ctx)
    for key in ("text", "value", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def create_user_turn(module_sdk, ctx: dict[str, Any]) -> dict[str, Any]:
    text = _submitted_text(ctx)
    payload = composer_payload(ctx)

    attachments_payload = payload.get("attachments")
    if not isinstance(attachments_payload, list):
        attachments_payload = []
    if not text and not attachments_payload:
        raise ValueError("chat_message_empty")

    conversation_id = str(ctx.get("conversation_id") or "").strip()
    conversation = None
    if conversation_id:
        conversation = module_sdk.database.get(Conversation, conversation_id)
    created = conversation is None
    if conversation is None:
        conversation = module_sdk.database.add(
            Conversation(title="", summary="", summary_until_sequence=0)
        )

    sequence = next_sequence(module_sdk, int(conversation.id))
    message = module_sdk.database.add(
        Message(
            conversation_id=int(conversation.id),
            role="user",
            kind="text",
            status="completed",
            sequence=sequence,
            content={"text": text},
        )
    )
    attachments = create_attachments(
        module_sdk,
        conversation_id=int(conversation.id),
        message_id=int(message.id),
        payloads=attachments_payload,
    )
    task_messages = []
    for attachment in attachments:
        metadata = attachment["metadata_json"]
        task_id = metadata.get("background_task_id")
        if not task_id:
            continue
        task_messages.append(
            module_sdk.database.add(
                Message(
                    conversation_id=int(conversation.id),
                    role="task",
                    kind="task",
                    status="running",
                    sequence=next_sequence(module_sdk, int(conversation.id)),
                    content={
                        "task_id": task_id,
                        "title": attachment["name"],
                    },
                )
            )
        )

    title = str(conversation.title or "").strip()
    updates: dict[str, Any] = {
        "last_message_at": datetime.now(timezone.utc).replace(tzinfo=None)
    }
    if not title:
        updates["title"] = module_sdk.i18n.t("chat.thread.untitled")
    conversation = module_sdk.database.update(
        Conversation, str(conversation.id), **updates
    )

    return {
        "conversation": conversation,
        "message": message,
        "attachments": attachments,
        "task_messages": task_messages,
        "created": created,
    }
