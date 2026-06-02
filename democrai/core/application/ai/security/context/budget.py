from __future__ import annotations

import json
import math
from typing import Any

from pydantic import BaseModel

from democrai.core.application.ai.engine.schemas.completion import ContentPart
from democrai.core.application.ai.engine.schemas.completion import Message
from democrai.core.application.ai.engine.schemas.completion import MessageRole
from democrai.core.application.ai.pipeline_context import ai_pipeline_step

DEFAULT_CONTEXT_TOKENS = 8192
DEFAULT_RESERVED_OUTPUT_TOKENS = 1024
SAFETY_MARGIN_TOKENS = 256
SINGLE_MESSAGE_BUDGET_RATIO = 0.60
CHARS_PER_TOKEN_ESTIMATE = 3
MAX_TOOL_RESULT_CHARS = 12000
TOOL_RESULT_BUDGET_RATIO = 0.30
TRUNCATED_TEXT_CHARS = 10000


async def guard_prompt_messages(
    messages: list[Any],
    *,
    options: Any = None,
    config: dict[str, Any] | None = None,
    stage: str,
) -> list[Any]:
    budget = _input_budget(options=options, config=config)
    single_message_budget = max(1, math.floor(budget * SINGLE_MESSAGE_BUDGET_RATIO))
    guarded = [_coerce_message(message) for message in messages]
    omitted: list[dict[str, Any]] = []

    for index, message in enumerate(guarded):
        estimated_tokens = _estimate_message_tokens(message)
        if estimated_tokens <= single_message_budget:
            continue
        omitted.append(
            {
                "index": index,
                "role": message.role.value,
                "reason": "single_message_budget_exceeded",
                "estimated_tokens": estimated_tokens,
            }
        )
        guarded[index] = _omitted_message(
            message,
            reason="message_too_long_for_context",
            estimated_tokens=estimated_tokens,
            budget_tokens=single_message_budget,
        )

    total_tokens = _estimate_messages_tokens(guarded)
    if total_tokens > budget:
        for index, message in enumerate(guarded):
            if message.role is MessageRole.SYSTEM:
                continue
            if _is_omitted_message(message):
                continue
            estimated_tokens = _estimate_message_tokens(message)
            omitted.append(
                {
                    "index": index,
                    "role": message.role.value,
                    "reason": "total_context_budget_exceeded",
                    "estimated_tokens": estimated_tokens,
                }
            )
            guarded[index] = _omitted_message(
                message,
                reason="message_omitted_to_fit_context_budget",
                estimated_tokens=estimated_tokens,
                budget_tokens=budget,
            )
            total_tokens = _estimate_messages_tokens(guarded)
            if total_tokens <= budget:
                break

    if not omitted:
        return guarded

    async with ai_pipeline_step(
        type="security.context_budget",
        name="prompt_messages",
        input={
            "stage": stage,
            "messages": len(messages),
            "estimated_tokens": _estimate_messages_tokens([_coerce_message(item) for item in messages]),
            "budget_tokens": budget,
            "single_message_budget_tokens": single_message_budget,
        },
    ) as step:
        if isinstance(step, dict):
            step["output"] = {
                "messages": len(guarded),
                "omitted": len(omitted),
                "estimated_tokens": _estimate_messages_tokens(guarded),
            }
            step["stats"] = {
                "budget_tokens": budget,
                "single_message_budget_tokens": single_message_budget,
                "omitted": omitted,
            }
    return guarded


async def guard_tool_result(
    result: Any,
    *,
    origin: str,
    options: Any = None,
    config: dict[str, Any] | None = None,
) -> Any:
    text = _to_prompt_text(result)
    original_chars = len(text)
    max_chars = _tool_result_budget_chars(options=options, config=config)
    if original_chars <= max_chars:
        return result

    compacted = _compact_tool_result(result, max_chars=max_chars)
    compacted_text = _to_prompt_text(compacted)
    async with ai_pipeline_step(
        type="security.context_budget",
        name="tool_result",
        input={
            "origin": origin,
            "original_chars": original_chars,
            "max_chars": max_chars,
        },
    ) as step:
        if isinstance(step, dict):
            step["output"] = {
                "truncated": True,
                "compacted_chars": len(compacted_text),
            }
            step["stats"] = {
                "original_chars": original_chars,
                "compacted_chars": len(compacted_text),
            }
    return compacted


def _input_budget(*, options: Any, config: dict[str, Any] | None) -> int:
    context_tokens = _context_tokens(options=options, config=config)
    reserved_output = _reserved_output_tokens(options)
    tool_schema_tokens = _tools_tokens(options)
    budget = context_tokens - reserved_output - tool_schema_tokens - SAFETY_MARGIN_TOKENS
    return max(512, budget)


def _context_tokens(*, options: Any, config: dict[str, Any] | None) -> int:
    for source in (_extra_options(options), options, config or {}):
        if not isinstance(source, dict):
            continue
        for key in ("context_length", "n_ctx", "max_model_len", "num_ctx"):
            value = _positive_int(source.get(key))
            if value is not None:
                return value
    return DEFAULT_CONTEXT_TOKENS


def _reserved_output_tokens(options: Any) -> int:
    for source in (options, _extra_options(options)):
        if not isinstance(source, dict):
            continue
        value = _positive_int(source.get("max_tokens"))
        if value is not None:
            return value
    return DEFAULT_RESERVED_OUTPUT_TOKENS


