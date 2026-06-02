from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any, AsyncGenerator, Dict, List

from democrai.sdk.engines import (
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
)
from democrai.sdk.engines import BaseEngine, LLMProvider
from democrai.sdk.ai_constants import AICapability, AIModelFormat, AIModelSourceKind
from democrai.sdk.dependencies import ensure_import, install_dependency


class AnthropicEngine(BaseEngine, LLMProvider):
    engine_id = "anthropic"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_dependency("anthropic", force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("anthropic", "anthropic")),
            ok_message="Anthropic engine ready",
            error_message="Anthropic engine requires shared state or local dependencies",
        )

    def __init__(self, config: dict):
        super().__init__(config)
        anthropic_mod = ensure_import("anthropic", dependency_key="anthropic")
        AsyncAnthropic = getattr(anthropic_mod, "AsyncAnthropic")
        self.client = AsyncAnthropic(
            api_key=self.api_key or os.environ.get("ANTHROPIC_API_KEY"),
            base_url="https://api.anthropic.com",
        )

    async def list_available_models(self) -> list[dict[str, Any]]:
        models_api = getattr(self.client, "models", None)
        list_method = getattr(models_api, "list", None)
        if not callable(list_method):
            return []
        response = list_method()
        if hasattr(response, "__await__"):
            response = await response
        rows = getattr(response, "data", None) or response or []
        result: list[dict[str, Any]] = []
        for row in rows:
            model_id = str(getattr(row, "id", "") or "").strip()
            if not model_id and isinstance(row, dict):
                model_id = str(row.get("id") or "").strip()
            if not model_id:
                continue
            result.append(
                {
                    "id": model_id,
                    "label": model_id,
                    "source_kind": AIModelSourceKind.PROVIDER_API,
                    "format": AIModelFormat.REMOTE,
                    "capabilities": [
                        AICapability.CHAT,
                        AICapability.TOOL_CALLING,
                        AICapability.REASONING,
                    ],
                }
            )
        return result

    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        payload = self._build_request_payload(messages, options)
        response = await self.client.messages.create(**payload)
        tool_calls = self._extract_tool_calls(response)
        return CompletionResponse(
            id=str(getattr(response, "id", "") or "anthropic"),
            content=None if tool_calls else self._extract_text(response),
            reasoning=self._extract_reasoning(response),
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=self._extract_usage(response),
            finish_reason=str(getattr(response, "stop_reason", "") or "stop"),
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        payload = self._build_request_payload(messages, options)
        response_id = "anthropic"
        input_tokens = 0
        output_tokens = 0
        finish_reason = None
        tool_states: dict[int, dict[str, str]] = {}
        async with self.client.messages.stream(**payload) as stream:
            async for event in stream:
                event_type = str(getattr(event, "type", "") or "")
                if event_type == "message_start":
                    message = getattr(event, "message", None)
                    response_id = str(getattr(message, "id", "") or response_id)
                    usage = getattr(message, "usage", None)
                    input_tokens = _usage_int(usage, "input_tokens")
                    output_tokens = _usage_int(usage, "output_tokens")
                    continue
                if event_type == "content_block_start":
                    content_block = getattr(event, "content_block", None)
                    if str(getattr(content_block, "type", "") or "") == "tool_use":
                        tool_states[int(getattr(event, "index", 0) or 0)] = {
                            "id": str(getattr(content_block, "id", "") or ""),
                            "name": str(getattr(content_block, "name", "") or ""),
                            "partial_json": "",
                        }
                    continue
                if event_type == "content_block_delta":
                    delta = getattr(event, "delta", None)
                    delta_type = str(getattr(delta, "type", "") or "")
                    if delta_type == "text_delta":
                        text = str(getattr(delta, "text", "") or "")
                        if text:
                            yield StreamChunk(id=response_id, delta=text)
                        continue
                    if delta_type == "thinking_delta":
                        thinking = str(getattr(delta, "thinking", "") or "")
                        if thinking:
                            yield StreamChunk(id=response_id, reasoning=thinking)
                        continue
                    if delta_type == "input_json_delta":
                        index = int(getattr(event, "index", 0) or 0)
                        state = tool_states.get(index)
                        if state is not None:
                            state["partial_json"] += str(
                                getattr(delta, "partial_json", "") or ""
                            )
                        continue
                if event_type == "content_block_stop":
                    index = int(getattr(event, "index", 0) or 0)
                    state = tool_states.pop(index, None)
                    if state is not None:
                        yield StreamChunk(
                            id=response_id,
                            delta=None,
                            tool_call_delta=ToolCall(
                                id=state["id"],
                                function_name=state["name"],
                                arguments=state["partial_json"] or "{}",
                            ),
                        )
                    continue
                if event_type == "message_delta":
                    delta = getattr(event, "delta", None)
                    finish_reason = str(
                        getattr(delta, "stop_reason", "") or finish_reason or "stop"
                    )
                    usage = getattr(event, "usage", None)
                    input_tokens = _usage_int(usage, "input_tokens") or input_tokens
                    output_tokens = _usage_int(usage, "output_tokens") or output_tokens
                    continue
            final_message_getter = getattr(stream, "get_final_message", None)
            if callable(final_message_getter):
                final_message = await final_message_getter()
                response_id = str(getattr(final_message, "id", "") or response_id)
                finish_reason = str(
                    getattr(final_message, "stop_reason", "") or finish_reason or "stop"
                )
                usage = getattr(final_message, "usage", None)
                input_tokens = _usage_int(usage, "input_tokens") or input_tokens
                output_tokens = _usage_int(usage, "output_tokens") or output_tokens
        yield StreamChunk(
            id=response_id,
            delta=None,
            finish_reason=finish_reason or "stop",
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )
        await asyncio.sleep(0)

    def _build_request_payload(
        self, messages: List[Message], options: CompletionOptions
    ) -> Dict[str, Any]:
        system_blocks: list[dict[str, Any]] = []
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == MessageRole.SYSTEM:
                text = self._content_to_text(msg.content)
                if text:
                    system_blocks.append({"type": "text", "text": text})
                continue
            formatted = self._format_message(msg)
            if formatted is not None:
                api_messages.append(formatted)

        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": api_messages
            or [{"role": "user", "content": [{"type": "text", "text": ""}]}],
            "max_tokens": options.max_tokens or 1024,
        }
        if system_blocks:
            payload["system"] = system_blocks
        if options.stop:
            payload["stop_sequences"] = list(options.stop)
        if options.tools:
            payload["tools"] = [
                {
                    "name": tool.function.name,
                    "description": tool.function.description or "",
                    "input_schema": tool.function.parameters
                    or {"type": "object", "properties": {}},
                }
                for tool in options.tools
            ]
        payload.update(self._request_extra(options.extra))
        thinking = payload.get("thinking")
        if isinstance(thinking, dict):
            budget_tokens = int(thinking["budget_tokens"])
            if payload["max_tokens"] <= budget_tokens:
                payload["max_tokens"] = budget_tokens + 1024
        if "temperature" in payload:
            payload.pop("temperature", None)
        if "top_p" in payload:
            payload.pop("top_p", None)
        return payload

    def _request_extra(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload = dict(extra)
        reasoning = payload.pop("reasoning", None)
        budget = payload.pop("reasoning_budget", None)
        payload.pop("reasoning_param_name", None)
        if reasoning in (None, "", False):
            return payload
        budget_tokens = _positive_int(budget, default=4096)
        payload["thinking"] = {
            "type": "enabled",
            "budget_tokens": budget_tokens,
        }
        return payload

    def _format_message(self, msg: Message) -> Dict[str, Any] | None:
        if msg.role == MessageRole.TOOL:
            tool_result = self._format_tool_result_message(msg)
            return tool_result

        role = "assistant" if msg.role == MessageRole.ASSISTANT else "user"
        content_blocks: list[dict[str, Any]] = []
        if msg.content:
            if isinstance(msg.content, str):
                content_blocks.append({"type": "text", "text": msg.content})
            else:
                for part in msg.content:
                    if part.type == "text" and part.text is not None:
                        content_blocks.append({"type": "text", "text": part.text})
                    elif part.type == "image":
                        content_blocks.append(self._format_image_part(part))
        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                arguments = tool_call.arguments or "{}"
                try:
                    parsed = json.loads(arguments)
                except Exception:
                    parsed = {}
                content_blocks.append(
                    {
                        "type": "tool_use",
                        "id": tool_call.id,
                        "name": tool_call.function_name,
                        "input": parsed if isinstance(parsed, dict) else {},
                    }
                )
        if not content_blocks:
            return None
        return {"role": role, "content": content_blocks}

    def _format_image_part(self, part: Any) -> dict[str, Any]:
        if part.data:
            payload = base64.b64encode(part.data).decode("utf-8")
            return {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": part.mime_type or "image/jpeg",
                    "data": payload,
                },
            }
        if part.url:
            return {
                "type": "image",
                "source": {
                    "type": "url",
                    "url": part.url,
                },
            }
        raise ValueError("anthropic_image_data_required")

    def _format_tool_result_message(self, msg: Message) -> Dict[str, Any]:
        tool_use_id = str(msg.tool_call_id or "").strip() or "tool"
        content_text = self._content_to_text(msg.content)
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content_text,
                }
            ],
        }

    def _content_to_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                str(part.text or "")
                for part in content
                if getattr(part, "type", None) == "text"
            )
        return ""

    def _extract_text(self, response: Any) -> str:
        chunks: list[str] = []
        for block in list(getattr(response, "content", None) or []):
            block_type = _block_value(block, "type")
            if block_type == "text":
                text = _block_value(block, "text")
                if text:
                    chunks.append(text)
        return "".join(chunks)

    def _extract_reasoning(self, response: Any) -> str | None:
        chunks: list[str] = []
        for block in list(getattr(response, "content", None) or []):
            block_type = _block_value(block, "type")
            if block_type == "thinking":
                thinking = _block_value(block, "thinking")
                if thinking:
                    chunks.append(thinking)
        return "".join(chunks) or None

    def _extract_usage(self, response: Any) -> CompletionUsage | None:
        usage = getattr(response, "usage", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage")
        if usage is None:
            return None
        prompt_tokens = _usage_int(usage, "input_tokens")
        completion_tokens = _usage_int(usage, "output_tokens")
        total_tokens = prompt_tokens + completion_tokens
        if total_tokens == 0:
            return None
        return CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _extract_tool_calls(self, response: Any) -> List[ToolCall] | None:
        tool_calls: list[ToolCall] = []
        for block in list(getattr(response, "content", None) or []):
            if str(getattr(block, "type", "") or "") != "tool_use":
                continue
            tool_calls.append(
                ToolCall(
                    id=str(getattr(block, "id", "") or ""),
                    function_name=str(getattr(block, "name", "") or ""),
                    arguments=json.dumps(getattr(block, "input", {}) or {}),
                )
            )
        return tool_calls or None


def _usage_int(usage: Any, key: str) -> int:
    if isinstance(usage, dict):
        value = usage.get(key)
    else:
        value = getattr(usage, key, None)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _block_value(block: Any, key: str) -> str:
    if isinstance(block, dict):
        return str(block.get(key) or "")
    return str(getattr(block, key, "") or "")


def _positive_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    result = int(value)
    if result <= 0:
        raise ValueError("expected_positive_int")
    return result
