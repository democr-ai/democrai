import asyncio
import inspect
import json
import logging
import time
from typing import Any, AsyncGenerator, List

from democrai.sdk.engines import (
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    ContentType,
    EngineMethodResponse,
    EngineUsage,
    Message,
    MessageRole,
    StreamChunk,
    Tool,
    ToolCall,
)
from democrai.sdk.engines import BaseEngine, LLMProvider
from democrai.sdk.ai_constants import AIModelFormat, AIModelSourceKind
from democrai.sdk.dependencies import install_dependency

logger = logging.getLogger("main")


class OllamaEngine(BaseEngine, LLMProvider):
    engine_id = "ollama"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        install_dependency("ollama", force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_modules(("ollama", "ollama")),
            ok_message="Ollama engine ready",
            error_message="Ollama engine requires shared state or local dependencies",
        )

    def __init__(self, config: dict):
        super().__init__(config)
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.embedding_retry_attempts = max(
            1, int(config.get("embedding_retry_attempts", 3) or 1)
        )
        self.embedding_retry_delay_seconds = max(
            0.0, float(config.get("embedding_retry_delay_seconds", 2.0) or 0.0)
        )
        self.timeout_seconds = max(1, int(config.get("timeout_seconds", 60) or 60))

    def _build_client(self):
        from ollama import AsyncClient

        return AsyncClient(host=str(self.base_url or "").strip())

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if hasattr(value, "model_dump") and callable(getattr(value, "model_dump")):
            dumped = value.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        if hasattr(value, "dict") and callable(getattr(value, "dict")):
            dumped = value.dict()
            return dumped if isinstance(dumped, dict) else {}
        try:
            dumped = dict(value)
            return dumped if isinstance(dumped, dict) else {}
        except Exception:
            return {}

    async def _call_async(self, maybe_awaitable: Any) -> Any:
        if inspect.isawaitable(maybe_awaitable):
            return await maybe_awaitable
        return maybe_awaitable

    @staticmethod
    def _summary_from_details(details: dict[str, Any]) -> str:
        values = [
            details.get("family"),
            details.get("parameter_size"),
            details.get("quantization_level"),
        ]
        return " | ".join(
            str(value or "").strip() for value in values if str(value or "").strip()
        )

    @staticmethod
    def _model_capabilities(raw: Any) -> list[str]:
        source = raw if isinstance(raw, list) else []
        resolved: list[str] = []
        mapping = {
            "completion": "chat",
            "tools": "tool_calling",
            "thinking": "reasoning",
            "vision": "image_to_text",
            "embedding": "embedding",
        }
        for item in source:
            capability = mapping.get(str(item or "").strip().lower())
            if capability and capability not in resolved:
                resolved.append(capability)
        return resolved

    @staticmethod
    def _reasoning_enabled(extra: dict[str, Any]) -> bool | None:
        if extra.get("think") is not None:
            return bool(extra.get("think"))
        if extra.get("reasoning") is not None:
            return bool(extra.get("reasoning"))
        return None

    @staticmethod
    def _response_reasoning(*sources: dict[str, Any]) -> str:
        for source in sources:
            if not isinstance(source, dict):
                continue
            for key in ("thinking", "reasoning", "reasoning_content"):
                value = source.get(key)
                if value not in (None, ""):
                    return str(value)
        return ""

    async def list_available_models(self) -> list[dict[str, Any]]:
        client = self._build_client()
        data = self._as_dict(await self._call_async(client.list()))
        rows = data.get("models") if isinstance(data.get("models"), list) else []
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = self._as_dict(row)
            model_id = str(
                payload.get("model") or payload.get("name") or payload.get("id") or ""
            ).strip()
            if not model_id:
                continue
            details_payload = self._as_dict(
                await self._call_async(client.show(model=model_id))
            )
            details = self._as_dict(
                details_payload.get("details") or payload.get("details")
            )
            result.append(
                {
                    "id": model_id,
                    "label": model_id,
                    "capabilities": self._model_capabilities(
                        details_payload.get("capabilities")
                    ),
                    "source_kind": AIModelSourceKind.PROVIDER_API,
                    "format": AIModelFormat.REMOTE,
                    "summary": self._summary_from_details(details),
                }
            )
        return result

    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        extra = dict(options.extra or {})
        payload = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "tools": self._format_tools(options.tools) if options.tools else None,
            "options": {
                "temperature": options.temperature,
                "top_p": options.top_p,
                "stop": options.stop,
            },
        }
        if self.config.get("num_ctx") not in (None, ""):
            payload["options"]["num_ctx"] = int(self.config["num_ctx"])
        reasoning_enabled = self._reasoning_enabled(extra)
        if reasoning_enabled is not None:
            payload["think"] = reasoning_enabled
        if extra.get("format") is not None:
            payload["format"] = extra.get("format")
        try:
            client = self._build_client()
            data = self._as_dict(await self._call_async(client.chat(**payload)))
        except Exception as exc:
            raise RuntimeError(
                f"Ollama request failed at {self.base_url}: {exc}"
            ) from exc
        if "error" in data:
            raise RuntimeError(f"Ollama error: {data['error']}")
        msg = self._as_dict(data.get("message"))
        tool_calls = None
        if isinstance(msg.get("tool_calls"), list):
            tool_calls = [
                ToolCall(
                    id=f"ollama_{i}",
                    function_name=str(
                        self._as_dict(
                            tc.get("function") if isinstance(tc, dict) else {}
                        ).get("name")
                        or ""
                    ),
                    arguments=json.dumps(
                        self._as_dict(
                            tc.get("function") if isinstance(tc, dict) else {}
                        ).get("arguments")
                        or {}
                    ),
                )
                for i, tc in enumerate(msg.get("tool_calls") or [])
            ]
        return CompletionResponse(
            id="ollama",
            content=msg.get("content"),
            reasoning=self._response_reasoning(msg, data),
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=CompletionUsage(
                prompt_tokens=int(data.get("prompt_eval_count") or 0),
                completion_tokens=int(data.get("eval_count") or 0),
                total_tokens=int(
                    (data.get("prompt_eval_count") or 0) + (data.get("eval_count") or 0)
                ),
            ),
            finish_reason=data.get("done_reason"),
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        extra = dict(options.extra or {})
        payload = {
            "model": self.model_name,
            "messages": self._format_messages(messages),
            "tools": self._format_tools(options.tools) if options.tools else None,
            "options": {
                "temperature": options.temperature,
                "top_p": options.top_p,
                "stop": options.stop,
            },
        }
        if self.config.get("num_ctx") not in (None, ""):
            payload["options"]["num_ctx"] = int(self.config["num_ctx"])
        reasoning_enabled = self._reasoning_enabled(extra)
        if reasoning_enabled is not None:
            payload["think"] = reasoning_enabled
        if extra.get("format") is not None:
            payload["format"] = extra.get("format")
        try:
            client = self._build_client()
            stream_obj = await self._call_async(client.chat(**payload, stream=True))
            pending_tool_call: ToolCall | None = None
            async for raw_chunk in stream_obj:
                chunk = self._as_dict(raw_chunk)
                msg = self._as_dict(chunk.get("message"))
                done = bool(chunk.get("done"))

                raw_tool_calls = raw_chunk.message.tool_calls or []
                if raw_tool_calls:
                    first = self._as_dict(raw_tool_calls[0])
                    fn = self._as_dict(first.get("function"))
                    pending_tool_call = ToolCall(
                        id="ollama_stream",
                        function_name=str(fn.get("name") or ""),
                        arguments=json.dumps(fn.get("arguments") or {}),
                    )

                # Emetti la tool call come chunk dedicato PRIMA del chunk finale
                # (finish_reason="stop"): un consumatore che chiude lo stream sullo
                # stop non deve perderla.
                if done and pending_tool_call is not None:
                    yield StreamChunk(
                        id="ollama",
                        tool_call_delta=pending_tool_call,
                        finish_reason=None,
                    )
                    pending_tool_call = None

                yield StreamChunk(
                    id="ollama",
                    delta=msg.get("content", ""),
                    reasoning=self._response_reasoning(msg, chunk),
                    tool_call_delta=None,
                    finish_reason="stop" if done else None,
                    prompt_tokens=int(chunk.get("prompt_eval_count") or 0)
                    if done
                    else None,
                    completion_tokens=int(chunk.get("eval_count") or 0)
                    if done
                    else None,
                    total_tokens=int(
                        (chunk.get("prompt_eval_count") or 0)
                        + (chunk.get("eval_count") or 0)
                    )
                    if done
                    else None,
                )
            # Catch-all: lo stream e' finito senza un chunk "done" che la portasse.
            if pending_tool_call is not None:
                yield StreamChunk(
                    id="ollama",
                    tool_call_delta=pending_tool_call,
                    finish_reason=None,
                )
        except Exception as exc:
            raise RuntimeError(
                f"Ollama request failed at {self.base_url}: {exc}"
            ) from exc

    async def _embed_texts(self, texts: List[str]) -> EngineMethodResponse:
        if not texts:
            return EngineMethodResponse(result=[])
        started_at = time.monotonic()
        logger.info("[Embedding] provider=ollama model=%s start", self.model_name)
        client = self._build_client()
        vectors, prompt_tokens = await self._embed_batch_with_retry(
            client=client,
            texts=[str(text or "") for text in texts],
        )
        logger.info(
            "[Embedding] provider=ollama model=%s done elapsed_ms=%s",
            self.model_name,
            int((time.monotonic() - started_at) * 1000),
        )
        dimensions = len(vectors[0]) if vectors else 0
        return EngineMethodResponse(
            result=vectors,
            usage=EngineUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                total_tokens=prompt_tokens,
            ),
            metadata={
                "input_count": len(texts),
                "items": len(vectors),
                "dimensions": dimensions,
            },
        )

    async def _embed_batch_with_retry(
        self,
        *,
        client: Any,
        texts: list[str],
    ) -> tuple[List[List[float]], int]:
        last_error: Exception | None = None
        for attempt in range(1, self.embedding_retry_attempts + 1):
            try:
                response = await self._call_async(
                    client.embed(model=self.model_name, input=texts)
                )
                data = self._as_dict(response)
                if "error" in data:
                    raise RuntimeError(str(data.get("error") or "unknown error"))
                prompt_tokens = int(data.get("prompt_eval_count") or 0)
                embeddings = data.get("embeddings")
                if isinstance(embeddings, list):
                    return (
                        [list(item) for item in embeddings if isinstance(item, list)],
                        prompt_tokens,
                    )
                return [], prompt_tokens
            except Exception as exc:
                last_error = exc
                if (
                    self._should_retry_embedding_error(exc)
                    and attempt < self.embedding_retry_attempts
                ):
                    if self.embedding_retry_delay_seconds > 0:
                        await asyncio.sleep(self.embedding_retry_delay_seconds)
                    continue
                raise
        assert last_error is not None
        raise last_error

    def _should_retry_embedding_error(self, exc: Exception) -> bool:
        text = str(exc or "").lower()
        if any(
            token in text
            for token in ("cannot connect", "connection", "timeout", "timed out")
        ):
            return True
        return any(token in text for token in (" 500", " 502", " 503", " 504"))

    def _format_tools(self, tools: List[Tool]) -> List[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.function.name,
                    "description": t.function.description,
                    "parameters": t.function.parameters,
                },
            }
            for t in tools
        ]

    def _format_messages(self, messages: List[Message]) -> List[dict]:
        formatted = []
        for msg in messages:
            item = {"role": msg.role.value, "content": msg.content or ""}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": self._tool_arguments_for_prompt(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.role == MessageRole.TOOL:
                item["content"] = msg.content
            if msg.content and not isinstance(msg.content, str):
                item["content"] = ""
                item["images"] = []
                for part in msg.content:
                    if part.type == ContentType.TEXT:
                        item["content"] += part.text
                    elif part.type == ContentType.IMAGE and part.data:
                        import base64

                        item["images"].append(
                            base64.b64encode(part.data).decode("utf-8")
                        )
            formatted.append(item)
        return formatted

    @staticmethod
    def _tool_arguments_for_prompt(arguments: Any) -> dict[str, Any]:
        if isinstance(arguments, dict):
            return arguments
        if not isinstance(arguments, str) or not arguments.strip():
            return {}
        parsed = json.loads(arguments)
        if not isinstance(parsed, dict):
            raise ValueError("ollama_tool_arguments_object_required")
        return parsed
