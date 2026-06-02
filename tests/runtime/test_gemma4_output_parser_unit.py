from __future__ import annotations

from democrai.core.application.ai.output_parsers.registry import get_output_parser


def test_gemma4_parser_extracts_thought_channel():
    parser = get_output_parser("gemma4")

    parsed = parser.parse(
        "<|channel>thought\nReasoning text.<channel|>\nFinal answer."
    )

    assert parsed.reasoning == "Reasoning text."
    assert parsed.content == "Final answer."


def test_gemma4_parser_extracts_bare_reasoning_before_channel_end():
    parser = get_output_parser("gemma4")

    parsed = parser.parse("Reasoning text.<channel|>\nFinal answer.")

    assert parsed.reasoning == "Reasoning text."
    assert parsed.content == "Final answer."


def test_gemma4_parser_extracts_native_tool_call():
    parser = get_output_parser("gemma4")

    parsed = parser.parse(
        '<|tool_call>call:system.test_echo{text:<|"|>scemo chi legge<|"|>}<tool_call|>'
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "system.test_echo"
    assert parsed.tool_calls[0].arguments == '{"text": "scemo chi legge"}'


def test_gemma4_parser_extracts_tool_call_with_wrapped_json_object_body():
    parser = get_output_parser("gemma4")

    parsed = parser.parse(
        '<|tool_call>call:agent_chat.component-agent_72091346a0'
        '{{"input":<|"|>Genera una card di esempio.<|"|>}}<tool_call|>'
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert (
        parsed.tool_calls[0].function_name
        == "agent_chat.component-agent_72091346a0"
    )
    assert parsed.tool_calls[0].arguments == '{"input": "Genera una card di esempio."}'


def test_gemma4_parser_strips_orphan_tool_end_before_content():
    parser = get_output_parser("gemma4")

    parsed = parser.parse("<tool_call|>Ecco un riassunto strutturato.")

    assert parsed.content == "Ecco un riassunto strutturato."
    assert parsed.tool_calls == []


def test_gemma4_parser_strips_orphan_quote_before_content():
    parser = get_output_parser("gemma4")

    parsed = parser.parse('<|"|>Ecco un riassunto strutturato.')

    assert parsed.content == "Ecco un riassunto strutturato."
    assert parsed.tool_calls == []


def test_gemma4_stream_parser_emits_reasoning_and_final_deltas():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    assert parser.feed(state, "<|chan") == []
    first = parser.feed(state, "nel>thought\nRea")
    second = parser.feed(state, "soning.<channel|>Fi")
    third = parser.feed(state, "nal.")

    assert first[0].reasoning == "Rea"
    assert first[0].content is None
    assert second[0].reasoning == "soning."
    assert second[0].content == "Fi"
    assert third[0].reasoning is None
    assert third[0].content == "nal."


def test_gemma4_stream_parser_does_not_emit_empty_thought_label():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    first = parser.feed(state, "<|channel>thought")
    second = parser.feed(state, "Reasoning.<channel|>Final.")

    assert first == []
    assert second[0].reasoning == "Reasoning."
    assert second[0].content == "Final."


def test_gemma4_stream_parser_emits_bare_reasoning_before_channel_end():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    first = parser.feed(state, "Rea")
    second = parser.feed(state, "soning.<channel|>Fi")
    third = parser.feed(state, "nal.")

    assert first == []
    assert second[0].reasoning == "Reasoning."
    assert second[0].content == "Fi"
    assert third[0].reasoning is None
    assert third[0].content == "nal."


def test_gemma4_stream_parser_emits_plain_content_on_finish_without_channel_end():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    assert parser.feed(state, "Plain answer") == []
    outputs = parser.finish(state)

    assert outputs[0].reasoning is None
    assert outputs[0].content == "Plain answer"


def test_gemma4_stream_parser_waits_for_partial_reasoning_marker_after_content():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    first = parser.feed(state, "Testo finale prima.\n\n<|chan")
    second = parser.feed(state, "nel>thought\nReason")
    third = parser.feed(state, "ing interno.<channel|>Altro testo.")

    assert len(first) == 1
    assert first[0].content == "Testo finale prima.\n\n"
    assert first[0].reasoning is None
    assert second[0].content is None
    assert second[0].reasoning == "Reason"
    assert third[0].content == "Altro testo."
    assert third[0].reasoning == "ing interno."


def test_gemma4_stream_parser_waits_for_partial_tool_marker():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    assert parser.feed(state, "<|tool") == []
    emitted = parser.feed(
        state,
        '_call>call:system.test_echo{text:<|"|>scemo chi legge<|"|>}<tool_call|>',
    )

    assert len(emitted) == 1
    assert emitted[0].content is None
    assert emitted[0].tool_calls[0].function_name == "system.test_echo"
    assert emitted[0].tool_calls[0].arguments == '{"text": "scemo chi legge"}'


def test_gemma4_stream_parser_extracts_tool_call_after_reasoning():
    parser = get_output_parser("gemma4")
    state = parser.new_stream_state()

    first = parser.feed(state, "<|channel>thought\nReason.<channel|>")
    assert first[0].reasoning == "Reason."

    second = parser.feed(state, "<|tool_call>call:system.test_echo{text:<|")
    assert second == []
    third = parser.feed(state, '"|>scemo chi legge<|"|>}<tool_call|>')

    assert len(third) == 1
    assert third[0].content is None
    assert third[0].tool_calls[0].function_name == "system.test_echo"
    assert third[0].tool_calls[0].arguments == '{"text": "scemo chi legge"}'


def test_gemma4_parser_extracts_reasoning_and_tool_call():
    parser = get_output_parser("gemma4")

    parsed = parser.parse(
        "<|channel>thought\nNeed tool.<channel|>"
        '<|tool_call>call:system.test_echo{text:<|"|>scemo chi legge<|"|>}<tool_call|>'
    )

    assert parsed.reasoning == "Need tool."
    assert parsed.content is None
    assert parsed.tool_calls[0].function_name == "system.test_echo"


def test_gemma4_parser_extracts_multiple_tool_calls_with_json_quotes():
    parser = get_output_parser("gemma4")

    parsed = parser.parse(
        '<|tool_call>call:chat.show-chart{title:"Messages, by role",labels:["User","Assistant"],data:[4,8],chart_type:"bar"}<tool_call|>'
        '<|tool_call>call:chat.show-collapse{title:"Details",text:"First item, second item"}<tool_call|>'
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 2
    assert parsed.tool_calls[0].function_name == "chat.show-chart"
    assert parsed.tool_calls[0].arguments == (
        '{"title": "Messages, by role", "labels": ["User", "Assistant"], '
        '"data": [4, 8], "chart_type": "bar"}'
    )
    assert parsed.tool_calls[1].function_name == "chat.show-collapse"
    assert parsed.tool_calls[1].arguments == (
        '{"title": "Details", "text": "First item, second item"}'
    )


def test_gemma4_parser_returns_error_tool_call_for_unparseable_tool_payload():
    parser = get_output_parser("gemma4")

    parsed = parser.parse(
        "<|tool_call>call:chat.show-collapse{"
        "title:Dettagli,"
        "text:Primo punto, secondo punto"
        "}<tool_call|>"
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "__democrai_tool_parse_error__"
    assert "gemma4_tool_call_invalid" in parsed.tool_calls[0].arguments
    assert "Primo punto, secondo punto" in parsed.tool_calls[0].arguments
