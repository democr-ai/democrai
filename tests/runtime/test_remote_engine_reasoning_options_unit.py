import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.schemas.completion import (
    CompletionOptions,
    Message,
)
from engines.anthropic.engine import AnthropicEngine
from engines.gemini.engine import GeminiEngine
from engines.openai.engine import OpenAIEngine
from engines.openai_compatible.engine import OpenAICompatibleEngine
import modules.system.ui.engine.model.test_params as test_params_mod


def _engine_model_detail_view_module():
    path = (
        Path(__file__).resolve().parents[2]
        / "modules/system/ui/engine/model/[id]/view.py"
    )
    spec = importlib.util.spec_from_file_location("engine_model_detail_view", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_openai_reasoning_uses_responses_reasoning_object():
    engine = OpenAIEngine.__new__(OpenAIEngine)

    payload = engine._request_extra(
        {
            "reasoning": True,
            "reasoning_budget": 4096,
        }
    )

    assert payload == {"reasoning": {"effort": "medium"}}


def test_openai_ignores_compatible_reasoning_param_name():
    engine = OpenAIEngine.__new__(OpenAIEngine)

    payload = engine._request_extra(
        {
            "reasoning": "high",
            "reasoning_param_name": "reasoning_effort",
        }
    )

    assert payload == {"reasoning": {"effort": "high"}}


def test_openai_compatible_reasoning_uses_configured_key():
    engine = OpenAICompatibleEngine.__new__(OpenAICompatibleEngine)

    payload = engine._request_extra(
        {
            "reasoning": "medium",
            "reasoning_param_name": "reasoning_effort",
            "reasoning_budget": 4096,
        }
    )

    assert payload == {"reasoning_effort": "medium"}


def test_openai_compatible_request_parameter_mapping_renames_and_drops_keys():
    engine = OpenAICompatibleEngine.__new__(OpenAICompatibleEngine)
    engine.config = {
        "request_parameter_mapping": [
            "max_tokens=max_completion_tokens",
            "temperature=",
            "top_p=",
            "reasoning=reasoning_effort",
        ]
    }

    payload = engine._apply_request_parameter_mapping(
        {
            "model": "gpt",
            "max_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9,
            "reasoning": "medium",
        }
    )

    assert payload == {
        "model": "gpt",
        "max_completion_tokens": 100,
        "reasoning_effort": "medium",
    }


def test_engine_model_test_options_include_saved_reasoning_param_name():
    view = _engine_model_detail_view_module()

    options = view._completion_options(
        {
            "generation": {
                "temperature": 0.4,
                "extra": {
                    "reasoning": "medium",
                    "reasoning_param_name": "reasoning_effort",
                },
            }
        },
        {},
    )

    assert options["temperature"] == 0.4
    assert options["extra.reasoning"] == "medium"
    assert options["extra.reasoning_param_name"] == "reasoning_effort"
    assert "extra" not in options


def test_openai_compatible_completion_extracts_reasoning_content():
    engine = OpenAICompatibleEngine.__new__(OpenAICompatibleEngine)
    message = SimpleNamespace(
        content="final answer",
        reasoning_content="internal reasoning",
    )

    assert engine._extract_reasoning(message) == "internal reasoning"


def test_anthropic_reasoning_budget_builds_thinking_payload():
    engine = AnthropicEngine.__new__(AnthropicEngine)
    engine.model_name = "claude"

    payload = engine._build_request_payload(
        [Message(role="user", content="hello")],
        CompletionOptions(
            max_tokens=128,
            extra={"reasoning": True, "reasoning_budget": 4096},
        ),
    )

    assert payload["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert payload["max_tokens"] == 5120
    assert "reasoning" not in payload
    assert "reasoning_budget" not in payload


def test_anthropic_completion_extracts_thinking_block():
    engine = AnthropicEngine.__new__(AnthropicEngine)
    response = SimpleNamespace(
        id="msg-1",
        content=[
            SimpleNamespace(type="thinking", thinking="internal reasoning"),
            SimpleNamespace(type="text", text="final answer"),
        ],
        usage=SimpleNamespace(input_tokens=3, output_tokens=4),
        stop_reason="end_turn",
    )

    assert engine._extract_text(response) == "final answer"
    assert engine._extract_reasoning(response) == "internal reasoning"


def test_gemini_reasoning_budget_builds_thinking_config():
    engine = GeminiEngine.__new__(GeminiEngine)
    engine.model_name = "gemini"
    engine._types = SimpleNamespace(
        GenerateContentConfig=lambda **kwargs: kwargs,
        ThinkingConfig=lambda **kwargs: {"thinking_config_payload": kwargs},
    )

    payload = engine._build_request_payload(
        [Message(role="user", content="hello")],
        CompletionOptions(extra={"reasoning": "medium", "reasoning_budget": 2048}),
    )

    assert payload["config"]["thinking_config"] == {
        "thinking_config_payload": {
            "thinking_budget": 2048,
            "include_thoughts": True,
        }
    }
    assert "reasoning" not in payload["config"]
    assert "reasoning_budget" not in payload["config"]


def test_gemini_extracts_reasoning_parts():
    engine = GeminiEngine.__new__(GeminiEngine)
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(thinking="internal "),
                        {"reasoning": "reasoning"},
                    ]
                )
            )
        ]
    )

    assert engine._extract_reasoning(response) == "internal reasoning"


def test_gemini_extracts_thought_summary_text_as_reasoning():
    engine = GeminiEngine.__new__(GeminiEngine)
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="summary", thought=True),
                        SimpleNamespace(text="answer", thought=False),
                    ]
                )
            )
        ]
    )

    assert engine._extract_reasoning(response) == "summary"
    assert engine._extract_text(response) == "answer"


