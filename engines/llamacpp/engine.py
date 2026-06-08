import asyncio
import base64
import importlib.util
import json
from typing import Any, AsyncGenerator, List

from democrai.sdk.engines import (
    CompletionOptions,
    CompletionResponse,
    CompletionUsage,
    Message,
    MessageRole,
    StreamChunk,
    Tool,
    ToolCall,
)
from democrai.sdk.engines import BaseEngine, LLMProvider
from democrai.sdk.dependencies import ensure_import, install_python_packages
from engines.llamacpp.chat_handler import (
    build_chat_handler,
    build_multimodal_chat_handler,
    chat_handler_with_template_options,
    set_template_options,
)


def has_nvidia() -> bool:
    from democrai.sdk.system import has_nvidia as system_has_nvidia

    return system_has_nvidia()


class LlamaCppEngine(BaseEngine, LLMProvider):
    engine_id = "llamacpp"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        if has_nvidia():
            install_python_packages(
                ["llama-cpp-python"],
                modules=["llama_cpp"],
                force=force,
                allow_source=True,
                extra_pip_args=["--no-binary", "llama-cpp-python"],
                env={
                    "CMAKE_ARGS": "-DGGML_CUDA=on",
                    "FORCE_CMAKE": "1",
                },
            )
            return
        install_python_packages(
            ["llama-cpp-python"],
            modules=["llama_cpp"],
            force=force,
            allow_source=True,
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        missing_shared = cls._default_missing_shared()
        missing_local: list[str] = []
        if importlib.util.find_spec("llama_cpp") is None:
            missing_local.append("llama_cpp")

        return {
            "ready": not missing_shared and not missing_local,
            "missing_shared": missing_shared,
            "missing_local": missing_local,
            "message": (
                "llama.cpp engine ready"
                if not missing_shared and not missing_local
                else "llama.cpp engine requires shared or local dependencies"
            ),
        }

    def __init__(self, config: dict):
        super().__init__(config)

        llama_cpp = ensure_import("llama_cpp", dependency_key="llama_cpp")
        llama_cls = llama_cpp.Llama

        model_path = config.get("model_path")
        if not model_path:
            raise ValueError("LlamaCppEngine requires 'model_path' in config")

        self.llm = llama_cls(
            model_path=str(model_path),
            n_ctx=config.get("n_ctx", 2048),
            n_gpu_layers=config.get("n_gpu_layers", -1),
            verbose=config.get("verbose", False),
            **config.get("llama_kwargs", {}),
        )
        self.custom_chat_handler = build_chat_handler(self.llm, config)
        self.multimodal_chat_handler = build_multimodal_chat_handler(config)

    @classmethod
    def _validate_config(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "ready": True,
            "missing_config": [],
            "message": "",
        }

    def cleanup(self):
        pass

    async def _generate_completion(
        self, messages: List[Message], options: CompletionOptions
    ) -> CompletionResponse:
        has_images = _messages_have_images(messages)
        self._ensure_multimodal_ready(has_images=has_images)
        prompt = self._format_messages(messages, options)
        api_tools = self._format_tools(options.tools) if options.tools else None

        resp: Any = await asyncio.to_thread(
            lambda: self._create_chat_completion(
                has_images=has_images,
                template_options=_template_options(options.extra),
                kwargs={
                    "messages": prompt,
                    "temperature": options.temperature,
                    "top_p": options.top_p,
                    "max_tokens": options.max_tokens,
                    "stop": options.stop,
                    "tools": api_tools,
                    "tool_choice": options.tool_choice,
                    "stream": False,
                },
            ),
        )

        msg = resp["choices"][0]["message"]
        content = msg.get("content")
        usage = self._usage_from_response(resp)

        tool_calls = None
        if "tool_calls" in msg:
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    function_name=tc["function"]["name"],
                    arguments=(
                        tc["function"]["arguments"]
                        if isinstance(tc["function"]["arguments"], str)
                        else json.dumps(tc["function"]["arguments"])
                    ),
                )
                for tc in msg["tool_calls"]
            ]

        return CompletionResponse(
            id=resp["id"],
            content=content,
            role=MessageRole.ASSISTANT,
            tool_calls=tool_calls,
            usage=usage,
        )

    async def _generate_stream(
        self, messages: List[Message], options: CompletionOptions
    ) -> AsyncGenerator[StreamChunk, None]:
        has_images = _messages_have_images(messages)
        self._ensure_multimodal_ready(has_images=has_images)
        prompt = self._format_messages(messages, options)
        api_tools = self._format_tools(options.tools) if options.tools else None

        def _get_stream():
            return self._create_chat_completion(
                has_images=has_images,
                template_options=_template_options(options.extra),
                kwargs={
                    "messages": prompt,
                    "temperature": options.temperature,
                    "top_p": options.top_p,
                    "max_tokens": options.max_tokens,
                    "stop": options.stop,
                    "tools": api_tools,
                    "tool_choice": options.tool_choice,
                    "stream": True,
                },
            )

        stream = await asyncio.to_thread(_get_stream)
        prompt_tokens = _current_token_count(self.llm)
        saw_usage = False
        generated_text_parts: list[str] = []
        for chunk in stream:
            delta = chunk["choices"][0]["delta"]
            content = delta.get("content")
            if content:
                generated_text_parts.append(str(content))
            usage_values = self._stream_usage_from_chunk(chunk)
            saw_usage = saw_usage or bool(usage_values)

            tool_call_delta = None
            if delta.get("tool_calls"):
                tc = delta["tool_calls"][0]
                tool_call_delta = ToolCall(
                    id=tc.get("id") or "",
                    function_name=tc.get("function", {}).get("name") or "",
                    arguments=tc.get("function", {}).get("arguments") or "",
                )

            yield StreamChunk(
                id=chunk["id"],
                delta=content,
                tool_call_delta=tool_call_delta,
                finish_reason=chunk["choices"][0].get("finish_reason"),
                **usage_values,
            )
            await asyncio.sleep(0)
        if not saw_usage:
            usage_values = _stream_usage_from_llama(
                self.llm,
                prompt_tokens=prompt_tokens,
                generated_text="".join(generated_text_parts),
            )
            if usage_values:
                yield StreamChunk(id="usage", **usage_values)

    def _ensure_multimodal_ready(self, *, has_images: bool) -> None:
        if has_images and self.multimodal_chat_handler is None:
            raise ValueError("llamacpp_multimodal_projector_required")

    def _create_chat_completion(
        self,
        *,
        has_images: bool,
        template_options: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> Any:
        if not has_images and self.custom_chat_handler is None and not template_options:
            return self.llm.create_chat_completion(**kwargs)
        previous_chat_handler = getattr(self.llm, "chat_handler", None)
        handler = (
            self.multimodal_chat_handler if has_images else self.custom_chat_handler
        )
        restore_template_options = handler is not None
        if handler is None:
            handler = chat_handler_with_template_options(self.llm, template_options)
        else:
            set_template_options(handler, template_options)
        self.llm.chat_handler = handler
        try:
            return self.llm.create_chat_completion(**kwargs)
        finally:
            if restore_template_options:
                set_template_options(handler, {})
            self.llm.chat_handler = previous_chat_handler

    def _usage_from_response(self, response: dict[str, Any]) -> CompletionUsage | None:
        usage = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage, dict):
            return None
        return CompletionUsage(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )

    def _stream_usage_from_chunk(self, chunk: dict[str, Any]) -> dict[str, Any]:
        usage = chunk.get("usage") if isinstance(chunk, dict) else None
        if not isinstance(usage, dict):
            return {}
        return {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

    def _format_tools(self, tools: List[Tool]) -> List[Any]:
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

    def _format_messages(
        self,
        messages: List[Message],
        options: CompletionOptions | None = None,
    ) -> List[Any]:
        extra = (
            options.extra
            if options is not None and isinstance(options.extra, dict)
            else {}
        )
        reasoning = extra.get("reasoning")
        reasoning_level = str(reasoning or "").strip().lower()
        effective_messages = list(messages)
        if reasoning_level in {"low", "medium", "high"}:
            effective_messages = [
                Message(
                    role=MessageRole.SYSTEM,
                    content=f"Reasoning: {reasoning_level}",
                ),
                *effective_messages,
            ]
        if (
            options is not None
            and options.tools
            and _uses_qwen35_vl_template(self.config)
        ):
            effective_messages = _with_qwen35_vl_tool_prompt(
                effective_messages,
                options.tools,
            )
        formatted: List[Any] = []
        structured_tool_arguments = _uses_structured_tool_arguments(self.config)
        for msg in effective_messages:
            entry = {"role": msg.role.value, "content": msg.content or ""}

            if msg.tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function_name,
                            "arguments": _tool_arguments_for_prompt(
                                tc.arguments,
                                structured=structured_tool_arguments,
                            ),
                        },
                    }
                    for tc in msg.tool_calls
                ]

            if msg.tool_responses:
                entry["tool_responses"] = list(msg.tool_responses)

            if msg.tool_call_id:
                entry["tool_call_id"] = msg.tool_call_id

            if not isinstance(msg.content, str) and msg.content:
                raw_parts = list(msg.content)
                if not any(part.type == "image" for part in raw_parts):
                    entry["content"] = "".join(
                        str(part.text or "")
                        for part in raw_parts
                        if part.type == "text"
                    )
                    formatted.append(entry)
                    continue
                content_parts: list[dict[str, Any]] = []
                for part in raw_parts:
                    if part.type == "text":
                        content_parts.append(
                            {"type": "text", "text": str(part.text or "")}
                        )
                    elif part.type == "image" and part.data:
                        mime_type = str(part.mime_type or "image/png")
                        encoded = base64.b64encode(part.data).decode("ascii")
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{encoded}",
                                },
                            }
                        )
                    elif part.type == "image" and part.url:
                        content_parts.append(
                            {
                                "type": "image_url",
                                "image_url": {"url": str(part.url)},
                            }
                        )
                entry["content"] = content_parts

            formatted.append(entry)
        return formatted


