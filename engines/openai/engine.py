from __future__ import annotations

import base64
import importlib
import importlib.metadata
import os
from typing import Any, AsyncGenerator

from democrai.sdk.ai_constants import AIModelFormat, AIModelSourceKind
from democrai.sdk.dependencies import ensure_import, install_python_packages
from democrai.sdk.engines import (
    BaseEngine,
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    EngineMethodResponse,
    EngineUsage,
    LLMProvider,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
)


_OPENAI_PACKAGE = "openai==2.40.0"
_OPENAI_VERSION = "2.40.0"


class OpenAIEngine(BaseEngine, LLMProvider):
    engine_id = "openai"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_python_packages([_OPENAI_PACKAGE], modules=["openai"], force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_module_labels(),
            ok_message="OpenAI engine ready",
            error_message="OpenAI engine requires shared state or local dependencies",
        )

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        missing = cls._missing_modules(("openai", _OPENAI_PACKAGE))
        if not _openai_version_matches():
            missing.append(_OPENAI_PACKAGE)
        if not _openai_runtime_symbols_available(
            responses=True,
            chat=False,
            embeddings=True,
            audio_speech=False,
            audio_transcriptions=False,
        ):
            missing.append("OpenAI runtime")
        return missing

    def __init__(self, config: dict):
        super().__init__({**dict(config), "base_url": "https://api.openai.com/v1"})
        openai_mod = ensure_import("openai", dependency_key="openai")
        AsyncOpenAI = getattr(openai_mod, "AsyncOpenAI")
        self.client = AsyncOpenAI(
            api_key=self.api_key or os.environ.get("OPENAI_API_KEY"),
            base_url="https://api.openai.com/v1",
        )

    async def list_available_models(self) -> list[dict[str, Any]]:
        response = await self.client.models.list()
        rows = getattr(response, "data", None) or []
        result: list[dict[str, Any]] = []
        for row in rows:
            model_id = getattr(row, "id", None)
            if not model_id:
                continue
            result.append(
                {
                    "id": model_id,
                    "label": model_id,
                    "source_kind": AIModelSourceKind.PROVIDER_API,
                    "format": AIModelFormat.REMOTE,
                }
            )
        return result

    async def _generate_completion(
        self,
        messages: list[Message],
        options: CompletionOptions,
    ) -> CompletionResponse:
        payload = self._build_response_payload(
            messages,
            options,
            stream=False,
        )
        response = await self.client.responses.create(**payload)
        return CompletionResponse(
            id=response.id,
            content=_response_text(response),
            reasoning=_response_reasoning(response),
            role=MessageRole.ASSISTANT,
            tool_calls=_response_tool_calls(response),
            usage=_response_usage(response),
            finish_reason=_response_finish_reason(response),
            status=getattr(response, "status", None),
        )

    async def _generate_stream(
        self,
        messages: list[Message],
        options: CompletionOptions,
    ) -> AsyncGenerator[StreamChunk, None]:
        payload = self._build_response_payload(
            messages,
            options,
            stream=True,
        )
        stream = await self.client.responses.create(**payload)
        stream_id = ""
        async for event in stream:
            stream_id = _event_response_id(event) or stream_id
            chunk_id = stream_id or "openai-response-stream"
            event_type = _field(event, "type")
            if event_type == "response.output_text.delta":
                yield StreamChunk(
                    id=chunk_id,
                    delta=_field(event, "delta"),
                )
            elif event_type in {
                "response.reasoning_text.delta",
                "response.reasoning_summary_text.delta",
            }:
                yield StreamChunk(
                    id=chunk_id,
                    reasoning=_field(event, "delta"),
                )
            elif event_type == "response.output_item.done":
                tool_call = _event_tool_call(event)
                if tool_call is not None:
                    yield StreamChunk(
                        id=chunk_id,
                        tool_call_delta=tool_call,
                    )
            elif event_type == "response.completed":
                response = _field(event, "response")
                usage = _response_usage(response)
                if usage is not None:
                    yield StreamChunk(
                        id=chunk_id,
                        prompt_tokens=usage.prompt_tokens,
                        completion_tokens=usage.completion_tokens,
                        total_tokens=usage.total_tokens,
                        finish_reason=_response_finish_reason(response),
                    )

    async def _embed_texts(self, texts: list[str]) -> EngineMethodResponse:
        if not texts:
            return EngineMethodResponse(result=[])
        response = await self.client.embeddings.create(
            model=self.model_name,
            input=texts,
        )
        vectors = [list(row.embedding) for row in response.data]
        usage = getattr(response, "usage", None)
        prompt_tokens = _int_field(usage, "prompt_tokens")
        total_tokens = _int_field(usage, "total_tokens", default=prompt_tokens)
        return EngineMethodResponse(
            result=vectors,
            usage=EngineUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=total_tokens,
            ),
            metadata={
                "input_count": len(texts),
                "items": len(vectors),
                "dimensions": len(vectors[0]) if vectors else 0,
            },
        )

    def _build_response_payload(
        self,
        messages: list[Message],
        options: CompletionOptions,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model_name,
            "input": self._format_input(messages),
            "stream": stream,
        }
        if options.max_tokens is not None:
            payload["max_output_tokens"] = options.max_tokens
        if options.tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "name": tool.function.name,
                    "description": tool.function.description,
                    "parameters": tool.function.parameters,
                }
                for tool in options.tools
            ]
        tool_choice = _response_tool_choice(options.tool_choice)
        if tool_choice is not None:
            payload["tool_choice"] = tool_choice
        payload.update(self._request_extra(options.extra))
        return payload

    def _request_extra(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload = dict(extra)
        reasoning = payload.pop("reasoning", None)
        payload.pop("reasoning_param_name", None)
        payload.pop("reasoning_budget", None)
        if reasoning not in (None, "", False):
            payload["reasoning"] = {"effort": _reasoning_effort(reasoning)}
        return payload

    def _format_input(self, messages: list[Message]) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for message in messages:
            if _enum_value(message.role) == "tool":
                formatted.append(
                    {
                        "type": "function_call_output",
                        "call_id": message.tool_call_id,
                        "output": _content_text(message.content),
                    }
                )
                continue
            entry: dict[str, Any] = {"role": _enum_value(message.role)}
            content = message.content
            if isinstance(content, str):
                entry["content"] = content
            elif content:
                entry["content"] = [_input_part(part) for part in content]
            if entry.get("content") is not None:
                formatted.append(entry)
            for tool_call in list(message.tool_calls or []):
                formatted.append(
                    {
                        "type": "function_call",
                        "call_id": tool_call.id,
                        "name": tool_call.function_name,
                        "arguments": tool_call.arguments,
                    }
                )
        return formatted


def _input_part(part: Any) -> dict[str, Any]:
    part_type = _enum_value(part.type)
    if part_type == "text":
        return {"type": "input_text", "text": part.text}
    if part_type == "image":
        if part.url:
            return {
                "type": "input_image",
                "image_url": part.url,
                "detail": "auto",
            }
        if part.data:
            mime = part.mime_type or "image/jpeg"
            encoded = base64.b64encode(part.data).decode("utf-8")
            return {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{encoded}",
                "detail": "auto",
            }
        raise ValueError("openai_image_data_required")
    raise ValueError("openai_input_part_type_unsupported")


def _response_tool_choice(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        function = value.get("function")
        if isinstance(function, dict) and function.get("name"):
            return {"type": "function", "name": function["name"]}
        return value
    return value


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(part.text or "") for part in content if part.text)
    return ""


def _reasoning_effort(value: Any) -> str:
    if value is True:
        return "medium"
    return value


def _response_text(response: Any) -> str | None:
    output_text = _field(response, "output_text")
    if output_text:
        return output_text
    parts: list[str] = []
    for item in _list_field(response, "output"):
        if _field(item, "type") != "message":
            continue
        for content in _list_field(item, "content"):
            if _field(content, "type") in {"output_text", "text"}:
                text = _field(content, "text")
                if text:
                    parts.append(text)
    return "".join(parts) or None


def _response_reasoning(response: Any) -> str | None:
    parts: list[str] = []
    for item in _list_field(response, "output"):
        if _field(item, "type") != "reasoning":
            continue
        for content in _list_field(item, "content"):
            text = _field(content, "text")
            if text:
                parts.append(text)
        for content in _list_field(item, "summary"):
            text = _field(content, "text")
            if text:
                parts.append(text)
    return "".join(parts) or None


def _response_tool_calls(response: Any) -> list[ToolCall] | None:
    calls: list[ToolCall] = []
    for item in _list_field(response, "output"):
        tool_call = _tool_call_from_item(item)
        if tool_call is not None:
            calls.append(tool_call)
    return calls or None


def _event_tool_call(event: Any) -> ToolCall | None:
    return _tool_call_from_item(_field(event, "item"))


def _tool_call_from_item(item: Any) -> ToolCall | None:
    if _field(item, "type") != "function_call":
        return None
    return ToolCall(
        id=_field(item, "call_id") or _field(item, "id"),
        function_name=_field(item, "name"),
        arguments=_field(item, "arguments") or "",
    )


def _response_usage(response: Any) -> CompletionUsage | None:
    usage = _field(response, "usage")
    if usage is None:
        return None
    prompt_tokens = _int_field(usage, "input_tokens")
    completion_tokens = _int_field(usage, "output_tokens")
    return CompletionUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=_int_field(
            usage,
            "total_tokens",
            default=prompt_tokens + completion_tokens,
        ),
    )


