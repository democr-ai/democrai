from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.pipeline.execution import (
    generate_stream_pipeline,
)
from democrai.core.application.ai.engine.pipeline.tool_calls import stream_tool_calls
from democrai.core.application.ai.engine.schemas.completion import StreamChunk
from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.pipeline_context import ai_pipeline_context
from democrai.core.application.ai.pipeline_context import create_ai_pipeline_context
from democrai.core.runtime.foundation.app import app_ctx


@pytest.mark.asyncio
async def test_generate_stream_pipeline_records_one_stream_step_for_many_chunks(monkeypatch):
    import democrai.core.application.ai.pipeline_context as pipeline_context_mod

    app_ctx().logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )
    recorded_steps = []
    monkeypatch.setattr(
        pipeline_context_mod,
        "_record_step",
        lambda context, **kwargs: recorded_steps.append(kwargs),
    )
    provider = _Provider(
        [
            StreamChunk(id="1", delta="a"),
            StreamChunk(id="1", delta="b"),
            StreamChunk(id="1", delta="c"),
        ]
    )

    with ai_pipeline_context(create_ai_pipeline_context(root_method="generate_stream")):
        chunks = [
            chunk
            async for chunk in generate_stream_pipeline(
                provider,
                messages=[],
                options={},
            )
        ]

    assert [chunk.delta for chunk in chunks] == ["a", "b", "c"]
    stream_steps = [step for step in recorded_steps if step["type"] == "stream"]
    chunk_steps = [step for step in recorded_steps if step["type"] == "stream.chunk"]
    assert len(stream_steps) == 1
    assert chunk_steps == []
    assert stream_steps[0]["output"] == {"chunks": 3}


def test_stream_tool_calls_preserves_multiple_tool_calls_in_one_stream():
    tool_calls = stream_tool_calls(
        [
            StreamChunk(
                id="1",
                tool_call_delta=ToolCall(
                    id="call-1",
                    function_name="first",
                    arguments='{"a":',
                ),
            ),
            StreamChunk(
                id="1",
                tool_call_delta=ToolCall(
                    id="call-1",
                    function_name="",
                    arguments="1}",
                ),
            ),
            StreamChunk(
                id="1",
                tool_call_delta=ToolCall(
                    id="call-2",
                    function_name="second",
                    arguments='{"b":2}',
                ),
            ),
        ]
    )

    assert [tool.function_name for tool in tool_calls] == ["first", "second"]
    assert [tool.arguments for tool in tool_calls] == ['{"a":1}', '{"b":2}']


class _Provider:
    engine_id = "test"

    def __init__(self, chunks):
        self.chunks = list(chunks)

    async def _invoke_stream_with_usage(self, method, payload, **kwargs):
        for chunk in self.chunks:
            yield chunk
