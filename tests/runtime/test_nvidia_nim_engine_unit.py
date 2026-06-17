from __future__ import annotations

from types import SimpleNamespace

import pytest

from democrai.sdk.engines import (
    CompletionOptions,
    ContentPart,
    ContentType,
    Function,
    Message,
    MessageRole,
    Tool,
)
from engines.nvidia_nim import engine as nim_engine


class FakeResponse:
    def __init__(
        self,
        *,
        json_data=None,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
        lines: list[bytes] | None = None,
        chunks: list[bytes] | None = None,
    ):
        self._json_data = json_data or {}
        self.content = content
        self.headers = headers or {}
        self._lines = lines or []
        self._chunks = chunks or []
        self.closed = False

    def json(self):
        return self._json_data

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self._lines)

    def iter_content(self, chunk_size=8192):
        del chunk_size
        return iter(self._chunks)

    def close(self):
        self.closed = True


class FakeRequests:
    def __init__(self):
        self.calls = []
        self.responses = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


@pytest.fixture()
def fake_requests(monkeypatch):
    fake = FakeRequests()
    monkeypatch.setattr(nim_engine, "ensure_import", lambda *args, **kwargs: fake)
    return fake


def make_engine(fake_requests, **config):
    values = {
        "base_url": "https://nim.example/v1/",
        "api_key": "secret",
        "model": "nvidia/test",
        "timeout_seconds": 7,
    }
    values.update(config)
    return nim_engine.NvidiaNimEngine(values)


@pytest.mark.asyncio
async def test_generate_completion_builds_chat_payload_with_tools_images_and_extra(fake_requests):
    fake_requests.responses.append(
        FakeResponse(
            json_data={
                "id": "cmpl-1",
                "choices": [
                    {
                        "message": {
                            "content": "hello",
                            "reasoning_content": "because",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {
                                        "name": "lookup",
                                        "arguments": "{\"q\":\"x\"}",
                                    },
                                }
                            ],
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 2,
                    "total_tokens": 5,
                },
            }
        )
    )
    provider = make_engine(fake_requests)
    messages = [
        Message(
            role=MessageRole.USER,
            content=[
                ContentPart(type=ContentType.TEXT, text="describe"),
                ContentPart(type=ContentType.IMAGE, data=b"img", mime_type="image/png"),
            ],
        )
    ]
    options = CompletionOptions(
        temperature=0.2,
        top_p=0.8,
        max_tokens=64,
        tools=[
            Tool(
                function=Function(
                    name="lookup",
                    description="lookup tool",
                    parameters={"type": "object"},
                )
            )
        ],
        tool_choice="auto",
        extra={"reasoning": {"effort": "high"}, "custom": 1},
    )

    response = await provider._generate_completion(messages, options)

    assert response.content == "hello"
    assert response.reasoning == "because"
    assert response.tool_calls[0].function_name == "lookup"
    assert response.usage.total_tokens == 5
    call = fake_requests.calls[0]
    assert call["url"] == "https://nim.example/v1/chat/completions"
    assert call["timeout"] == 7.0
    assert call["headers"]["Authorization"] == "Bearer secret"
    assert call["json"]["model"] == "nvidia/test"
    assert call["json"]["stream"] is False
    assert call["json"]["messages"][0]["content"][1]["image_url"]["url"] == "data:image/png;base64,aW1n"
    assert call["json"]["tools"][0]["function"]["name"] == "lookup"
    assert call["json"]["reasoning"] == {"effort": "high"}
    assert call["json"]["custom"] == 1


