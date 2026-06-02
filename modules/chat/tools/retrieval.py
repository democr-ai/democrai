from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk
from democrai.sdk.decorators import tool

from ..models import Attachment
from ..models import Message


def _sdk(sdk):
    return sdk if sdk is not None else active_sdk


def _conversation_id(context: dict[str, Any] | None) -> int:
    return int((context or {}).get("conversation_id") or 0)


def _matches(result: Any) -> list[dict[str, Any]]:
    items = []
    for item in list(getattr(result, "matches", []) or []):
        items.append(
            {
                "item_id": getattr(item, "item_id", None),
                "source_id": getattr(item, "source_id", None),
                "kind": getattr(item, "kind", None),
                "title": getattr(item, "title", None),
                "content": getattr(item, "content", None),
                "summary": getattr(item, "summary", None),
                "score": getattr(item, "score", None),
                "metadata": getattr(item, "metadata", None),
            }
        )
    return items


def _message_text(row: Message | dict[str, Any]) -> str:
    content = row["content"] if isinstance(row, dict) else row.content
    return content.get("text") or content.get("markdown") or ""


def _search_messages_database(
    module_sdk: Any,
    conversation_id: int,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    result = Message.list(
        filters={
            "conversation_id": conversation_id,
            "content_query": query,
        },
        sort={"field": "sequence", "direction": "desc"},
        page=0,
        page_size=limit,
    )
    rows = result["rows"]
    return [
        {
            "id": row["id"],
            "role": row["role"],
            "sequence": row["sequence"],
            "text": _message_text(row),
        }
        for row in rows
    ]


def _conversation_extraction_request_ids(conversation_id: int) -> list[str]:
    result = Attachment.list(
        filters={"conversation_id": conversation_id},
        sort={"field": "id", "direction": "asc"},
        page=0,
        page_size=200,
    )
    request_ids: list[str] = []
    seen: set[str] = set()
    for row in result["rows"]:
        request_id = row["extraction_request_id"]
        if request_id and request_id not in seen:
            request_ids.append(request_id)
            seen.add(request_id)
    return request_ids


def _search_extracted_documents(
    module_sdk: Any,
    *,
    conversation_id: int,
    query: str,
    top_k: int | str,
) -> dict[str, Any]:
    request_ids = _conversation_extraction_request_ids(conversation_id)
    if not request_ids:
        return {
            "status": "ok",
            "conversation_id": conversation_id,
            "matches": [],
            "source": "extracted_items",
        }
    result = module_sdk.knowledge.search_extracted_items(
        query_text=query,
        limit=max(1, min(20, int(top_k or 8))),
        extraction_request_ids=request_ids,
    )
    return {
        "status": "ok",
        "conversation_id": conversation_id,
        "matches": list(result.get("matches") or []),
        "source": "extracted_items",
    }


@tool(
    "search-messages",
    title="Search chat messages",
    description="Search persisted messages inside the current chat thread.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "default": 8},
        },
        "required": ["query"],
    },
)
async def search_messages(
    query: str,
    limit: int | str = 8,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    config = module_sdk.knowledge.get_runtime_config()
    resolved_id = _conversation_id(context)
    needle = str(query or "").strip()
    if not needle:
        return {"status": "error", "error": "query_required"}
    if resolved_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    max_rows = max(1, min(20, int(limit or 8)))
    if not bool(config.get("enabled")):
        return {
            "status": "ok",
            "conversation_id": resolved_id,
            "matches": _search_messages_database(module_sdk, resolved_id, needle, max_rows),
            "source": "database",
        }
    result = await module_sdk.knowledge.retrieve(
        query_text=needle,
        top_k=max_rows,
        metadata_filters={
            "module_name": "chat",
            "conversation_id": resolved_id,
        },
    )
    return {
        "status": "ok",
        "conversation_id": resolved_id,
        "matches": _matches(result),
        "source": "knowledge",
    }


@tool(
    "search-documents",
    title="Search chat documents",
    description="Search knowledge embeddings for documents linked to this chat thread.",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 8},
        },
        "required": ["query"],
    },
)
async def search_documents(
    query: str,
    top_k: int | str = 8,
    *,
    sdk=None,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    module_sdk = _sdk(sdk)
    resolved_id = _conversation_id(context)
    if resolved_id <= 0:
        return {"status": "error", "error": "conversation_id_required"}
    config = module_sdk.knowledge.get_runtime_config()
    needle = str(query or "").strip()
    if not needle:
        return {"status": "error", "error": "query_required"}
    if not bool(config.get("enabled")):
        return _search_extracted_documents(
            module_sdk,
            conversation_id=resolved_id,
            query=needle,
            top_k=top_k,
        )
    result = await module_sdk.knowledge.retrieve(
        query_text=needle,
        top_k=max(1, min(20, int(top_k or 8))),
        metadata_filters={
            "module_name": "chat",
            "conversation_id": resolved_id,
        },
    )
    matches = _matches(result)
    if matches:
        return {"status": "ok", "conversation_id": resolved_id, "matches": matches}
    return _search_extracted_documents(
        module_sdk,
        conversation_id=resolved_id,
        query=needle,
        top_k=top_k,
    )
