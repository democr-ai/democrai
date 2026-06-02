import os
from typing import Any, AsyncGenerator, Dict, List, cast

from democrai.sdk.engines import (
    BaseEngine,
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    EngineMethodResponse,
    EngineUsage,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
    LLMProvider,
)
from democrai.sdk.ai_constants import AIModelFormat, AIModelSourceKind
from democrai.sdk.dependencies import ensure_import, install_dependency


class OpenAICompatibleEngine(BaseEngine, LLMProvider):
    engine_id = "openai_compatible"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_dependency("openai", force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("openai", "openai")),
            ok_message="OpenAI-compatible engine ready",
            error_message="OpenAI-compatible engine requires shared state or local dependencies",
        )

    def __init__(self, config: dict):
        super().__init__(config)
        openai_mod = ensure_import("openai", dependency_key="openai")
        AsyncOpenAI = getattr(openai_mod, "AsyncOpenAI")
        self.client = AsyncOpenAI(
            api_key=self.api_key or os.environ.get("OPENAI_API_KEY"),
            base_url=self.base_url,
        )

    def _request_extra(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload = dict(extra)
        reasoning = payload.pop("reasoning", None)
        configured_param_name = str(
            payload.pop("reasoning_param_name", "") or ""
        ).strip()
        payload.pop("reasoning_budget", None)
        if reasoning in (None, "", False):
            return payload
        param_name = (
            configured_param_name
            if self._allow_reasoning_param_name_override() and configured_param_name
            else self._default_reasoning_param_name()
        )
        if not param_name:
            return payload
        payload[param_name] = self._reasoning_request_value(reasoning)
        return payload

    def _apply_request_parameter_mapping(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        config = getattr(self, "config", {})
        mappings = _request_parameter_mapping(config if isinstance(config, dict) else {})
        payload = _omit_none_values(payload)
        if not mappings:
            return payload
        resolved = dict(payload)
        for source, target in mappings:
            if source not in resolved:
                continue
            value = resolved.pop(source)
            if target:
                resolved[target] = value
        return resolved

    def _default_reasoning_param_name(self) -> str:
        return "reasoning"

    def _allow_reasoning_param_name_override(self) -> bool:
        return True

    def _reasoning_request_value(self, value: Any) -> Any:
        return value

    async def list_available_models(self) -> list[dict[str, Any]]:
        response = await self.client.models.list()
        rows = getattr(response, "data", None) or []
        result: list[dict[str, Any]] = []
        for row in rows:
            model_id = str(getattr(row, "id", "") or "").strip()
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
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        api_messages = self._format_messages(messages)
        api_tools = None
        if options.tools:
            api_tools = [
                {
                    "type": t.type,
                    "function": {
                        "name": t.function.name,
                        "description": t.function.description,
                        "parameters": t.function.parameters,
                    },
                }
                for t in options.tools
            ]

        payload = self._apply_request_parameter_mapping(
            {
                "model": self.model_name,
                "messages": cast(Any, api_messages),
                "temperature": options.temperature,
                "top_p": options.top_p,
                "max_tokens": options.max_tokens,
                "stream": False,
                "stop": options.stop,
                "tools": cast(Any, api_tools),
                "tool_choice": options.tool_choice,
                **self._request_extra(options.extra),
            }
        )
        resp = await self.client.chat.completions.create(**payload)
        choice = resp.choices[0]
        usage = None
        if resp.usage:
            usage = CompletionUsage(
                prompt_tokens=resp.usage.prompt_tokens,
                completion_tokens=resp.usage.completion_tokens,
                total_tokens=resp.usage.total_tokens,
            )
        tool_calls = None
        if choice.message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    function_name=cast(Any, tc).function.name,
                    arguments=cast(Any, tc).function.arguments,
                )
                for tc in choice.message.tool_calls
            ]
        return CompletionResponse(
            id=resp.id,
            content=choice.message.content,
            reasoning=self._extract_reasoning(choice.message),
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=choice.finish_reason,
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        api_messages = self._format_messages(messages)
        api_tools = None
        if options.tools:
            api_tools = [
                {
                    "type": t.type,
                    "function": {
                        "name": t.function.name,
                        "description": t.function.description,
                        "parameters": t.function.parameters,
                    },
                }
                for t in options.tools
            ]
        extra = self._request_extra(options.extra)
        stream_options = dict(extra.get("stream_options") or {})
        stream_options["include_usage"] = True
        extra["stream_options"] = stream_options
        payload = self._apply_request_parameter_mapping(
            {
                "model": self.model_name,
                "messages": cast(Any, api_messages),
                "temperature": options.temperature,
                "top_p": options.top_p,
                "max_tokens": options.max_tokens,
                "stream": True,
                "stop": options.stop,
                "tools": cast(Any, api_tools),
                "tool_choice": options.tool_choice,
                **extra,
            }
        )
        stream = await self.client.chat.completions.create(**payload)
        openai_mod = ensure_import("openai", dependency_key="openai")
        AsyncStream = getattr(openai_mod, "AsyncStream", None)
        if AsyncStream is not None:
            assert isinstance(stream, AsyncStream)
        async for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
                completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
                total_tokens = int(getattr(usage, "total_tokens", 0) or 0)
                if prompt_tokens or completion_tokens or total_tokens:
                    yield StreamChunk(
                        id=chunk.id,
                        delta=None,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        total_tokens=total_tokens,
                    )
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            emitted_tool_call = False
            if delta.tool_calls:
                for tc in cast(Any, delta.tool_calls):
                    yield StreamChunk(
                        id=chunk.id,
                        delta=None,
                        tool_call_delta=ToolCall(
                            id=tc.id or "",
                            function_name=tc.function.name or "",
                            arguments=tc.function.arguments or "",
                        ),
                        finish_reason=chunk.choices[0].finish_reason,
                    )
                    emitted_tool_call = True
            if delta.content or not emitted_tool_call:
                yield StreamChunk(
                    id=chunk.id,
                    delta=delta.content,
                    reasoning=getattr(delta, "reasoning_content", None)
                    or getattr(delta, "reasoning", None),
                    tool_call_delta=None,
                    finish_reason=chunk.choices[0].finish_reason,
                )

    async def _embed_texts(self, texts: List[str]) -> EngineMethodResponse:
        if not texts:
            return EngineMethodResponse(result=[])
        resp = await self.client.embeddings.create(
            model=self.model_name,
            input=[str(text or "") for text in texts],
        )
        vectors = [list(row.embedding) for row in resp.data]
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", prompt_tokens) or prompt_tokens)
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

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        formatted: List[Dict[str, Any]] = []
        for msg in messages:
            entry = {"role": _enum_value(msg.role)}
            content = msg.content
            if content:
                if isinstance(content, str):
                    entry["content"] = content
                else:
                    parts = []
                    for part in content:
                        part_type = _enum_value(part.type)
                        if part_type == "text":
                            parts.append({"type": "text", "text": part.text})
                        elif part_type == "image":
                            image_data = {"type": "image_url", "image_url": {}}
                            if part.url:
                                image_data["image_url"] = {"url": part.url}
                            elif part.data:
                                import base64

                                b64_str = base64.b64encode(part.data).decode("utf-8")
                                mime = part.mime_type or "image/jpeg"
                                image_data["image_url"] = {
                                    "url": f"data:{mime};base64,{b64_str}"
                                }
                            else:
                                raise ValueError("openai_compatible_image_data_required")
                            parts.append(image_data)
                    entry["content"] = parts
            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id
            formatted.append(entry)
        return formatted

    def _extract_reasoning(self, message: Any) -> str | None:
        reasoning = getattr(message, "reasoning_content", None) or getattr(
            message,
            "reasoning",
            None,
        )
        return str(reasoning) if reasoning else None


def _enum_value(value: Any) -> str:
    return getattr(value, "value", value)


def _omit_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _request_parameter_mapping(config: dict[str, Any]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    raw = config.get("request_parameter_mapping")
    if not isinstance(raw, list):
        return result
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("invalid_request_parameter_mapping")
        source, separator, target = item.partition("=")
        if not separator:
            raise ValueError("invalid_request_parameter_mapping")
        source = source.strip()
        target = target.strip()
        if not source:
            raise ValueError("invalid_request_parameter_mapping")
        result.append((source, target))
    return result
