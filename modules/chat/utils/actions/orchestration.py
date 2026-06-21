from __future__ import annotations

from datetime import datetime, timezone
import json
import re
import uuid
from typing import Any

from democrai.sdk.media import media_type_from_content_type

from modules.chat.models import Attachment, Conversation, Message
from modules.chat.utils.actions.conversation import composer_payload
from modules.chat.utils.actions.messages import next_sequence
from modules.chat.utils.ui.state import knowledge_state

RECENT_MESSAGE_LIMIT = 10
CHAT_TOOLS = [
    "chat.search-messages",
    "core.ask-user",
    "chat.list-attachments",
    "chat.read-document",
    "chat.extract-full-summary",
    "chat.search-documents",
    "chat.wait-seconds",
]
CHAT_SKILLS = ["chat.chat_context"]
CHAT_AGENTS = [
    "chat.stats-agent",
    "chat.component-agent",
]
_UNTRUSTED_CONTENT_RE = re.compile(r"</?untrusted-content\b[^>]*>", re.IGNORECASE)
_UNTRUSTED_CONTENT_PARTIAL_RE = re.compile(
    r"<(?:/)?untrusted-content\b[^>]*$",
    re.IGNORECASE,
)
_GPT_OSS_FINAL_RE = re.compile(
    r"(?:<\|start\|>assistant)?<\|channel\|>final(?:<\|message\|>)?(.*?)(?=<\|end\|>|<\|start\|>|<\|channel\|>|$)",
    flags=re.DOTALL,
)
_GEMMA_END_TOKEN = "<channel|>"
_DEBUG_PREVIEW_CHARS = 4000


def _now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _dev_enabled(module_sdk) -> bool:
    is_dev = getattr(getattr(module_sdk, "system", None), "is_dev", None)
    if not callable(is_dev):
        return False
    try:
        return bool(is_dev())
    except Exception:
        return False


def _debug_preview(value: Any, *, max_chars: int = _DEBUG_PREVIEW_CHARS) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except Exception:
            text = str(value)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "...<truncated>"


def _chunk_text(chunk: Any) -> str:
    if chunk is None:
        return ""
    if isinstance(chunk, str):
        return chunk
    if isinstance(chunk, bytes | bytearray):
        return chunk.decode("utf-8", errors="ignore")
    if isinstance(chunk, dict):
        return str(
            chunk.get("delta") or chunk.get("content") or chunk.get("text") or ""
        )
    return str(
        getattr(chunk, "delta", None)
        or getattr(chunk, "content", None)
        or getattr(chunk, "text", None)
        or ""
    )


def _chunk_reasoning(chunk: Any) -> str:
    if chunk is None or isinstance(chunk, str | bytes | bytearray):
        return ""
    if isinstance(chunk, dict):
        return str(chunk.get("reasoning") or "")
    return str(getattr(chunk, "reasoning", None) or "")


def _message_text(row: Message) -> str:
    return row["content"].get("text") or ""


def _clean_model_text(text: str) -> str:
    cleaned = _UNTRUSTED_CONTENT_RE.sub("", str(text or "")).strip()
    final_parts = [
        match.group(1).strip() for match in _GPT_OSS_FINAL_RE.finditer(cleaned)
    ]
    final_text = "".join(part for part in final_parts if part)
    if final_text:
        cleaned = final_text
    if _GEMMA_END_TOKEN in cleaned:
        cleaned = cleaned.rsplit(_GEMMA_END_TOKEN, 1)[1]
    return cleaned.replace("<|end|>", "").strip()


def _clean_stream_display_text(text: str) -> str:
    cleaned = _UNTRUSTED_CONTENT_RE.sub("", str(text or ""))
    return _UNTRUSTED_CONTENT_PARTIAL_RE.sub("", cleaned)


def _is_direct_provider_attachment(mime_type: str) -> bool:
    return str(mime_type or "").strip().lower().startswith("image/")


def _attachment_reference_text(attachments: list[Attachment]) -> str:
    lines = []
    for attachment in attachments:
        parts = [
            f"id={int(_row_field(attachment, 'id') or 0)}",
            f"name={str(_row_field(attachment, 'name') or '').strip() or '-'}",
            f"mime={str(_row_field(attachment, 'mime_type') or '').strip() or '-'}",
        ]
        request_id = str(_row_field(attachment, "extraction_request_id") or "").strip()
        if request_id:
            parts.append(f"extraction_request_id={request_id}")
        lines.append("- " + ", ".join(parts))
    if not lines:
        return ""
    return (
        "Uploaded attachments for this message:\n"
        + "\n".join(lines)
        + "\nUse chat attachment and retrieval tools for non-image files."
    )