def _messages_have_images(messages: List[Message]) -> bool:
    for message in messages:
        content = message.content
        if isinstance(content, list):
            for part in content:
                if part.type == "image":
                    return True
    return False


def _uses_structured_tool_arguments(config: dict[str, Any]) -> bool:
    return str(config.get("chat_template") or "").strip() == "gemma4_thinking"


def _uses_qwen35_vl_template(config: dict[str, Any]) -> bool:
    return str(config.get("chat_template") or "").strip() == "qwen35_vl_thinking"


def _with_qwen35_vl_tool_prompt(
    messages: list[Message],
    tools: list[Tool],
) -> list[Message]:
    prompt = _qwen35_vl_tool_prompt(tools)
    if messages and messages[0].role == MessageRole.SYSTEM:
        first = messages[0]
        content = str(first.content or "")
        return [
            first.model_copy(
                update={
                    "content": f"{prompt}\n\n{content}" if content else prompt,
                }
            ),
            *messages[1:],
        ]
    return [
        Message(
            role=MessageRole.SYSTEM,
            content=prompt,
        ),
        *messages,
    ]


def _qwen35_vl_tool_prompt(tools: list[Tool]) -> str:
    tool_specs = [
        {
            "type": "function",
            "function": {
                "name": tool.function.name,
                "description": tool.function.description,
                "parameters": tool.function.parameters,
            },
        }
        for tool in tools
    ]
    return (
        "# Tools\n\n"
        "You have access to the following functions:\n\n"
        "<tools>\n"
        + "\n".join(json.dumps(tool, ensure_ascii=False) for tool in tool_specs)
        + "\n</tools>\n\n"
        "If you choose to call a function ONLY reply in the following format with NO suffix:\n\n"
        "<tool_call>\n"
        "<function=example_function_name>\n"
        "<parameter=example_parameter_1>\n"
        "value_1\n"
        "</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )


def _tool_arguments_for_prompt(arguments: str, *, structured: bool) -> Any:
    if not structured:
        return arguments
    try:
        parsed = json.loads(arguments)
    except Exception:
        return arguments
    return parsed if isinstance(parsed, dict) else arguments


def _template_options(extra: dict[str, Any]) -> dict[str, Any]:
    if "reasoning" not in extra:
        return {}
    reasoning = extra.get("reasoning")
    if isinstance(reasoning, bool):
        return {"enable_thinking": reasoning}
    if isinstance(reasoning, str):
        normalized = reasoning.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return {"enable_thinking": True}
        if normalized in {"false", "0", "no", "off"}:
            return {"enable_thinking": False}
    return {}


def _current_token_count(llm: Any) -> int | None:
    value = getattr(llm, "n_tokens", None)
    return int(value) if isinstance(value, int) else None


def _stream_usage_from_llama(
    llm: Any,
    *,
    prompt_tokens: int | None,
    generated_text: str,
) -> dict[str, int]:
    total_tokens = _current_token_count(llm)
    if total_tokens is None:
        return {}
    completion_tokens = _completion_token_count(llm, generated_text)
    if prompt_tokens is None or prompt_tokens <= 0:
        prompt_tokens = max(total_tokens - completion_tokens, 0)
    if completion_tokens <= 0:
        completion_tokens = max(total_tokens - prompt_tokens, 0)
    total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


def _completion_token_count(llm: Any, text: str) -> int:
    if not text:
        return 0
    tokens = llm.tokenize(
        str(text).encode("utf-8"),
        add_bos=False,
        special=True,
    )
    return len(tokens)
