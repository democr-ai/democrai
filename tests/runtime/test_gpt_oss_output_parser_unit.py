from __future__ import annotations

from democrai.core.application.ai.output_parsers.registry import get_output_parser


def test_gpt_oss_parser_extracts_analysis_and_final():
    parser = get_output_parser("gpt_oss")

    parsed = parser.parse(
        '<|channel|>analysis<|message|>Think this through.<|end|>'
        '<|start|>assistant<|channel|>final<|message|>Sure.<|end|>'
    )

    assert parsed.reasoning == "Think this through."
    assert parsed.content == "Sure."


def test_gpt_oss_stream_parser_emits_final_delta_without_raw_markers():
    parser = get_output_parser("gpt_oss")
    state = parser.new_stream_state()

    first = parser.feed(state, "<|channel|>analysis<|message|>Reason")
    second = parser.feed(state, "ing.<|end|><|start|>assistant")
    third = parser.feed(state, "<|channel|>final<|message|>Su")
    fourth = parser.feed(state, "re.<|end|>")

    assert first[0].reasoning == "Reason"
    assert first[0].content is None
    assert second[0].reasoning == "ing."
    assert second[0].content is None
    assert third[0].reasoning is None
    assert third[0].content == "Su"
    assert fourth[0].reasoning is None
    assert fourth[0].content == "re."
    assert parser.finish(state) == []


def test_gpt_oss_parser_removes_leading_channel_fragment_from_final_message():
    parser = get_output_parser("gpt_oss")

    parsed = parser.parse(
        '<|channel|>analysis<|message|>Reasoning.<|end|>'
        '<|start|>assistant<|channel|>final<|message|>'
        '<|channel|>analysFinal answer.<|end|>'
    )

    assert parsed.reasoning == "Reasoning."
    assert parsed.content == "Final answer."


def test_gpt_oss_parser_handles_channels_without_message_marker():
    parser = get_output_parser("gpt_oss")

    parsed = parser.parse(
        '<|channel|>analysisReasoning without message marker.<|end|>'
        '<|channel|>finalFinal answer without message marker.<|end|>'
    )

    assert parsed.reasoning == "Reasoning without message marker."
    assert parsed.content == "Final answer without message marker."


def test_gpt_oss_stream_waits_for_partial_channel_before_emitting():
    parser = get_output_parser("gpt_oss")
    state = parser.new_stream_state()

    assert parser.feed(state, "<|channel|>analys") == []
    first = parser.feed(state, "isReason")
    second = parser.feed(state, "ing.<|end|><|channel|>finalAn")
    third = parser.feed(state, "swer.<|end|>")

    assert first[0].reasoning == "Reason"
    assert first[0].content is None
    assert second[0].reasoning == "ing."
    assert second[0].content == "An"
    assert third[0].reasoning is None
    assert third[0].content == "swer."


def test_gpt_oss_parser_extracts_commentary_function_call():
    parser = get_output_parser("gpt_oss")

    parsed = parser.parse(
        '<|channel|>analysis<|message|>Need a tool.<|end|>'
        '<|start|>assistant<|channel|>commentary to=functions.system.test_echo '
        '<|constrain|>json<|message|>{"text":"scemo chi legge"}<|end|>'
    )

    assert parsed.reasoning == "Need a tool."
    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "system.test_echo"
    assert parsed.tool_calls[0].arguments == '{"text": "scemo chi legge"}'


def test_gpt_oss_stream_parser_emits_commentary_function_call_once():
    parser = get_output_parser("gpt_oss")
    state = parser.new_stream_state()

    assert parser.feed(state, "<|channel|>commentary to=functions.system.test_echo ") == []
    assert parser.feed(state, '<|constrain|>json<|message|>{"text"') == []
    emitted = parser.feed(state, ':"scemo chi legge"}<|end|>')

    assert len(emitted) == 1
    assert emitted[0].tool_calls[0].function_name == "system.test_echo"
    assert emitted[0].tool_calls[0].arguments == '{"text": "scemo chi legge"}'
    assert parser.finish(state) == []