def _attachment_status_map(
    module_sdk,
    attachments: list[Attachment],
) -> dict[str, dict[str, Any]]:
    request_ids = [
        str(_row_field(attachment, "extraction_request_id") or "").strip()
        for attachment in attachments
        if str(_row_field(attachment, "extraction_request_id") or "").strip()
    ]
    if not request_ids:
        return {}
    result = module_sdk.knowledge.list_extraction_statuses(request_ids)
    return {
        str(item.get("request_id") or ""): dict(item)
        for item in list(result.get("items") or [])
        if isinstance(item, dict)
    }


def _attachment_extraction_status(
    attachment: Attachment,
    statuses: dict[str, dict[str, Any]],
) -> str:
    request_id = str(_row_field(attachment, "extraction_request_id") or "").strip()
    if not request_id:
        return "not_requested"
    status = statuses.get(request_id) or {}
    return str(status.get("extraction_status") or "unknown").strip() or "unknown"


def _conversation_attachment_text(
    attachments: list[Attachment],
    statuses: dict[str, dict[str, Any]],
) -> str:
    lines = []
    for attachment in attachments:
        request_id = str(_row_field(attachment, "extraction_request_id") or "").strip()
        parts = [
            f"id={int(_row_field(attachment, 'id') or 0)}",
            f"name={str(_row_field(attachment, 'name') or '').strip() or '-'}",
            f"mime_type={str(_row_field(attachment, 'mime_type') or '').strip() or '-'}",
            f"extraction_status={_attachment_extraction_status(attachment, statuses)}",
        ]
        if request_id:
            parts.append(f"extraction_request_id={request_id}")
        lines.append("- " + ", ".join(parts))
    if not lines:
        return ""
    return "Current uploaded attachments:\n" + "\n".join(lines)


def _content_for_provider(row: Message, attachments: list[Attachment]) -> Any:
    text = _message_text(row)
    if not attachments:
        return text
    attachment_text = _attachment_reference_text(attachments)
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": "\n\n".join(part for part in (text, attachment_text) if part),
        }
    ]
    for attachment in attachments:
        mime_type = str(_row_field(attachment, "mime_type") or "").strip()
        storage_path = str(_row_field(attachment, "storage_path") or "").strip()
        if (
            not mime_type
            or not storage_path
            or not _is_direct_provider_attachment(mime_type)
        ):
            continue
        content.append(
            {
                "type": media_type_from_content_type(mime_type),
                "mime_type": mime_type,
                "storage_path": storage_path,
            }
        )
    return content


