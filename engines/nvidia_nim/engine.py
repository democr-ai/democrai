from __future__ import annotations

import asyncio
import base64
import importlib
import importlib.metadata
import io
import json
from typing import Any, AsyncGenerator, Iterable, List, cast

from democrai.sdk.dependencies import ensure_engine_venv, ensure_import, install_python_packages
from democrai.sdk.engines import (
    BaseEngine,
    BaseSTTProvider,
    BaseTTSProvider,
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


_REQUESTS_PACKAGE = "requests==2.34.2"
_REQUESTS_VERSION = "2.34.2"
_READY_MODULES = ("requests", "urllib3", "certifi")


class NvidiaNimEngine(BaseEngine, LLMProvider, BaseSTTProvider, BaseTTSProvider):
    engine_id = "nvidia_nim"

    @classmethod
    def _install(
        cls,
        force: bool = False,
        *,
        node_id: str | None = None,
        source_node_id: str | None = None,
    ) -> None:
        ensure_engine_venv()
        install_python_packages([_REQUESTS_PACKAGE], modules=["requests"], force=force)

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        del node_id
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._missing_module_labels(),
            ok_message="NVIDIA NIM engine ready",
            error_message="NVIDIA NIM engine requires shared state or local dependencies",
        )

    @classmethod
    def _missing_module_labels(cls) -> list[str]:
        missing: list[str] = []
        for module_name in _READY_MODULES:
            missing.extend(cls._missing_modules((module_name, module_name)))
        if not _requests_version_matches():
            missing.append(_REQUESTS_PACKAGE)
        if not _requests_runtime_symbols_available():
            missing.append("NVIDIA NIM requests runtime")
        return missing

    def __init__(self, config: dict):
        BaseEngine.__init__(self, config)
        BaseSTTProvider.__init__(self, config)
        BaseTTSProvider.__init__(self, config)
        self._requests = ensure_import("requests", dependency_key="requests")
        self.base_url = _required_text(config.get("base_url"), "base_url")
        self.speech_base_url = _optional_text(config.get("speech_base_url")) or self.base_url
        self.timeout_seconds = float(config.get("timeout_seconds") or 60)

    async def _generate_completion(
        self,
        messages: List[Message],
        options: CompletionOptions,
    ) -> CompletionResponse:
        payload = self._completion_payload(messages, options, stream=False)
        data = await asyncio.to_thread(self._post_json, self.base_url, "chat/completions", payload)
        return _completion_response(data)

    async def _generate_stream(
        self,
        messages: List[Message],
        options: CompletionOptions,
    ) -> AsyncGenerator[StreamChunk, None]:
        payload = self._completion_payload(messages, options, stream=True)
        async for chunk in self._stream_sse(self.base_url, "chat/completions", payload):
            yield chunk

    async def _embed_texts(self, texts: List[str]) -> EngineMethodResponse:
        if not texts:
            return EngineMethodResponse(result=[])
        payload = {
            "model": self.model_name,
            "input": [str(text or "") for text in texts],
        }
        data = await asyncio.to_thread(self._post_json, self.base_url, "embeddings", payload)
        vectors = [list(row.get("embedding") or []) for row in data.get("data") or []]
        usage = _engine_usage(data.get("usage"))
        return EngineMethodResponse(
            result=vectors,
            usage=usage,
            metadata={
                "input_count": len(texts),
                "items": len(vectors),
                "dimensions": len(vectors[0]) if vectors else 0,
            },
        )

    async def transcribe(
        self,
        audio_data: bytes,
        language: str | None = None,
    ) -> dict[str, Any]:
        def call() -> dict[str, Any]:
            audio_file = io.BytesIO(audio_data)
            audio_file.name = _audio_upload_name(audio_data)
            data: dict[str, Any] = {"model": self.model_name}
            if language:
                data["language"] = language
            response = self._requests.post(
                _api_url(self.speech_base_url, "audio/transcriptions"),
                headers=self._headers(),
                data=_omit_none_values(data),
                files={"file": (audio_file.name, audio_file, _audio_mime_type(audio_file.name))},
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            return cast(dict[str, Any], response.json())

        data = await asyncio.to_thread(call)
        result: dict[str, Any] = {"text": str(data.get("text") or "")}
        usage = _usage_dict(data.get("usage"))
        if usage is not None:
            result["usage"] = usage
            result["usage_metadata"] = {"usage_source": "provider"}
        return result

    async def synthesize(self, text: str, options: Any) -> dict[str, Any]:
        payload = self._tts_payload(text, options)

        def call() -> tuple[bytes, str]:
            response = self._requests.post(
                _api_url(self.speech_base_url, "audio/synthesize"),
                headers=self._headers(content_type="application/json"),
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            content_type = str(response.headers.get("content-type") or "audio/wav")
            return bytes(response.content), content_type

        data, content_type = await asyncio.to_thread(call)
        return {
            "data": data,
            "content_type": content_type,
            "usage": {
                "input_characters": len(text),
                "audio_bytes": len(data),
            },
            "usage_metadata": {
                "usage_source": "local",
                "usage_calculation": "engines.nvidia_nim.engine.NvidiaNimEngine.synthesize",
            },
        }

    async def synthesize_stream(
        self,
        text: str,
        options: Any,
    ) -> AsyncGenerator[bytes, None]:
        payload = self._tts_payload(text, options)
        queue: asyncio.Queue[bytes | None | BaseException] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def publish(item: bytes | None | BaseException) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def producer() -> None:
            response = None
            try:
                response = self._requests.post(
                    _api_url(self.speech_base_url, "audio/synthesize_online"),
                    headers=self._headers(content_type="application/json"),
                    json=payload,
                    stream=True,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        publish(bytes(chunk))
                publish(None)
            except BaseException as exc:
                publish(exc)
            finally:
                if response is not None:
                    response.close()

        task = asyncio.create_task(asyncio.to_thread(producer))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            await task

    def _completion_payload(
        self,
        messages: list[Message],
        options: CompletionOptions,
        *,
        stream: bool,
    ) -> dict[str, Any]:
        api_tools = None
        if options.tools:
            api_tools = [
                {
                    "type": tool.type,
                    "function": {
                        "name": tool.function.name,
                        "description": tool.function.description,
                        "parameters": tool.function.parameters,
                    },
                }
                for tool in options.tools
            ]
        extra = dict(options.extra or {})
        if stream:
            stream_options = dict(extra.get("stream_options") or {})
            stream_options["include_usage"] = True
            extra["stream_options"] = stream_options
        return _omit_none_values(
            {
                "model": self.model_name,
                "messages": self._format_messages(messages),
                "temperature": options.temperature,
                "top_p": options.top_p,
                "max_tokens": options.max_tokens,
                "stream": stream,
                "stop": options.stop,
                "tools": api_tools,
                "tool_choice": options.tool_choice,
                **extra,
            }
        )

    def _post_json(
        self,
        base_url: str,
        path: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._requests.post(
            _api_url(base_url, path),
            headers=self._headers(content_type="application/json"),
            json=payload,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        return cast(dict[str, Any], response.json())

    async def _stream_sse(
        self,
        base_url: str,
        path: str,
        payload: dict[str, Any],
    ) -> AsyncGenerator[StreamChunk, None]:
        queue: asyncio.Queue[StreamChunk | None | BaseException] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def publish(item: StreamChunk | None | BaseException) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, item)

        def producer() -> None:
            response = None
            try:
                response = self._requests.post(
                    _api_url(base_url, path),
                    headers=self._headers(content_type="application/json"),
                    json=payload,
                    stream=True,
                    timeout=self.timeout_seconds,
                )
                response.raise_for_status()
                for item in _iter_sse_events(response.iter_lines()):
                    if item == "[DONE]":
                        break
                    for chunk in _stream_chunks(json.loads(item)):
                        publish(chunk)
                publish(None)
            except BaseException as exc:
                publish(exc)
            finally:
                if response is not None:
                    response.close()

        task = asyncio.create_task(asyncio.to_thread(producer))
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            await task

    def _headers(self, *, content_type: str | None = None) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _format_messages(self, messages: list[Message]) -> list[dict[str, Any]]:
        formatted: list[dict[str, Any]] = []
        for message in messages:
            entry: dict[str, Any] = {"role": _enum_value(message.role)}
            if message.content:
                entry["content"] = _message_content(message.content)
            if message.tool_calls:
                entry["tool_calls"] = [_tool_call_payload(tool_call) for tool_call in message.tool_calls]
            if message.tool_call_id:
                entry["tool_call_id"] = message.tool_call_id
            if message.tool_responses:
                entry["tool_responses"] = message.tool_responses
            formatted.append(entry)
        return formatted

    def _tts_payload(self, text: str, options: Any) -> dict[str, Any]:
        return _omit_none_values(
            {
                "model": getattr(options, "model", None) or self.model_name,
                "input": text,
                "voice": getattr(options, "voice", None),
                "response_format": getattr(options, "response_format", None),
                "speed": getattr(options, "speed", None),
            }
        )


def _api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _required_text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{field}_required")
    return text


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _message_content(content: Any) -> Any:
    if isinstance(content, str):
        return content
    parts: list[dict[str, Any]] = []
    for part in content:
        part_type = _enum_value(part.type)
        if part_type == "text":
            parts.append({"type": "text", "text": part.text})
        elif part_type == "image":
            parts.append({"type": "image_url", "image_url": {"url": _image_url(part)}})
        else:
            parts.append(_omit_none_values({"type": part_type, "text": part.text, "url": part.url}))
    return parts


def _image_url(part: Any) -> str:
    if part.url:
        return str(part.url)
    if part.data:
        data = bytes(part.data)
        encoded = base64.b64encode(data).decode("utf-8")
        mime = part.mime_type or "image/jpeg"
        return f"data:{mime};base64,{encoded}"
    raise ValueError("nvidia_nim_image_data_required")


def _tool_call_payload(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "type": tool_call.type,
        "function": {
            "name": tool_call.function_name,
            "arguments": tool_call.arguments,
        },
    }


def _tool_call(value: dict[str, Any]) -> ToolCall:
    function = value.get("function") if isinstance(value.get("function"), dict) else {}
    return ToolCall(
        id=str(value.get("id") or ""),
        type=str(value.get("type") or "function"),
        function_name=str(function.get("name") or ""),
        arguments=str(function.get("arguments") or ""),
    )


def _completion_response(data: dict[str, Any]) -> CompletionResponse:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    usage = _completion_usage(data.get("usage"))
    tool_calls = None
    if message.get("tool_calls"):
        tool_calls = [_tool_call(item) for item in message.get("tool_calls") or []]
    return CompletionResponse(
        id=str(data.get("id") or ""),
        content=message.get("content"),
        reasoning=_reasoning_value(message),
        role=MessageRole.ASSISTANT,
        tool_calls=tool_calls,
        usage=usage,
        finish_reason=choice.get("finish_reason"),
    )


def _iter_sse_events(lines: Iterable[Any]) -> Iterable[str]:
    for raw_line in lines:
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else str(raw_line)
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        yield line[5:].strip()


def _stream_chunks(data: dict[str, Any]) -> list[StreamChunk]:
    chunks: list[StreamChunk] = []
    usage = _usage_dict(data.get("usage"))
    if usage is not None:
        chunks.append(
            StreamChunk(
                id=str(data.get("id") or "stream"),
                delta=None,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                total_tokens=usage["total_tokens"],
            )
        )
    for choice in data.get("choices") or []:
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        finish_reason = choice.get("finish_reason")
        emitted_tool_call = False
        for tool_call in delta.get("tool_calls") or []:
            chunks.append(
                StreamChunk(
                    id=str(data.get("id") or "stream"),
                    delta=None,
                    tool_call_delta=_tool_call(tool_call),
                    finish_reason=finish_reason,
                )
            )
            emitted_tool_call = True
        if delta.get("content") or _reasoning_value(delta) or not emitted_tool_call:
            chunks.append(
                StreamChunk(
                    id=str(data.get("id") or "stream"),
                    delta=delta.get("content"),
                    reasoning=_reasoning_value(delta),
                    finish_reason=finish_reason,
                )
            )
    return chunks


def _completion_usage(value: Any) -> CompletionUsage | None:
    usage = _usage_dict(value)
    if usage is None:
        return None
    return CompletionUsage(**usage)


def _engine_usage(value: Any) -> EngineUsage:
    usage = _usage_dict(value)
    if usage is None:
        return EngineUsage()
    return EngineUsage(**usage)


def _usage_dict(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    prompt_tokens = _int_value(value, "prompt_tokens", "input_tokens")
    completion_tokens = _int_value(value, "completion_tokens", "output_tokens")
    total_tokens = _int_value(value, "total_tokens")
    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = int(prompt_tokens or 0) + int(completion_tokens or 0)
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        return None
    return {
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "total_tokens": int(total_tokens or 0),
    }


def _int_value(value: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        try:
            return int(raw)
        except Exception:
            return None
    return None


def _reasoning_value(value: dict[str, Any]) -> str | None:
    reasoning = value.get("reasoning_content")
    if reasoning is None:
        reasoning = value.get("reasoning")
    return str(reasoning) if reasoning else None


def _omit_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _audio_upload_name(audio_data: bytes) -> str:
    header = bytes(audio_data[:32])
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "audio.wav"
    if header.startswith(b"ID3") or header[:2] in {b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"}:
        return "audio.mp3"
    if header.startswith(b"OggS"):
        return "audio.ogg"
    if header.startswith(b"fLaC"):
        return "audio.flac"
    if header.startswith(b"\x1a\x45\xdf\xa3"):
        return "audio.webm"
    if b"ftyp" in header[:16]:
        return "audio.m4a"
    return "audio.wav"


def _audio_mime_type(name: str) -> str:
    if name.endswith(".mp3"):
        return "audio/mpeg"
    if name.endswith(".ogg"):
        return "audio/ogg"
    if name.endswith(".flac"):
        return "audio/flac"
    if name.endswith(".webm"):
        return "audio/webm"
    if name.endswith(".m4a"):
        return "audio/mp4"
    return "audio/wav"


def _requests_version_matches() -> bool:
    try:
        return importlib.metadata.version("requests").split("+", 1)[0] == _REQUESTS_VERSION
    except importlib.metadata.PackageNotFoundError:
        return False


def _requests_runtime_symbols_available() -> bool:
    try:
        requests_mod = importlib.import_module("requests")
    except Exception:
        return False
    return callable(getattr(requests_mod, "post", None)) and callable(
        getattr(requests_mod, "Session", None)
    )