@pytest.mark.asyncio
async def test_generate_stream_parses_sse_reasoning_usage_and_done(fake_requests):
    fake_requests.responses.append(
        FakeResponse(
            lines=[
                b'data: {"id":"s1","choices":[{"delta":{"reasoning":"plan"},"finish_reason":null}]}',
                b'data: {"id":"s1","choices":[{"delta":{"content":"hi"},"finish_reason":null}]}',
                b'data: {"id":"s1","usage":{"prompt_tokens":4,"completion_tokens":3,"total_tokens":7},"choices":[]}',
                b"data: [DONE]",
                b'data: {"id":"ignored","choices":[{"delta":{"content":"x"}}]}',
            ]
        )
    )
    provider = make_engine(fake_requests)

    chunks = [
        chunk
        async for chunk in provider._generate_stream(
            [Message(role=MessageRole.USER, content="hello")],
            CompletionOptions(extra={"provider_specific": True}),
        )
    ]

    assert [chunk.reasoning for chunk in chunks if chunk.reasoning] == ["plan"]
    assert [chunk.delta for chunk in chunks if chunk.delta] == ["hi"]
    usage_chunks = [chunk for chunk in chunks if chunk.total_tokens]
    assert usage_chunks[0].prompt_tokens == 4
    assert usage_chunks[0].completion_tokens == 3
    assert fake_requests.calls[0]["json"]["stream"] is True
    assert fake_requests.calls[0]["json"]["stream_options"] == {"include_usage": True}
    assert fake_requests.calls[0]["json"]["provider_specific"] is True
    assert fake_requests.responses == []


@pytest.mark.asyncio
async def test_embed_texts_maps_vectors_and_usage(fake_requests):
    fake_requests.responses.append(
        FakeResponse(
            json_data={
                "data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}],
                "usage": {"prompt_tokens": 6, "total_tokens": 6},
            }
        )
    )
    provider = make_engine(fake_requests)

    response = await provider._embed_texts(["a", "b"])

    assert response.result == [[0.1, 0.2], [0.3, 0.4]]
    assert response.usage.prompt_tokens == 6
    assert response.metadata["dimensions"] == 2
    assert fake_requests.calls[0]["url"] == "https://nim.example/v1/embeddings"
    assert fake_requests.calls[0]["json"]["input"] == ["a", "b"]


@pytest.mark.asyncio
async def test_transcribe_uses_multipart_and_speech_base_url_fallback(fake_requests):
    fake_requests.responses.append(
        FakeResponse(json_data={"text": "ciao", "usage": {"input_tokens": 2, "output_tokens": 1}})
    )
    provider = make_engine(fake_requests, speech_base_url="")

    response = await provider.transcribe(b"RIFFxxxxWAVEdata", language="it")

    assert response["text"] == "ciao"
    assert response["usage"] == {
        "prompt_tokens": 2,
        "completion_tokens": 1,
        "total_tokens": 3,
    }
    call = fake_requests.calls[0]
    assert call["url"] == "https://nim.example/v1/audio/transcriptions"
    assert call["data"] == {"model": "nvidia/test", "language": "it"}
    file_name, file_obj, mime = call["files"]["file"]
    assert file_name == "audio.wav"
    assert file_obj.read().startswith(b"RIFF")
    assert mime == "audio/wav"
    assert "Content-Type" not in call["headers"]


@pytest.mark.asyncio
async def test_synthesize_and_stream_use_speech_base_url(fake_requests):
    fake_requests.responses.extend(
        [
            FakeResponse(content=b"audio", headers={"content-type": "audio/wav"}),
            FakeResponse(chunks=[b"a", b"b"]),
        ]
    )
    provider = make_engine(fake_requests, speech_base_url="https://speech.example/v1")
    options = SimpleNamespace(
        model=None,
        voice="luna",
        response_format="wav",
        speed=1.0,
    )

    response = await provider.synthesize("hello", options)
    chunks = [chunk async for chunk in provider.synthesize_stream("hello", options)]

    assert response["data"] == b"audio"
    assert response["content_type"] == "audio/wav"
    assert chunks == [b"a", b"b"]
    assert fake_requests.calls[0]["url"] == "https://speech.example/v1/audio/synthesize"
    assert fake_requests.calls[0]["json"] == {
        "model": "nvidia/test",
        "input": "hello",
        "voice": "luna",
        "response_format": "wav",
        "speed": 1.0,
    }
    assert fake_requests.calls[1]["url"] == "https://speech.example/v1/audio/synthesize_online"
    assert fake_requests.calls[1]["stream"] is True


def test_requires_base_url(fake_requests):
    with pytest.raises(ValueError, match="base_url_required"):
        nim_engine.NvidiaNimEngine({"model": "nvidia/test"})
