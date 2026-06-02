import asyncio
import base64
import json
import os
from typing import Any, AsyncGenerator, Dict, List

from democrai.sdk.engines import (
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    ContentPart,
    Message,
    MessageRole,
    StreamChunk,
    ToolCall,
)
from democrai.sdk.engines import BaseEngine, LLMProvider
from democrai.sdk.ai_constants import AICapability, AIModelFormat, AIModelSourceKind
from democrai.sdk.dependencies import ensure_import, install_python_packages


class GeminiEngine(BaseEngine, LLMProvider):
    engine_id = "gemini"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_python_packages(
            ["google-genai"],
            modules=["google.genai"],
            force=force,
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("google.genai", "google-genai")),
            ok_message="Gemini engine ready",
            error_message="Gemini engine requires shared state or local dependencies",
        )

    def __init__(self, config: dict):
        super().__init__(config)
        genai = ensure_import("google.genai", dependency_key="google_genai")
        self._types = ensure_import("google.genai.types", dependency_key="google_genai")
        self.client = genai.Client(
            api_key=self.api_key or os.environ.get("GOOGLE_API_KEY")
        )

    async def list_available_models(self) -> list[dict[str, Any]]:
        def _list_models():
            return list(self.client.models.list())

        rows = await asyncio.to_thread(_list_models)
        result: list[dict[str, Any]] = []
        for row in rows:
            raw_name = str(
                getattr(row, "name", "")
                or getattr(row, "id", "")
                or ""
            ).strip()
            if not raw_name:
                continue
            model_id = raw_name.removeprefix("models/")
            result.append(
                {
                    "id": model_id,
                    "label": model_id,
                    "source_kind": AIModelSourceKind.PROVIDER_API,
                    "format": AIModelFormat.REMOTE,
                    "capabilities": [
                        AICapability.CHAT,
                        AICapability.REASONING,
                    ],
                }
            )
        return result

    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        payload = self._build_request_payload(messages, options)
        response = await asyncio.to_thread(
            self.client.models.generate_content,
            model=self.model_name or "gemini-2.0-flash",
            contents=payload["contents"],
            config=payload["config"],
        )
        tool_calls = self._extract_tool_calls(response)
        return CompletionResponse(
            id="gemini",
            content=self._extract_text(response) if not tool_calls else None,
            reasoning=self._extract_reasoning(response),
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=self._extract_usage(response),
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        payload = self._build_request_payload(messages, options)
        stream = await asyncio.to_thread(
            lambda: list(
                self.client.models.generate_content_stream(
                    model=self.model_name or "gemini-2.0-flash",
                    contents=payload["contents"],
                    config=payload["config"],
                )
            )
        )
        final_usage = None
        finish_reason: str | None = None
        emitted_tool_call_ids: set[str] = set()
        for chunk in stream:
            final_usage = self._extract_usage(chunk) or final_usage
            finish_reason = self._extract_finish_reason(chunk) or finish_reason
            tool_calls = self._extract_tool_calls(chunk) or []
            for tool_call in tool_calls:
                if tool_call.id in emitted_tool_call_ids:
                    continue
                emitted_tool_call_ids.add(tool_call.id)
                yield StreamChunk(
                    id="gemini",
                    tool_call_delta=tool_call,
                )
            text = self._extract_text(chunk)
            reasoning = self._extract_reasoning(chunk)
            if text or reasoning:
                yield StreamChunk(id="gemini", delta=text or None, reasoning=reasoning)
        if final_usage is not None or finish_reason is not None:
            yield StreamChunk(
                id="gemini",
                delta=None,
                finish_reason=finish_reason or "stop",
                prompt_tokens=final_usage.prompt_tokens if final_usage else None,
                completion_tokens=final_usage.completion_tokens if final_usage else None,
                total_tokens=final_usage.total_tokens if final_usage else None,
            )
        if not stream:
            response = await self._generate_completion(messages, options)
            yield StreamChunk(id=response.id, delta=response.content)

    def _build_request_payload(
        self, messages: List[Message], options: CompletionOptions
    ) -> Dict[str, Any]:
        api_tools = None
        if options.tools:
            api_tools = [
                {
                    "function_declarations": [
                        {
                            "name": t.function.name,
                            "description": t.function.description or "",
                            "parameters": t.function.parameters,
                        }
                    ]
                }
                for t in options.tools
            ]
        cfg_kwargs: Dict[str, Any] = {
            "temperature": options.temperature,
            "top_p": options.top_p,
        }
        if options.max_tokens is not None:
            cfg_kwargs["max_output_tokens"] = options.max_tokens
        if options.stop:
            cfg_kwargs["stop_sequences"] = options.stop
        if api_tools:
            cfg_kwargs["tools"] = api_tools
        cfg_kwargs.update(self._request_extra(options.extra))
        config = self._types.GenerateContentConfig(**cfg_kwargs)
        return {
            "contents": [self._format_message(msg) for msg in messages],
            "config": config,
        }

    def _request_extra(self, extra: dict[str, Any]) -> dict[str, Any]:
        payload = dict(extra)
        reasoning = payload.pop("reasoning", None)
        budget = payload.pop("reasoning_budget", None)
        payload.pop("reasoning_param_name", None)
        if reasoning in (None, ""):
            return payload
        thinking_config = {
            "thinking_budget": 0
            if reasoning is False
            else _positive_int(budget, default=4096),
            "include_thoughts": reasoning is not False,
        }
        ThinkingConfig = getattr(self._types, "ThinkingConfig", None)
        payload["thinking_config"] = (
            ThinkingConfig(**thinking_config)
            if callable(ThinkingConfig)
            else thinking_config
        )
        return payload

    def _format_message(self, msg: Message) -> Dict[str, Any]:
        role = "user"
        if msg.role == MessageRole.ASSISTANT:
            role = "model"
        parts: List[Any] = []
        if msg.role == MessageRole.TOOL:
            parts.append(
                {
                    "function_response": {
                        "name": _tool_response_name(msg.tool_call_id),
                        "response": _tool_response_payload(msg.content),
                    }
                }
            )
            return {"role": role, "parts": parts}
        if msg.content:
            if isinstance(msg.content, str):
                parts.append({"text": msg.content})
            else:
                parts.extend(self._format_multimodal(msg.content))
        if msg.tool_calls:
            for tc in msg.tool_calls:
                part = {
                    "function_call": {
                        "name": tc.function_name,
                        "args": json.loads(tc.arguments),
                    }
                }
                thought_signature = _tool_call_thought_signature(tc.id)
                if thought_signature:
                    part["thought_signature"] = thought_signature
                parts.append(part)
        if not parts:
            parts = [{"text": ""}]
        return {"role": role, "parts": parts}

    def _format_multimodal(self, content: List[ContentPart]) -> List[Any]:
        parts: List[Any] = []
        for part in content:
            if part.type == "text" and part.text is not None:
                parts.append({"text": part.text})
            elif part.type == "image":
                if part.data:
                    parts.append(
                        {
                            "inline_data": {
                                "mime_type": part.mime_type or "image/jpeg",
                                "data": part.data,
                            }
                        }
                    )
                elif part.url:
                    parts.append({"text": f"[Image: {part.url}]"})
        return parts

    def _extract_text(self, response: Any) -> str:
        parts = []
        for part in _response_parts(response):
            if bool(_part_value(part, "thought")):
                continue
            text = _part_value(part, "text")
            if isinstance(text, str) and text:
                parts.append(text)
        if parts:
            return "".join(parts)
        return getattr(response, "text", None) or ""

    def _extract_reasoning(self, response: Any) -> str | None:
        chunks: list[str] = []
        for part in _response_parts(response):
            text = _part_value(part, "text")
            if bool(_part_value(part, "thought")) and isinstance(text, str) and text:
                chunks.append(text)
                continue
            for key in ("thought", "thinking", "reasoning"):
                value = _part_value(part, key)
                if isinstance(value, str) and value:
                    chunks.append(value)
        return "".join(chunks) or None

    def _extract_usage(self, response: Any) -> CompletionUsage | None:
        usage = getattr(response, "usage_metadata", None)
        if usage is None and isinstance(response, dict):
            usage = response.get("usage_metadata")
        if usage is None:
            return None
        prompt_tokens = _usage_int(usage, "prompt_token_count")
        completion_tokens = _usage_int(usage, "candidates_token_count")
        total_tokens = _usage_int(usage, "total_token_count")
        if total_tokens == 0:
            total_tokens = prompt_tokens + completion_tokens
        if prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0:
            return None
        return CompletionUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

    def _extract_finish_reason(self, response: Any) -> str | None:
        candidates = getattr(response, "candidates", None)
        if isinstance(response, dict):
            candidates = response.get("candidates")
        for candidate in list(candidates or []):
            raw = (
                candidate.get("finish_reason")
                if isinstance(candidate, dict)
                else getattr(candidate, "finish_reason", None)
            )
            if raw is None:
                continue
            name = getattr(raw, "name", None) or str(raw)
            resolved = str(name).strip().lower()
            if resolved and resolved != "finish_reason_unspecified":
                return resolved
        return None

    def _extract_tool_calls(self, response: Any) -> List[ToolCall] | None:
        extracted: List[ToolCall] = []
        for i, part in enumerate(_response_parts(response)):
            fn = _part_value(part, "function_call") or _part_value(part, "functionCall")
            if not fn:
                continue
            args = _part_value(fn, "args")
            name = _part_value(fn, "name") or ""
            extracted.append(
                ToolCall(
                    id=_gemini_tool_call_id(
                        name=name,
                        thought_signature=_part_value(part, "thought_signature")
                        or _part_value(part, "thoughtSignature"),
                    ),
                    function_name=name,
                    arguments=json.dumps(dict(args) if args else {}),
                )
            )
        return extracted or None


def _usage_int(usage: Any, key: str) -> int:
    if isinstance(usage, dict):
        value = usage.get(key)
    else:
        value = getattr(usage, key, None)
    try:
        return int(value or 0)
    except Exception:
        return 0


def _response_parts(response: Any) -> list[Any]:
    candidates = getattr(response, "candidates", None)
    if isinstance(response, dict):
        candidates = response.get("candidates")
    parts: list[Any] = []
    direct_parts = _value_parts(response)
    if direct_parts:
        parts.extend(direct_parts)
    for candidate in list(candidates or []):
        candidate_parts = _value_parts(candidate)
        if candidate_parts:
            parts.extend(candidate_parts)
            continue
        content = (
            candidate.get("content")
            if isinstance(candidate, dict)
            else getattr(candidate, "content", None)
        )
        parts.extend(_value_parts(content))
    return parts


def _value_parts(value: Any) -> list[Any]:
    if value is None:
        return []
    raw = value.get("parts") if isinstance(value, dict) else getattr(value, "parts", None)
    return list(raw or [])


def _part_value(part: Any, key: str) -> Any:
    if isinstance(part, dict):
        return part.get(key)
    return getattr(part, key, None)


def _tool_response_name(tool_call_id: str | None) -> str:
    if not tool_call_id:
        return "tool"
    try:
        parsed = json.loads(tool_call_id)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("name"):
        return str(parsed["name"])
    if ":" in tool_call_id:
        return tool_call_id.split(":", 1)[0]
    return tool_call_id


def _gemini_tool_call_id(*, name: Any, thought_signature: Any) -> str:
    if thought_signature:
        signature_payload: dict[str, Any]
        if isinstance(thought_signature, bytes):
            signature_payload = {
                "thought_signature_b64": base64.b64encode(thought_signature).decode(
                    "ascii"
                )
            }
        else:
            signature_payload = {"thought_signature": thought_signature}
        return json.dumps(
            {
                "name": str(name),
                **signature_payload,
            },
            separators=(",", ":"),
        )
    return str(name)


def _tool_call_thought_signature(tool_call_id: str | None) -> Any:
    if not tool_call_id:
        return None
    try:
        parsed = json.loads(tool_call_id)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if "thought_signature_b64" in parsed:
        return base64.b64decode(parsed["thought_signature_b64"])
    return parsed.get("thought_signature")


def _tool_response_payload(content: Any) -> dict[str, Any]:
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            return {"result": content}
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    if isinstance(content, dict):
        return content
    return {"result": content}


def _positive_int(value: Any, *, default: int) -> int:
    if value in (None, ""):
        return default
    result = int(value)
    if result < 0:
        raise ValueError("expected_non_negative_int")
    return result
