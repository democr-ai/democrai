from __future__ import annotations

from typing import Any

from modules.chat.models import Attachment


def create_attachments(
    module_sdk,
    *,
    conversation_id: int,
    message_id: int,
    payloads: list[dict],
) -> list[dict[str, Any]]:
    for item in payloads:
        background_task_id = item.get("background_task_id") or ""
        module_sdk.database.add(
            Attachment(
                conversation_id=conversation_id,
                message_id=message_id,
                name=item["name"],
                mime_type=item["content_type"],
                storage_path=item["storage_path"],
                file_id=item["file_id"],
                extraction_request_id=item.get("extraction_request_id") or "",
                metadata_json={
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "background_task_id": background_task_id,
                },
            )
        )
    if not payloads:
        return []
    result = Attachment.list(
        filters={"message_id": message_id},
        sort={"field": "id", "direction": "asc"},
        page=0,
        page_size=len(payloads),
    )
    return result["rows"]