def _tools_tokens(options: Any) -> int:
    tools = None
    for source in (options, _extra_options(options)):
        if isinstance(source, dict) and source.get("tools") is not None:
            tools = source.get("tools")
            break
    if tools in (None, ""):
        return 0
    return _estimate_tokens(
        json.dumps(
            _json_compatible(tools),
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


def _json_compatible(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_json_compatible(item) for item in value]
    return value


def tool_result_budget_chars(
    *, options: Any = None, config: dict[str, Any] | None = None
) -> int:
    """Max chars a single tool result may occupy for the active model.

    Same budget ``guard_tool_result`` enforces downstream: a tool that wants to
    pre-size its own output (e.g. paginating a document) should target this so
    it never gets compacted after the fact.
    """
    return _tool_result_budget_chars(options=options, config=config)


def _tool_result_budget_chars(*, options: Any, config: dict[str, Any] | None) -> int:
    budget_tokens = _input_budget(options=options, config=config)
    result_tokens = max(128, math.floor(budget_tokens * TOOL_RESULT_BUDGET_RATIO))
    return result_tokens * CHARS_PER_TOKEN_ESTIMATE


def _extra_options(options: Any) -> dict[str, Any]:
    if not isinstance(options, dict):
        return {}
    extra = options.get("extra")
    return extra if isinstance(extra, dict) else {}


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _coerce_message(value: Any) -> Message:
    return value if isinstance(value, Message) else Message(**value)


def _estimate_messages_tokens(messages: list[Message]) -> int:
    return sum(_estimate_message_tokens(message) for message in messages)


def _estimate_message_tokens(message: Message) -> int:
    return _estimate_tokens(_message_prompt_text(message))


def _estimate_tokens(text: str) -> int:
    return math.ceil(len(text.encode("utf-8")) / CHARS_PER_TOKEN_ESTIMATE)


def _message_prompt_text(message: Message) -> str:
    payload = _message_budget_payload(message)
    return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def _message_budget_payload(message: Message) -> dict[str, Any]:
    content = message.content
    if isinstance(content, list):
        content = [_content_part_budget_payload(part) for part in content]
    return {
        key: value
        for key, value in {
            "role": message.role.value,
            "content": content,
            "tool_calls": [
                tool_call.model_dump(mode="json", exclude_none=True)
                for tool_call in message.tool_calls or []
            ] or None,
            "tool_responses": message.tool_responses,
            "tool_call_id": message.tool_call_id,
            "security": message.security,
        }.items()
        if value is not None
    }


def _content_part_budget_payload(part: ContentPart) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "type": part.type.value,
            "text": part.text,
            "url": part.url,
            "data_bytes": len(part.data) if part.data is not None else None,
            "mime_type": part.mime_type,
            "storage_path": part.storage_path,
        }.items()
        if value is not None
    }


def _omitted_message(
    message: Message,
    *,
    reason: str,
    estimated_tokens: int,
    budget_tokens: int,
) -> Message:
    content = (
        "[message omitted: too long for context; "
        f"reason={reason}; "
        f"estimated_tokens={estimated_tokens}; "
        f"budget_tokens={budget_tokens}]"
    )
    security = dict(message.security or {})
    metadata = security.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    metadata.update(
        {
            "context_budget_omitted": True,
            "reason": reason,
            "estimated_tokens": estimated_tokens,
            "budget_tokens": budget_tokens,
        }
    )
    security["metadata"] = metadata
    return Message(
        role=message.role,
        content=content,
        security=security or None,
        tool_calls=message.tool_calls if message.role is MessageRole.ASSISTANT else None,
        tool_responses=(
            message.tool_responses if message.role is MessageRole.ASSISTANT else None
        ),
        tool_call_id=message.tool_call_id if message.role is MessageRole.TOOL else None,
    )


def _is_omitted_message(message: Message) -> bool:
    content = message.content
    return isinstance(content, str) and content.startswith("[message omitted:")


def _to_prompt_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _compact_tool_result(value: Any, *, max_chars: int) -> Any:
    if isinstance(value, dict):
        return _compact_mapping(value, max_chars=max_chars)
    if isinstance(value, list):
        return {
            "status": "truncated",
            "truncated": True,
            "original_items": len(value),
            "items": value[:20],
        }
    text = str(value)
    return {
        "status": "truncated",
        "truncated": True,
        "text": text[: min(TRUNCATED_TEXT_CHARS, max_chars)],
        "omitted_chars": max(0, len(text) - min(TRUNCATED_TEXT_CHARS, max_chars)),
    }


def _compact_mapping(value: dict[str, Any], *, max_chars: int) -> dict[str, Any]:
    kept: dict[str, Any] = {}
    for key in (
        "status",
        "error",
        "error_type",
        "id",
        "component_id",
        "component_kind",
        "conversation_id",
        "message_id",
        "request_id",
        "kind",
        "name",
        "title",
    ):
        if key in value:
            kept[key] = value[key]
    kept["truncated"] = True
    kept["original_chars"] = len(_to_prompt_text(value))
    remaining_budget = max(0, max_chars - len(_to_prompt_text(kept)) - 200)
    if remaining_budget > 0:
        preview = _mapping_preview(value, kept_keys=set(kept))
        preview_text = _to_prompt_text(preview)
        kept["preview"] = (
            preview
            if len(preview_text) <= remaining_budget
            else preview_text[:remaining_budget]
        )
    return kept


def _mapping_preview(value: dict[str, Any], *, kept_keys: set[str]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key, item in value.items():
        if key in kept_keys:
            continue
        if isinstance(item, str):
            preview[key] = item[:1000]
        elif isinstance(item, list):
            preview[key] = item[:5]
        elif isinstance(item, dict):
            preview[key] = _mapping_preview(item, kept_keys=set())
        else:
            preview[key] = item
        if len(_to_prompt_text(preview)) > MAX_TOOL_RESULT_CHARS:
            break
    return preview
