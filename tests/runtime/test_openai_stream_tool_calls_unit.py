from types import SimpleNamespace

import pytest

import engines.openai_compatible.engine as openai_compatible_engine_mod
from democrai.core.application.ai.engine.schemas.completion import (
    Function,
    Message,
    Tool,
    ToolCall,
)
from engines.openai.engine import OpenAIEngine
from engines.openai_compatible.engine import OpenAICompatibleEngine


@pytest.mark.asyncio
async def test_openai_stream_uses_responses_events():
    engine = OpenAIEngine.__new__(OpenAIEngine)
    engine.client = _openai_responses_client(
        [
            SimpleNamespace(
                type="response.output_text.delta",
                response_id="resp-1",
                delta="hel",
            ),
            SimpleNamespace(
                type="response.output_text.delta",
                response_id="resp-1",
                delta="lo",
            ),
            SimpleNamespace(
                type="response.output_item.done",
                response_id="resp-1",
                item=SimpleNamespace(
                    type="function_call",
                    call_id="call-1",
                    name="first",
                    arguments='{"a":1}',
                ),
            ),
            SimpleNamespace(
                type="response.completed",
                response=SimpleNamespace(
                    id="resp-1",
                    status="completed",
                    usage=SimpleNamespace(
                        input_tokens=3,
                        output_tokens=5,
                        total_tokens=8,
                    ),
                ),
            ),
        ]
    )
    engine.model_name = "gpt"

    chunks = [
        chunk
        async for chunk in engine._generate_stream(
            [],
            _options(),
        )
    ]

    assert engine.client.responses.create.kwargs["stream"] is True
    assert engine.client.responses.create.kwargs["max_output_tokens"] == 32
    assert "max_tokens" not in engine.client.responses.create.kwargs
    assert [chunk.delta for chunk in chunks if chunk.delta] == ["hel", "lo"]
    tool_calls = [chunk.tool_call_delta for chunk in chunks if chunk.tool_call_delta]
    assert [tool.function_name for tool in tool_calls] == ["first"]
    assert [tool.arguments for tool in tool_calls] == ['{"a":1}']
    stats = [chunk for chunk in chunks if chunk.total_tokens]
    assert stats[0].prompt_tokens == 3
    assert stats[0].completion_tokens == 5
    assert stats[0].total_tokens == 8


@pytest.mark.asyncio
async def test_openai_stream_uses_fallback_id_when_delta_event_has_no_response_id():
    engine = OpenAIEngine.__new__(OpenAIEngine)
    engine.client = _openai_responses_client(
        [
            SimpleNamespace(
                type="response.output_text.delta",
                delta="hello",
            ),
        ]
    )
    engine.model_name = "gpt"

    chunks = [
        chunk
        async for chunk in engine._generate_stream(
            [],
            _options(),
        )
    ]

    assert chunks[0].id == "openai-response-stream"
    assert chunks[0].delta == "hello"


def test_openai_response_payload_uses_official_reasoning_and_token_keys():
    engine = OpenAIEngine.__new__(OpenAIEngine)
    engine.model_name = "gpt"

    payload = engine._build_response_payload(
        [],
        _options(
            extra={
                "reasoning": "high",
                "reasoning_param_name": "reasoning_effort",
            },
            tools=[
                Tool(
                    function=Function(
                        name="lookup",
                        description="Lookup",
                        parameters={"type": "object"},
                    )
                )
            ],
        ),
        stream=False,
    )

    assert payload["max_output_tokens"] == 32
    assert "max_tokens" not in payload
    assert "temperature" not in payload
    assert "top_p" not in payload
    assert "reasoning_effort" not in payload
    assert payload["reasoning"] == {"effort": "high"}
    assert payload["tools"] == [
        {
            "type": "function",
            "name": "lookup",
            "description": "Lookup",
            "parameters": {"type": "object"},
        }
    ]


def test_openai_formats_tool_loop_as_responses_input_items():
    engine = OpenAIEngine.__new__(OpenAIEngine)

    payload = engine._format_input(
        [
            Message(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        function_name="lookup",
                        arguments='{"q":"demo"}',
                    )
                ],
            ),
            Message(
                role="tool",
                tool_call_id="call-1",
                content="result",
            ),
        ]
    )

    assert payload == [
        {
            "type": "function_call",
            "call_id": "call-1",
            "name": "lookup",
            "arguments": '{"q":"demo"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": "result",
        },
    ]


@pytest.mark.asyncio
async def test_openai_compatible_stream_emits_all_tool_calls_in_chunk(monkeypatch):
    monkeypatch.setattr(
        openai_compatible_engine_mod,
        "ensure_import",
        lambda name, dependency_key=None: SimpleNamespace(AsyncStream=None),
    )
    engine = OpenAICompatibleEngine.__new__(OpenAICompatibleEngine)
    engine.client = _openai_compatible_client(_stream_chunk())
    engine.model_name = "gpt"
    engine.config = {
        "request_parameter_mapping": [
            "max_tokens=max_completion_tokens",
            "temperature=",
            "top_p=",
        ]
    }

    chunks = [
        chunk
        async for chunk in engine._generate_stream(
            [],
            _options(),
        )
    ]

    tool_calls = [chunk.tool_call_delta for chunk in chunks if chunk.tool_call_delta]
    assert [tool.function_name for tool in tool_calls] == ["first", "second"]
    assert [tool.arguments for tool in tool_calls] == ['{"a":1}', '{"b":2}']
    request = engine.client.chat.completions.create.kwargs
    assert request["max_completion_tokens"] == 32
    assert "max_tokens" not in request
    assert "temperature" not in request
    assert "top_p" not in request
    assert "stop" not in request
    assert "tool_choice" not in request


def _options(*, extra=None, tools=None):
    return SimpleNamespace(
        tools=tools or [],
        temperature=0.7,
        top_p=0.9,
        max_tokens=32,
        stop=None,
        tool_choice=None,
        extra=extra or {},
    )


def _stream_chunk():
    return SimpleNamespace(
        id="chunk-1",
        choices=[
            SimpleNamespace(
                finish_reason=None,
                delta=SimpleNamespace(
                    content=None,
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="first",
                                arguments='{"a":1}',
                            ),
                        ),
                        SimpleNamespace(
                            id="call-2",
                            function=SimpleNamespace(
                                name="second",
                                arguments='{"b":2}',
                            ),
                        ),
                    ],
                ),
            )
        ],
    )


def _openai_compatible_client(chunk):
    return SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(
                create=_CreateStream([chunk]),
            )
        )
    )


def _openai_responses_client(events):
    return SimpleNamespace(
        responses=SimpleNamespace(
            create=_CreateStream(events),
        )
    )


class _CreateStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)
        self.kwargs = None

    async def __call__(self, **kwargs):
        self.kwargs = kwargs
        return _AsyncStream(self.chunks)


class _AsyncStream:
    def __init__(self, chunks):
        self.chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.chunks:
            raise StopAsyncIteration
        return self.chunks.pop(0)