def _row_field(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _last_user_message_id(rows: list[dict[str, Any]]) -> int:
    for row in reversed(rows):
        if str(row.get("role") or "").strip() != "user":
            continue
        return int(row.get("id") or 0)
    return 0


def build_provider_messages(
    module_sdk, conversation: Conversation
) -> list[dict[str, Any]]:
    total_messages = (
        Message.count(filters={"conversation_id": int(conversation.id)}) or 0
    )

    recent = Message.list(
        filters={"conversation_id": int(conversation.id)},
        sort={"field": "sequence", "direction": "desc"},
        page=0,
        page_size=RECENT_MESSAGE_LIMIT,
    )
    selected = sorted(
        list(recent.get("rows") or []),
        key=lambda item: int(item.get("sequence") or 0),
    )

    attachments_result = Attachment.list(
        filters={"conversation_id": int(conversation.id)},
        sort={"field": "id", "direction": "asc"},
        page=0,
        page_size=200,
    )
    attachments = list(attachments_result.get("rows") or [])
    attachment_statuses = _attachment_status_map(module_sdk, attachments)
    attachment_overview = _conversation_attachment_text(attachments, attachment_statuses)
    last_user_message_id = _last_user_message_id(selected)
    by_message: dict[int, list[Attachment]] = {}
    for attachment in attachments:
        message_id = int(_row_field(attachment, "message_id") or 0)
        if message_id == last_user_message_id:
            by_message.setdefault(message_id, []).append(attachment)

    summary = str(getattr(conversation, "summary", "") or "").strip()
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "You are the Democrai chat conversation router and final responder. "
                "The current conversation has this summary: "
                f"{summary}"
                ""
                f"There are {total_messages} total messages in the conversation"
                "Only the last "
                f"{RECENT_MESSAGE_LIMIT} messages are provided; use chat.search-messages "
                "when older context is needed. Always produce a final user-facing "
                "answer after tool or agent calls; do not stop after delegation and do "
                "not describe internal handoffs unless the user explicitly asks how the "
                "system works. Use the chat attachment and retrieval tools directly "
                "for uploaded attachments and extracted content, including documents, "
                "audio, video, and images processed by background extractors. For "
                "file-related questions, inspect attachment status with "
                "chat.list-attachments, search extracted content with "
                "chat.search-documents, read a document for analysis with "
                "chat.read-document (returns the whole document when it fits, "
                "otherwise an index of blocks to request by index; every result "
                "includes counts of items per type, so answer how-many questions "
                "from counts instead of reading; pass kind=table/formula/image to "
                "read those items). For an overview of a large document use "
                "chat.extract-full-summary first (builds and caches a document "
                "map/summary on the document record); then use read-document or "
                "chat.search-documents to open exactly the parts you need. Wait "
                "briefly with chat.wait-seconds "
                "when extraction is pending and the file is needed. Use "
                "chat.search-messages only for older chat context. Do not claim an "
                "uploaded file cannot be processed until attachment status and "
                "extracted content have been inspected. "
                "Use the stats agent for current chat/runtime statistics: message, "
                "attachment and component counts, visible background tasks, running "
                "tasks, and knowledge runtime state. Use the component agent only to "
                "render UI from compact data. It can create Alert, Badge, Card, Chart "
                "(bar, line, area), DataTable, Descriptions, metric Grid, List, "
                "Markdown, Progress, SequenceDiagram, Tabs, Text, and Title components. "
                "Ask it for one focused component unless the user explicitly wants "
                "multiple separate components. When calling an agent tool, "
                "put the short task in the required input field only; do not use task "
                "or other argument names and do not copy the whole conversation into "
                "the input. When calling the component agent, describe only the desired "
                "component type and the compact data to display. Do not send A2UI JSON, "
                "component_kind, components arrays, YAML, renderer props, or nested UI "
                "structures to the component agent; it owns choosing and calling the "
                "dedicated component tool. Use agent results as evidence and answer "
                "naturally; do not say 'I sent a command to the agent' as the final "
                "answer. "
                "If the user asks about uploaded files, check status with document search and retrieve tools. "
                "If the user asks for statistics or visual summaries, call the stats "
                "agent first, then call the component agent with the relevant compact "
                "data to display. After a component agent call, never paste raw JSON "
                "in the final answer; briefly tell the user what was displayed. When "
                "a required value should come from the user, call core.ask-user with a "
                "Form model instead of guessing or describing a manual HITL process. "
                "Form models for core.ask-user must be flat lists of fields; do not "
                "use row, column, children, or nested layout nodes. "
                "For Form fields, use type select for dropdown controls; dropdown is "
                "not a supported Form field type. "
                "The internal pipeline step name agent_hitl_form is not a callable "
                "tool name; the callable tool is core.ask-user."
                + (f"\n\n{attachment_overview}" if attachment_overview else "")
            ),
        }
    ]
    summary = str(getattr(conversation, "summary", "") or "").strip()
    if summary:
        messages.append(
            {
                "role": "system",
                "content": f"Current thread summary:\n{summary}",
            }
        )
    for row in selected:
        if str(row.get("kind") or "").strip() == "task":
            continue
        messages.append(
            {
                "role": str(row.get("role") or "user"),
                "content": _content_for_provider(
                    row, by_message.get(int(row.get("id") or 0), [])
                ),
            }
        )
    return messages


def _selected_names(payload: dict[str, Any], key: str) -> list[str]:
    values = payload.get(key)
    if not isinstance(values, list):
        return []
    return [str(item or "").strip() for item in values if str(item or "").strip()]


def _set_nested_value(target: dict[str, Any], key: str, value: Any) -> None:
    parts = [part for part in key.split(".") if part]
    if not parts:
        return
    current = target
    for part in parts[:-1]:
        nested = current.get(part)
        if not isinstance(nested, dict):
            nested = {}
            current[part] = nested
        current = nested
    current[parts[-1]] = value


def _options(option_entries: list[dict[str, Any]]) -> dict[str, Any]:
    options: dict[str, Any] = {}
    for item in option_entries:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        if key.startswith("extra."):
            _set_nested_value(options, key, item.get("value"))
        else:
            options[key] = item.get("value")
    return options


