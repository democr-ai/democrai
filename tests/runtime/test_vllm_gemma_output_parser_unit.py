from __future__ import annotations

from democrai.core.application.ai.output_parsers.registry import get_output_parser


def test_vllm_gemma_parser_extracts_raw_tool_call():
    parser = get_output_parser("vllm_gemma")

    parsed = parser.parse("call:system_test_echo_b352998447{text:diagnostica tool calling}")

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "system_test_echo_b352998447"
    assert parsed.tool_calls[0].arguments == '{"text": "diagnostica tool calling"}'


def test_vllm_gemma_stream_parser_buffers_raw_tool_call_until_complete():
    parser = get_output_parser("vllm_gemma")
    state = parser.new_stream_state()

    assert parser.feed(state, "call:system_test_echo_b352998447{text:diagnostica") == []
    outputs = parser.feed(state, " tool calling}")

    assert len(outputs) == 1
    assert outputs[0].content is None
    assert outputs[0].tool_calls[0].function_name == "system_test_echo_b352998447"
    assert outputs[0].tool_calls[0].arguments == '{"text": "diagnostica tool calling"}'


def test_vllm_gemma_parser_keeps_gemma_reasoning_channel():
    parser = get_output_parser("vllm_gemma")

    parsed = parser.parse("<|channel>thought\nReasoning text.<channel|>\nFinal answer.")

    assert parsed.reasoning == "Reasoning text."
    assert parsed.content == "Final answer."


def test_vllm_gemma_parser_splits_final_output_generation_tail():
    parser = get_output_parser("vllm_gemma")

    parsed = parser.parse(
        "thought\n"
        "Thinking Process:\n\n"
        "1. Analyze the input.\n"
        "2. Identify the content.\n"
        '6. Final Output Generation: Respond with a greeting. (E.g., "Ciao!", "Hello!", or a simple acknowledgment.)Ciao! 👋'
    )

    assert parsed.reasoning is not None
    assert "Final Output Generation:" in parsed.reasoning
    assert parsed.content == "Ciao! 👋"


def test_vllm_gemma_stream_parser_emits_inline_reasoning_deltas():
    parser = get_output_parser("vllm_gemma")
    state = parser.new_stream_state()

    first = parser.feed(state, "thought\nThinking Pro")
    second = parser.feed(state, "cess:\n\n1. Analyze")

    assert len(first) == 1
    assert first[0].reasoning == "Thinking Pro"
    assert first[0].content is None
    assert len(second) == 1
    assert second[0].reasoning == "cess:\n\n1. Analyze"
    assert second[0].content is None


def test_vllm_gemma_stream_parser_splits_inline_final_output_tail():
    parser = get_output_parser("vllm_gemma")
    state = parser.new_stream_state()

    first = parser.feed(
        state,
        "thought\nThinking Process:\n\n1. Analyze.\n6. Final Output Generation: Reply politely. (E.g., hi.)",
    )
    second = parser.feed(state, "Ciao!")

    assert len(first) == 1
    assert "Final Output Generation:" in (first[0].reasoning or "")
    assert first[0].content is None
    assert len(second) == 1
    assert second[0].reasoning is None
    assert second[0].content == "Ciao!"
