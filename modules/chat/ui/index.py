from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from modules.chat.utils.ui.mime import attachment_accept
from modules.chat.utils.ui.state import (
    chat_llm_state,
    knowledge_state,
    stt_configured,
    thread_list_state,
)


@permission_required(["chat.view"])
async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/index")

    llm = await chat_llm_state(sdk)
    llm_ready = bool(llm.get("configured"))
    accept = attachment_accept(sdk)

    builder.set_data("/chat/thread_list", thread_list_state(sdk))
    builder.get_component("chat_message_list").set_property("messages", [])
    builder.get_component("chat_composer").set_property("voice", stt_configured(sdk))

    builder.set_store("/chat/current/attachments", [], scope="page")
    builder.set_store("/chat/current/knowledge", knowledge_state(sdk), scope="page")

    builder.set_store(
        "/chat/home",
        {
            "llm_ready": llm_ready,
            "llm_status": str(llm.get("status") or ""),
            "composer_disabled": not llm_ready,
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
