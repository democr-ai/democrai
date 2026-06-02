from __future__ import annotations

from democrai.core.application.ai.output_parsers.registry import get_output_parser


def test_vllm_qwen_parser_extracts_xml_tool_call():
    parser = get_output_parser("vllm_qwen")

    parsed = parser.parse(
        "<tool_call><function=system_test_echo_b352998447>"
        "<parameter=text>diagnostica tool calling</parameter>"
        "</function></tool_call>"
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "system_test_echo_b352998447"
    assert parsed.tool_calls[0].arguments == '{"text": "diagnostica tool calling"}'


def test_vllm_qwen_stream_parser_buffers_xml_tool_call_until_complete():
    parser = get_output_parser("vllm_qwen")
    state = parser.new_stream_state()

    assert parser.feed(
        state,
        "<tool_call><function=system_test_echo_b352998447><parameter=text>diagnostica",
    ) == []
    outputs = parser.feed(state, " tool calling</parameter></function></tool_call>")

    assert len(outputs) == 1
    assert outputs[0].content is None
    assert outputs[0].tool_calls[0].function_name == "system_test_echo_b352998447"
    assert outputs[0].tool_calls[0].arguments == '{"text": "diagnostica tool calling"}'


def test_vllm_qwen_parser_keeps_reasoning():
    parser = get_output_parser("vllm_qwen")

    parsed = parser.parse("<think>Reasoning text.</think>Final answer.")

    assert parsed.reasoning == "Reasoning text."
    assert parsed.content == "Final answer."
