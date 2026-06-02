from __future__ import annotations

from modules.chat.models import Attachment, ChatComponent, Conversation, Message
from modules.chat.utils.ui.rows import component_row, thread_row

THREAD_MESSAGE_PAGE_SIZE = 30
THREAD_LIST_PAGE_SIZE = 15


def thread_list_state(
    module_sdk,
    *,
    page: int = 0,
    page_size: int = THREAD_LIST_PAGE_SIZE,
    active_thread_id: int | str | None = None,
) -> dict:
    resolved_page = max(0, int(page or 0))
    resolved_page_size = max(1, int(page_size or THREAD_LIST_PAGE_SIZE))
    conversations = Conversation.list(
        sort={"field": "last_message_at", "direction": "desc"},
        page=resolved_page,
        page_size=resolved_page_size,
    )
    rows: list[dict] = []
    for row in conversations["rows"]:
        messages_result = Message.list(
            filters={"conversation_id": row["id"]},
            sort={"field": "sequence", "direction": "desc"},
            page=0,
            page_size=1,
        )
        messages = messages_result["rows"]
        item = thread_row(row, messages[0] if messages else None)
        item["active"] = str(item["id"]) == str(active_thread_id or "")
        rows.append(item)
    total_rows = int(conversations.get("total_rows") or 0)
    total_pages = max(1, (total_rows + resolved_page_size - 1) // resolved_page_size)
    display_page = min(resolved_page + 1, total_pages)
    return {
        "items": rows,
        "page": resolved_page,
        "page_size": resolved_page_size,
        "total_rows": total_rows,
        "has_prev": resolved_page > 0,
        "has_next": resolved_page + 1 < total_pages,
        "page_label": f"{display_page}/{total_pages}",
        "active_thread_id": str(active_thread_id or ""),
    }


def recent_threads(module_sdk) -> list[dict]:
    return thread_list_state(module_sdk, page=0, page_size=200)["items"]


def _timeline_window(
    module_sdk,
    conversation_id: int,
    *,
    before_sequence: int | None = None,
    page_size: int = THREAD_MESSAGE_PAGE_SIZE,
) -> list[tuple[int, dict]]:
    limit = max(1, page_size)
    filters = {"conversation_id": conversation_id}
    if before_sequence is not None:
        filters["before_sequence"] = before_sequence
    messages_result = Message.list(
        filters=filters,
        sort={"field": "sequence", "direction": "desc"},
        page=0,
        page_size=limit,
    )
    components_result = ChatComponent.list(
        filters=filters,
        sort={"field": "sequence", "direction": "desc"},
        page=0,
        page_size=limit,
    )
    messages = messages_result["rows"]
    components = components_result["rows"]
    selected = sorted(
        [
            *[(row["sequence"], "message", row) for row in messages],
            *[(row["sequence"], "component", row) for row in components],
        ],
        key=lambda item: item[0],
        reverse=True,
    )[:limit]
    message_ids = [row["id"] for _sequence, kind, row in selected if kind == "message"]
    attachments = []
    if message_ids:
        attachments_result = Attachment.all(
            filters={
                "conversation_id": conversation_id,
                "message_ids": message_ids,
            },
            sort={"field": "id", "direction": "asc"},
        )
        attachments = attachments_result["rows"]
    by_message: dict[int, list] = {}
    for attachment in attachments:
        by_message.setdefault(attachment["message_id"], []).append(attachment)
    timeline = []
    for sequence, kind, row in selected:
        if kind == "message":
            for key in ("created_at", "updated_at"):
                value = row.get(key)
                if hasattr(value, "isoformat"):
                    row[key] = value.isoformat()
            attachments = by_message.get(row["id"], [])
            if attachments:
                for attachment in attachments:
                    for key in ("created_at", "updated_at"):
                        value = attachment.get(key)
                        if hasattr(value, "isoformat"):
                            attachment[key] = value.isoformat()
                content = dict(row["content"])
                content["attachments"] = attachments
                row["content"] = content
            timeline.append((sequence, row))
        else:
            timeline.append((sequence, component_row(row)))
    timeline.sort(key=lambda item: item[0])
    return timeline


def thread_messages(module_sdk, conversation_id: int) -> list[dict]:
    return [item[1] for item in _timeline_window(module_sdk, conversation_id)]


def thread_messages_before(
    module_sdk,
    conversation_id: int,
    before_sequence: int,
    *,
    page_size: int = THREAD_MESSAGE_PAGE_SIZE,
) -> list[dict]:
    timeline = _timeline_window(
        module_sdk,
        conversation_id,
        before_sequence=before_sequence,
        page_size=page_size,
    )
    return [item[1] for item in timeline]


def visible_oldest_sequence(module_sdk, items: list[dict]) -> int:
    sequences = []
    for item in items:
        if "sequence" in item:
            sequences.append(item["sequence"])
    return min(sequences) if sequences else 0


def thread_attachments(module_sdk, conversation_id: int) -> list[dict]:
    result = Attachment.list(
        filters={"conversation_id": conversation_id},
        sort={"field": "id", "direction": "asc"},
        page=0,
        page_size=200,
    )
    rows = result["rows"]
    for row in rows:
        for key in ("created_at", "updated_at"):
            value = row.get(key)
            if hasattr(value, "isoformat"):
                row[key] = value.isoformat()
    return rows


def knowledge_state(module_sdk) -> dict:
    config = module_sdk.knowledge.get_runtime_config()
    enabled = bool(config.get("enabled"))
    embedding_model = config.get("embedding_model_registry_id")
    return {
        "enabled": enabled,
        "embedding_retrieval_available": bool(enabled and embedding_model),
        "config": config,
    }


async def chat_llm_state(module_sdk) -> dict:
    return module_sdk.ai.get_composer_options_for_capability("chat")


def stt_configured(module_sdk) -> bool:
    result = module_sdk.models.model_registry.list(
        page=0, page_size=100, filters={"capabilies": "stt", "status": "active"}
    )

    has = False
    for row in result.get("rows"):
        if "stt" in row.get("capabilities"):
            has = True
            break

    return has