def build_provider_options(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        **_options(list(payload.get("options") or [])),
        "tools": [*CHAT_TOOLS, *_selected_names(payload, "selected_tools")],
        "skills": [*CHAT_SKILLS, *_selected_names(payload, "selected_skills")],
        "agents": [*CHAT_AGENTS, *_selected_names(payload, "selected_agents")],
        "mcp": _selected_names(payload, "selected_mcp"),
        "tool_max_iterations": 10,
    }


def _pipeline_field(message: Any, key: str) -> Any:
    if isinstance(message, dict):
        return message.get(key)
    return getattr(message, key, None)


def _pipeline_message_title(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    return (
        payload.get("tool_title")
        or payload.get("agent_title")
        or payload.get("mcp_name")
        or ""
    )


def _is_important_pipeline_message(message: Any) -> bool:
    return _pipeline_field(message, "type") in {
        "tool.call",
        "tool.call.started",
        "tool.call.finished",
        "tool.call.failed",
        "tool.response",
        "agent.call",
        "agent.response",
        "agent.failed",
        "agent.pipeline.started",
        "agent.pipeline.finished",
        "mcp.call",
        "mcp.response",
    }


def _pipeline_message_row(
    message: Any, *, message_id: str | None = None
) -> dict[str, Any] | None:
    # print("[PIPELINE MESSAGE]", message)
    if not _is_important_pipeline_message(message):
        return None
    payload = _pipeline_field(message, "payload")
    title = _pipeline_message_title(payload)
    if not title:
        return None
    return {
        "id": message_id or f"agent_step_{uuid.uuid4().hex}",
        "role": "system",
        "kind": "task",
        "status": "running",
        "content": {"title": title},
        "meta": "agent step",
    }


async def run_chat_orchestration(
    module_sdk,
    ctx: dict[str, Any],
    conversation: Conversation,
    user_message: Message,
    *,
    on_step=None,
    on_message=None,
    on_stream_start=None,
    on_stream_delta=None,
    request_id: str | None = None,
) -> Message | None:
    payload = composer_payload(ctx)
    provider_result = await module_sdk.ai.get_provider_for_objective(
        "chat",
        required_capabilities=["chat"],
    )
    if provider_result.get("status") != "ok" or not provider_result.get("provider"):
        raise RuntimeError(str(provider_result.get("error") or "provider_unavailable"))
    provider = provider_result["provider"]

    text_parts: list[str] = []
    reasoning_parts: list[str] = []

    async def _on_message(message: Any) -> None:
        if on_message is not None:
            result = on_message(message)
            if hasattr(result, "__await__"):
                await result
        if on_step is not None:
            row = _pipeline_message_row(message)
            if row is not None:
                await on_step(row)

    knowledge = knowledge_state(module_sdk)
    ingest = bool(knowledge.get("enabled"))
    ingest_meta = {
        "module_name": "chat",
        "conversation_id": int(conversation.id),
        "thread_id": int(conversation.id),
        "message_id": int(user_message.id),
    }
    if on_stream_start is not None:
        await on_stream_start()

    async for chunk in provider.generate_stream(
        messages=build_provider_messages(module_sdk, conversation),
        options=build_provider_options(payload),
        request_id=request_id,
        ingest=ingest,
        ingest_meta=ingest_meta,
        on_message=_on_message,
    ):
        text = _chunk_text(chunk)
        reasoning = _chunk_reasoning(chunk)
        if not text and not reasoning:
            continue
        if text:
            text_parts.append(text)
        if reasoning:
            reasoning_parts.append(reasoning)
        if on_stream_delta is not None:
            await on_stream_delta(
                _clean_stream_display_text("".join(text_parts)),
                "".join(reasoning_parts),
            )

    raw_text = "".join(text_parts)
    final_text = _clean_model_text(raw_text)
    reasoning_text = "".join(reasoning_parts).strip()

    if not final_text:  # and not reasoning_text:
        return None

    content = {"text": final_text}
    if reasoning_text:
        content["reasoning"] = reasoning_text

    message = module_sdk.database.add(
        Message(
            conversation_id=conversation.id,
            role="assistant",
            kind="text",
            status="completed",
            sequence=next_sequence(module_sdk, conversation.id),
            content=content,
        )
    )
    module_sdk.database.update(
        Conversation,
        str(conversation.id),
        last_message_at=_now_naive(),
    )
    return message
