from types import SimpleNamespace

import pytest

import engines.vllm.engine as vllm_engine
from democrai.sdk.engines import get_output_parser
from engines.vllm.engine import VLLMEngine


def test_hermes_tool_call_parser_buffers_split_marker_prefixes():
    parser = get_output_parser("hermes")
    state = parser.new_stream_state()

    assert parser.feed(state, "<") == []
    assert parser.feed(state, "tool_") == []
    assert parser.feed(state, "call>") == []
    assert parser.feed(state, '{"name":"x","arguments":{}}') == []
    parsed = parser.feed(state, "</tool_call>")

    assert len(parsed) == 1
    assert parsed[0].tool_calls[0].function_name == "x"


def test_hermes_tool_call_parser_reads_xml_function_payload():
    parsed = get_output_parser("hermes").parse(
        "<tool_call><function=system.test_echo><parameter=text> Hello, World!",
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "system.test_echo"
    assert parsed.tool_calls[0].arguments == '{"text": "Hello, World!"}'


@pytest.mark.asyncio
async def test_vllm_stream_buffers_split_tool_call_marker(monkeypatch):
    monkeypatch.setattr(
        vllm_engine,
        "ensure_import",
        lambda name, dependency_key=None: SimpleNamespace(
            SamplingParams=lambda **kwargs: kwargs,
            RequestOutputKind=SimpleNamespace(DELTA="delta"),
        ),
    )
    engine = VLLMEngine.__new__(VLLMEngine)
    engine.output_parser = get_output_parser("hermes")
    engine._active_request_ids = set()
    engine.llm = _LLM(
        [
            _request_output("<", finished=False),
            _request_output("tool_", finished=False),
            _request_output("call>", finished=False),
            _request_output(
                '{"name":"system.test","arguments":{"value":1}}</tool_call>',
                finished=True,
            ),
        ]
    )

    chunks = [
        chunk
        async for chunk in engine._generate_stream(
            [],
            SimpleNamespace(
                extra={},
                temperature=0.7,
                top_p=0.9,
                max_tokens=32,
                stop=None,
                tools=[],
            ),
        )
    ]

    text_chunks = [chunk.delta for chunk in chunks if chunk.delta]
    tool_chunks = [chunk.tool_call_delta for chunk in chunks if chunk.tool_call_delta]
    assert text_chunks == [
        "<",
        "tool_",
        "call>",
        '{"name":"system.test","arguments":{"value":1}}</tool_call>',
    ]
    assert tool_chunks == []


@pytest.mark.asyncio
async def test_vllm_stream_parses_open_xml_tool_call(monkeypatch):
    monkeypatch.setattr(
        vllm_engine,
        "ensure_import",
        lambda name, dependency_key=None: SimpleNamespace(
            SamplingParams=lambda **kwargs: kwargs,
            RequestOutputKind=SimpleNamespace(DELTA="delta"),
        ),
    )
    engine = VLLMEngine.__new__(VLLMEngine)
    engine.output_parser = get_output_parser("hermes")
    engine._active_request_ids = set()
    engine.llm = _LLM(
        [
            _request_output("<tool_call>", finished=False),
            _request_output("<function=system.test_echo>", finished=False),
            _request_output("<parameter=text>Hello, World!", finished=True),
        ]
    )

    chunks = [
        chunk
        async for chunk in engine._generate_stream(
            [],
            SimpleNamespace(
                extra={},
                temperature=0.7,
                top_p=0.9,
                max_tokens=32,
                stop=None,
                tools=[],
            ),
        )
    ]

    text_chunks = [chunk.delta for chunk in chunks if chunk.delta]
    tool_chunks = [chunk.tool_call_delta for chunk in chunks if chunk.tool_call_delta]
    assert text_chunks == [
        "<tool_call>",
        "<function=system.test_echo>",
        "<parameter=text>Hello, World!",
    ]
    assert tool_chunks == []


def _request_output(text: str, *, finished: bool):
    return SimpleNamespace(
        request_id="request-1",
        prompt_token_ids=[1, 2],
        outputs=[
            SimpleNamespace(
                text=text,
                token_ids=[1],
                finish_reason="stop" if finished else None,
            )
        ],
        finished=finished,
    )


class _LLM:
    def __init__(self, outputs):
        self.llm_engine = _LLMEngine(outputs)

    def _preprocess_chat_one(self, *args, **kwargs):
        return {}


class _LLMEngine:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.request_id = ""

    def add_request(self, request_id, *args, **kwargs):
        self.request_id = request_id
        for output in self.outputs:
            output.request_id = request_id

    def step(self):
        return [self.outputs.pop(0)]
