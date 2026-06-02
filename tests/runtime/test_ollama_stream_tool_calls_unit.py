from __future__ import annotations

from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.pipeline.tool_calls import stream_tool_calls
from democrai.core.application.ai.engine.schemas.completion import CompletionOptions
from engines.ollama.engine import OllamaEngine


class _FakeOllamaStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._chunks:
            raise StopAsyncIteration
        return self._chunks.pop(0)


class _FakeOllamaClient:
    def __init__(self, chunks):
        self._chunks = chunks

    async def chat(self, **_payload):
        return _FakeOllamaStream(self._chunks)


class _FakeOllamaChunk(dict):
    @property
    def message(self):
        return SimpleNamespace(
            tool_calls=self.get("message", {}).get("tool_calls") or []
        )


@pytest.mark.asyncio
async def test_ollama_stream_tool_arguments_emit_deltas_for_cumulative_chunks():
    engine = OllamaEngine.__new__(OllamaEngine)
    engine.model_name = "gemma4:26b"
    engine.config = {}
    engine.base_url = "http://ollama.test"
    engine._build_client = lambda: _FakeOllamaClient(
        [
            _FakeOllamaChunk({
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "chat.show-table",
                                "arguments": {"columns": [{"key": "name"}]},
                            }
                        }
                    ],
                },
                "done": False,
            }),
            _FakeOllamaChunk({
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "chat.show-table",
                                "arguments": {
                                    "columns": [{"key": "name"}],
                                    "rows": [{"name": "Ada"}],
                                },
                            }
                        }
                    ],
                },
                "done": False,
            }),
        ]
    )

    chunks = [
        chunk
        async for chunk in engine._generate_stream([], CompletionOptions())
    ]
    tool_calls = stream_tool_calls(chunks)

    assert len(tool_calls) == 1
    assert tool_calls[0].function_name == "chat.show-table"
    assert tool_calls[0].arguments == (
        '{"columns": [{"key": "name"}], "rows": [{"name": "Ada"}]}'
    )
    assert engine._tool_arguments_for_prompt(tool_calls[0].arguments) == {
        "columns": [{"key": "name"}],
        "rows": [{"name": "Ada"}],
    }
