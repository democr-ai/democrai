from democrai.core.application.ai.output_parsers.registry import get_output_parser


def test_llama31_parser_extracts_raw_json_tool_call():
    parser = get_output_parser("llama31")

    parsed = parser.parse(
        '{"name": "system_test-echo_b352998447", '
        '"parameters": {"text": "Usa il tool di test"}}'
    )

    assert parsed.content is None
    assert len(parsed.tool_calls) == 1
    assert parsed.tool_calls[0].function_name == "system_test-echo_b352998447"
    assert parsed.tool_calls[0].arguments == '{"text": "Usa il tool di test"}'


def test_llama31_parser_leaves_non_tool_json_as_content():
    parser = get_output_parser("llama31")

    parsed = parser.parse('{"message": "ok"}')

    assert parsed.content == '{"message": "ok"}'
    assert parsed.tool_calls == []


def test_llama31_stream_parser_buffers_until_json_tool_call_is_complete():
    parser = get_output_parser("llama31")
    state = parser.new_stream_state()

    assert parser.feed(state, '{"name": "system_test') == []
    emitted = parser.feed(
        state,
        '-echo_b352998447", "parameters": {"text": "Usa il tool di test"}}',
    )

    assert len(emitted) == 1
    assert emitted[0].content is None
    assert emitted[0].tool_calls[0].function_name == "system_test-echo_b352998447"
    assert emitted[0].tool_calls[0].arguments == '{"text": "Usa il tool di test"}'
