from types import SimpleNamespace

import pytest

import engines.vllm.engine as vllm_engine
from democrai.sdk.engines import get_output_parser
from engines.vllm.engine import VLLMEngine


@pytest.mark.asyncio
async def test_vllm_completion_exposes_reasoning_content(monkeypatch):
    monkeypatch.setattr(
        vllm_engine,
        "ensure_import",
        lambda name, dependency_key=None: SimpleNamespace(
            SamplingParams=lambda **kwargs: kwargs,
        ),
    )
    engine = VLLMEngine.__new__(VLLMEngine)
    engine.output_parser = get_output_parser()
    engine._active_request_ids = set()
    engine.llm = _LLM()

    response = await engine._generate_completion(
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

    assert response.content == "final answer"
    assert response.reasoning == "reasoning block"


def test_vllm_cancel_request_aborts_active_request():
    aborted = []
    engine = VLLMEngine.__new__(VLLMEngine)
    engine._active_request_ids = {"request-1"}
    engine.llm = SimpleNamespace(
        llm_engine=SimpleNamespace(
            abort_request=lambda value, internal=False: aborted.append(
                (value, internal)
            )
        )
    )

    engine.cancel_request("request-1")

    assert aborted == [(["request-1"], True)]


def test_qwen3_parser_moves_thinking_process_to_reasoning():
    parser = get_output_parser("qwen3")

    parsed = parser.parse("Thinking Process:\n\n1. Analyze\n\nFinal draft")

    assert parsed.reasoning == "Thinking Process:\n\n1. Analyze\n\nFinal draft"
    assert parsed.content is None


def test_qwen3_parser_moves_heres_thinking_process_to_reasoning():
    parser = get_output_parser("qwen3")

    parsed = parser.parse("Here's a thinking process:\n\n1. Analyze\n\nFinal draft")

    assert parsed.reasoning == "Here's a thinking process:\n\n1. Analyze\n\nFinal draft"
    assert parsed.content is None


def test_qwen3_stream_waits_for_thinking_process_marker():
    parser = get_output_parser("qwen3")
    state = parser.new_stream_state()

    assert parser.feed(state, "Thinking Process") == []
    chunks = parser.feed(state, ":\n\n1. Analyze")

    assert len(chunks) == 1
    assert chunks[0].reasoning == "Thinking Process:\n\n1. Analyze"
    assert chunks[0].content is None


def test_qwen3_stream_buffers_partial_tool_call():
    parser = get_output_parser("qwen3")
    state = parser.new_stream_state()

    assert parser.feed(state, "<tool_call>\n<function=system_test-echo") == []
    assert parser.feed(state, "_b352998447>\n<parameter=text>\ndiagnostica") == []
    chunks = parser.feed(
        state,
        " tool calling\n</parameter>\n</function>\n</tool_call>",
    )

    assert len(chunks) == 1
    assert chunks[0].content is None
    assert len(chunks[0].tool_calls) == 1
    tool_call = chunks[0].tool_calls[0]
    assert tool_call.function_name == "system_test-echo_b352998447"
    assert tool_call.arguments == '{"text": "diagnostica tool calling"}'


class _LLM:
    def __init__(self):
        self.llm_engine = _LLMEngine()

    def _preprocess_chat_one(self, *args, **kwargs):
        return {}


class _LLMEngine:
    def __init__(self):
        self.request_id = ""

    def add_request(self, request_id, *args, **kwargs):
        self.request_id = request_id

    def step(self):
        return [
            SimpleNamespace(
                request_id=self.request_id,
                prompt_token_ids=[1, 2],
                finished=True,
                outputs=[
                    SimpleNamespace(
                        text="final answer",
                        reasoning_content="reasoning block",
                        token_ids=[3, 4],
                        finish_reason="stop",
                    )
                ],
            )
        ]
