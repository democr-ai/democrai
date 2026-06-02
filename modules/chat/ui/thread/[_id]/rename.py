from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from modules.chat.models import Conversation


@permission_required(["chat.write"])
async def render(params: dict, session: dict):
    route_params = dict(params.get("route_params") or {})
    conversation_id = int(route_params["_id"])
    conversation = sdk.database.get(Conversation, str(conversation_id))

    builder = sdk.ui.load("utils/ui/yaml/thread_rename")
    builder.set_data(
        "/chat/thread_rename",
        {
            "conversation_id": str(conversation_id),
            "values": {
                "title": str(getattr(conversation, "title", "") or "")
                if conversation is not None
                else "",
            },
        },
    )
    form = builder.get_component("chat_thread_rename_form")
    if form is not None:
        form.set_property(
            "action",
            {
                "name": "chat.rename_thread",
                "context": {
                    "conversation_id": str(conversation_id),
                    "thread_list_surface_id": "main_content",
                },
            },
        )
    return builder
