from __future__ import annotations

from modules.chat.models import ChatComponent, Message


def next_sequence(module_sdk, conversation_id: int) -> int:
    messages = Message.list(
        filters={"conversation_id": conversation_id},
        sort={"field": "sequence", "direction": "desc"},
        page=0,
        page_size=1,
    )
    components = ChatComponent.list(
        filters={"conversation_id": conversation_id},
        sort={"field": "sequence", "direction": "desc"},
        page=0,
        page_size=1,
    )
    current = [
        row["sequence"]
        for row in [
            *messages["rows"],
            *components["rows"],
        ]
        if row.get("sequence") is not None
    ]
    return (max(current) if current else 0) + 1
