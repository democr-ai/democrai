from types import SimpleNamespace

import pytest

from democrai.core.application.ai.engine.pipeline.execution import (
    generate_completion_pipeline,
)
from democrai.core.application.ai.engine.schemas.completion import CompletionResponse


@pytest.mark.asyncio
async def test_generate_completion_response_event_uses_content_length(monkeypatch):
    import democrai.core.application.ai.engine.pipeline.execution as execution_mod

    events = []
    async def _emit_event(**kwargs):
        events.append(kwargs)

    monkeypatch.setattr(
        execution_mod,
        "emit_ai_pipeline_event",
        _emit_event,
    )
    await generate_completion_pipeline(
        _Provider("long response text"),
        messages=[],
        options={},
    )

    response_event = [
        event for event in events if event["type"] == "llm.response"
    ][0]
    assert response_event["payload"]["content_length"] == len("long response text")
    assert "content" not in response_event["payload"]


class _Provider:
    engine_id = "test"

    def __init__(self, content: str):
        self.content = content

    async def _invoke_with_usage(self, method, payload, **kwargs):
        return CompletionResponse(id="r1", content=self.content)
