from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from modules.chat.models import Conversation
from modules.chat.utils.ui.mime import attachment_accept
from modules.chat.utils.ui.state import (
    chat_llm_state,
    knowledge_state,
    stt_configured,
    thread_attachments,
    thread_list_state,
    thread_messages,
    visible_oldest_sequence,
)


@permission_required(["chat.view"])
async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    conversation_id = int(route_params["id"])
    conversation = sdk.database.get(Conversation, str(conversation_id))
    if conversation is None:
        return sdk.ui.load("utils/ui/yaml/index")

    builder = sdk.ui.load("utils/ui/yaml/thread")
    llm = await chat_llm_state(sdk)
    llm_ready = bool(llm.get("configured"))

    accept = attachment_accept(sdk)

    initial_messages = thread_messages(sdk, conversation_id)

    builder.set_data(
        "/chat/thread_list",
        thread_list_state(sdk, active_thread_id=conversation_id),
    )
    builder.get_component("chat_message_list").set_property(
        "messages", initial_messages
    )
    builder.get_component("chat_composer").set_property("voice", stt_configured(sdk))
    builder.set_store(
        "/chat/current/oldest_sequence",
        visible_oldest_sequence(sdk, initial_messages),
        scope="page",
    )
    builder.set_store(
        "/chat/current/attachments",
        thread_attachments(sdk, conversation_id),
        scope="page",
    )

    builder.get_component("chat_composer").set_property(
        "send_action",
        {
            "name": "chat.submit_message",
            "context": {
                "source": "chat_thread",
                "conversation_id": str(conversation_id),
                "composer": "chat_composer",
                "target": "chat_message_list",
            },
        },
    )
    builder.get_component("chat_message_list").set_property(
        "on_load_more",
        {
            "name": "chat.load_older_messages",
            "context": {
                "target": "chat_message_list",
                "conversation_id": str(conversation_id),
                "before_sequence": visible_oldest_sequence(sdk, initial_messages),
            },
        },
    )

    builder.set_store("/chat/current/knowledge", knowledge_state(sdk), scope="page")
    builder.set_store(
        "/chat/thread",
        {
            "conversation_id": str(conversation_id),
            "title": str(conversation.title or ""),
            "composer_disabled": not llm_ready,
            "llm_status": str(llm.get("status") or ""),
            "attachment_accept": accept,
            "attachment_enabled": bool(accept),
            "model_capabilities": list(llm.get("model_capabilities") or []),
            "options": dict(llm.get("options") or {}),
            "options_schema": dict(llm.get("options_schema") or {"fields": []}),
            "options_editable": bool(llm.get("options_editable")),
        },
        scope="page",
    )
    return builder