def test_gemini_extracts_stream_chunk_direct_parts_thought_summary():
    engine = GeminiEngine.__new__(GeminiEngine)
    chunk = SimpleNamespace(
        parts=[
            SimpleNamespace(text="stream summary", thought=True),
            SimpleNamespace(text="stream answer", thought=False),
        ]
    )

    assert engine._extract_reasoning(chunk) == "stream summary"
    assert engine._extract_text(chunk) == "stream answer"


def test_gemini_extracts_stream_chunk_candidate_parts_thought_summary():
    engine = GeminiEngine.__new__(GeminiEngine)
    chunk = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                parts=[
                    SimpleNamespace(text="candidate summary", thought=True),
                    SimpleNamespace(text="candidate answer", thought=False),
                ]
            )
        ]
    )

    assert engine._extract_reasoning(chunk) == "candidate summary"
    assert engine._extract_text(chunk) == "candidate answer"


@pytest.mark.asyncio
async def test_gemini_stream_emits_tool_call_delta():
    engine = GeminiEngine.__new__(GeminiEngine)
    engine.model_name = "gemini"
    engine._types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    engine.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content_stream=lambda **kwargs: [
                SimpleNamespace(
                    candidates=[
                        SimpleNamespace(
                            content=SimpleNamespace(
                                parts=[
                                    SimpleNamespace(
                                        function_call=SimpleNamespace(
                                            name="lookup",
                                            args={"q": "demo"},
                                        )
                                    )
                                ]
                            )
                        )
                    ]
                )
            ]
        )
    )

    chunks = [
        chunk
        async for chunk in engine._generate_stream(
            [Message(role="user", content="hello")],
            CompletionOptions(),
        )
    ]

    tool_calls = [chunk.tool_call_delta for chunk in chunks if chunk.tool_call_delta]
    assert len(tool_calls) == 1
    assert tool_calls[0].function_name == "lookup"
    assert tool_calls[0].arguments == '{"q": "demo"}'


@pytest.mark.asyncio
async def test_gemini_stream_deduplicates_repeated_complete_tool_call_chunks():
    engine = GeminiEngine.__new__(GeminiEngine)
    engine.model_name = "gemini"
    engine._types = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    chunk = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            function_call=SimpleNamespace(
                                name="lookup",
                                args={"q": "demo"},
                            )
                        )
                    ]
                )
            )
        ]
    )
    engine.client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content_stream=lambda **kwargs: [chunk, chunk]
        )
    )

    chunks = [
        item
        async for item in engine._generate_stream(
            [Message(role="user", content="hello")],
            CompletionOptions(),
        )
    ]

    tool_calls = [item.tool_call_delta for item in chunks if item.tool_call_delta]
    assert len(tool_calls) == 1
    assert tool_calls[0].arguments == '{"q": "demo"}'


def test_gemini_formats_tool_response_text_without_json_parsing_error():
    engine = GeminiEngine.__new__(GeminiEngine)

    message = engine._format_message(
        Message(
            role="tool",
            tool_call_id="lookup",
            content="plain tool result",
        )
    )

    assert message == {
        "role": "user",
        "parts": [
            {
                "function_response": {
                    "name": "lookup",
                    "response": {"result": "plain tool result"},
                }
            }
        ],
    }


def test_gemini_formats_tool_response_json_object():
    engine = GeminiEngine.__new__(GeminiEngine)

    message = engine._format_message(
        Message(
            role="tool",
            tool_call_id="lookup",
            content='{"value": 1}',
        )
    )

    assert message["parts"][0]["function_response"]["response"] == {"value": 1}


def test_gemini_preserves_thought_signature_on_function_call_history():
    engine = GeminiEngine.__new__(GeminiEngine)
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            thought_signature="sig-a",
                            function_call=SimpleNamespace(
                                name="lookup",
                                args={"q": "demo"},
                            ),
                        )
                    ]
                )
            )
        ]
    )

    tool_call = engine._extract_tool_calls(response)[0]
    message = engine._format_message(
        Message(
            role="assistant",
            tool_calls=[tool_call],
        )
    )

    assert message["parts"][0] == {
        "function_call": {
            "name": "lookup",
            "args": {"q": "demo"},
        },
        "thought_signature": "sig-a",
    }


def test_gemini_tool_response_name_uses_original_function_name_from_signed_call():
    engine = GeminiEngine.__new__(GeminiEngine)
    response = SimpleNamespace(
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(
                            thought_signature="sig-a",
                            function_call=SimpleNamespace(
                                name="lookup",
                                args={},
                            ),
                        )
                    ]
                )
            )
        ]
    )
    tool_call = engine._extract_tool_calls(response)[0]

    message = engine._format_message(
        Message(
            role="tool",
            tool_call_id=tool_call.id,
            content="done",
        )
    )

    assert message["parts"][0]["function_response"]["name"] == "lookup"


def test_reasoning_option_fields_are_added_from_provider_manifest():
    fields = test_params_mod._reasoning_option_fields(
        {
            "capability_option_fields": {
                "reasoning": [
                    {
                        "name": "reasoning_budget",
                        "label": "Reasoning budget",
                        "type": "number",
                        "default": 4096,
                    }
                ]
            }
        },
        {"extra": {"reasoning_budget": 2048}},
    )

    assert fields == [
        {
            "name": "extra.reasoning_budget",
            "label": "Reasoning budget",
            "type": "number",
            "default": 4096,
            "value": 2048,
        }
    ]
