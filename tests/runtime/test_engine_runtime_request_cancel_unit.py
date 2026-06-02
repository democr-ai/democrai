import asyncio

import pytest

import democrai.core.application.ai.engine.runtime.provider as provider_mod
import democrai.core.application.ai.pipeline_context as pipeline_context_mod
from democrai.core.application.ai.engine.runtime.provider import EngineRuntimeProvider
from democrai.core.application.ai.engine.runtime.requests import cancel_runtime_request
from democrai.core.runtime.foundation.app import app_ctx


@pytest.mark.asyncio
async def test_generate_completion_background_request_can_be_cancelled(monkeypatch):
    app_ctx().logger = type(
        "Logger",
        (),
        {
            "debug": staticmethod(lambda *_args, **_kwargs: None),
            "info": staticmethod(lambda *_args, **_kwargs: None),
            "warning": staticmethod(lambda *_args, **_kwargs: None),
            "error": staticmethod(lambda *_args, **_kwargs: None),
        },
    )()
    started = asyncio.Event()
    messages = []
    errors = []
    cancelled = []

    async def _pipeline(*args, **kwargs):
        started.set()
        await asyncio.sleep(60)

    monkeypatch.setattr(provider_mod, "generate_completion_pipeline", _pipeline)
    monkeypatch.setattr(pipeline_context_mod, "_record_step", lambda *args, **kwargs: None)

    provider = EngineRuntimeProvider(
        engine_row_id=1,
        model_registry_id=2,
        engine_id="test",
        config={"model": "test-model"},
    )
    monkeypatch.setattr(provider, "_cancel_request", lambda request_id: cancelled.append(request_id))

    response = await provider.generate_completion(
        messages=[],
        options={},
        on_response=lambda value: None,
        on_error=lambda exc: errors.append(exc),
        on_message=lambda message: messages.append(message),
    )

    await asyncio.wait_for(started.wait(), timeout=1)
    assert cancel_runtime_request(response.request_id)
    assert cancelled == [response.request_id]

    for _ in range(20):
        if not cancel_runtime_request(response.request_id):
            break
        await asyncio.sleep(0.01)

    assert not cancel_runtime_request(response.request_id)
    assert errors == []
    assert any(message.type == "request.cancelled" for message in messages)
