import asyncio
from types import SimpleNamespace

import pytest

import democrai.core.application.ai.pipeline_context as pipeline_context_mod
from democrai.core.application.ai.pipeline_context import ai_pipeline_context
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import create_ai_pipeline_context


class _Logger:
    def __init__(self):
        self.errors = []

    def error(self, message, *_args, **_kwargs):
        self.errors.append(message)


@pytest.mark.asyncio
async def test_ai_pipeline_step_logs_stalled_step(monkeypatch):
    pytest.skip("pipeline step watchdog intentionally disabled")
    logger = _Logger()
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(logger=logger),
    )
    monkeypatch.setattr(
        pipeline_context_mod,
        "_ai_pipeline_step_stall_seconds",
        lambda: 0.01,
    )
    monkeypatch.setattr(pipeline_context_mod, "_record_step", lambda *_args, **_kwargs: None)

    with ai_pipeline_context(create_ai_pipeline_context(root_method="generate_completion")):
        async with ai_pipeline_step(type="engine.call", name="generate_completion"):
            await asyncio.sleep(0.03)

    assert any("error_type=pipeline_step_stalled" in item for item in logger.errors)
    assert any("generator=engine.call:generate_completion" in item for item in logger.errors)


def test_ai_pipeline_step_error_logger_uses_error_class(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(logger=logger),
    )
    context = create_ai_pipeline_context(root_method="generate_completion")

    pipeline_context_mod._log_ai_pipeline_step_error(
        context,
        step_id="step-1",
        type="engine.call",
        name="generate_completion",
        error=RuntimeError("boom"),
        error_message="boom",
    )

    assert len(logger.errors) == 1
    assert "error_type=RuntimeError" in logger.errors[0]
    assert "generator=engine.call:generate_completion" in logger.errors[0]