def _response_finish_reason(response: Any) -> str | None:
    incomplete = _field(response, "incomplete_details")
    if incomplete is not None:
        reason = _field(incomplete, "reason")
        if reason:
            return reason
    return _field(response, "status")


def _event_response_id(event: Any) -> str:
    response = _field(event, "response")
    raw = _field(response, "id") or _field(event, "response_id") or _field(event, "id")
    return raw if isinstance(raw, str) else ""


def _list_field(value: Any, name: str) -> list[Any]:
    raw = _field(value, name)
    return raw if isinstance(raw, list) else []


def _int_field(value: Any, name: str, *, default: int = 0) -> int:
    raw = _field(value, name)
    return raw if isinstance(raw, int) else default


def _field(value: Any, name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        return value.get(name)
    return getattr(value, name, None)


def _enum_value(value: Any) -> str:
    return getattr(value, "value", value)


def _openai_version_matches() -> bool:
    try:
        return importlib.metadata.version("openai").split("+", 1)[0] == _OPENAI_VERSION
    except importlib.metadata.PackageNotFoundError:
        return False


def _openai_runtime_symbols_available(
    *,
    responses: bool,
    chat: bool,
    embeddings: bool,
    audio_speech: bool,
    audio_transcriptions: bool,
) -> bool:
    try:
        openai_mod = importlib.import_module("openai")
    except Exception:
        return False
    AsyncOpenAI = getattr(openai_mod, "AsyncOpenAI", None)
    if not callable(AsyncOpenAI):
        return False
    try:
        client = AsyncOpenAI(api_key="sk-dummy")
    except Exception:
        return False
    audio = getattr(client, "audio", None)
    checks = (
        not responses or hasattr(client, "responses"),
        not chat or hasattr(getattr(client, "chat", None), "completions"),
        not embeddings or hasattr(client, "embeddings"),
        not audio_speech or hasattr(audio, "speech"),
        not audio_transcriptions or hasattr(audio, "transcriptions"),
    )
    return all(checks)
