from __future__ import annotations

import asyncio
from types import SimpleNamespace

from democrai.core.platform.channels.models import Message as ChannelMessage
from democrai.core.platform.pipeline.hooks import resolve_pipeline_hook
from democrai.core.platform.pipeline.models import PipelineContext
from democrai.core.platform.pipeline.registry import pipeline_hook_registry


def test_resolve_pipeline_hook_merge_strategies_and_failure_path(monkeypatch):
    saved_hooks = dict(pipeline_hook_registry._hooks)  # pylint: disable=protected-access
    saved_order = pipeline_hook_registry._order  # pylint: disable=protected-access
    pipeline_hook_registry._hooks = {}  # pylint: disable=protected-access
    pipeline_hook_registry._order = 0  # pylint: disable=protected-access

    errors = []
    monkeypatch.setattr(
        "democrai.core.platform.pipeline.hooks.app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(error=lambda msg: errors.append(msg))),
    )

    async def _good(_ctx):
        return ["x"]

    async def _bad(_ctx):
        raise RuntimeError("boom")

    async def _replace(_ctx):
        return "y"

    async def _chain(ctx):
        return f"{ctx.response_text}-z"

    async def _none(_ctx):
        return None

    async def _pre_llm_chain(_ctx):
        return "extra-prompt"

    async def _memory_chain(_ctx):
        return {"tag": "v"}

    pipeline_hook_registry.register("h.acc", _good, module_name="demo")
    pipeline_hook_registry.register("", _good, module_name="demo")
    pipeline_hook_registry.register("h.acc", _bad, module_name="demo")
    pipeline_hook_registry.register("h.acc", _none, module_name="demo")
    pipeline_hook_registry.register("h.rep", _replace, module_name="demo")
    pipeline_hook_registry.register("chat.post_response", _chain, module_name="demo")
    pipeline_hook_registry.register("chat.pre_llm", _pre_llm_chain, module_name="demo")
    pipeline_hook_registry.register("chat.on_memory_write", _memory_chain, module_name="demo")

    ctx = PipelineContext(message=ChannelMessage(text="a"), session={}, thread_id="t")
    ctx.response_text = "base"
    try:
        acc = asyncio.run(resolve_pipeline_hook("h.acc", ctx, merge_strategy="accumulate"))
        rep = asyncio.run(resolve_pipeline_hook("h.rep", ctx, merge_strategy="replace"))
        chain = asyncio.run(resolve_pipeline_hook("chat.post_response", ctx, merge_strategy="chain"))
        asyncio.run(resolve_pipeline_hook("chat.pre_llm", ctx, merge_strategy="chain"))
        asyncio.run(resolve_pipeline_hook("chat.on_memory_write", ctx, merge_strategy="chain"))
    finally:
        pipeline_hook_registry._hooks = saved_hooks  # pylint: disable=protected-access
        pipeline_hook_registry._order = saved_order  # pylint: disable=protected-access

    assert acc == ["x"]
    assert rep == "y"
    assert chain == "base-z"
    assert "extra-prompt" in ctx.extra_system_prompts
    assert ctx.metadata["memory_chunk"] == {"tag": "v"}
    assert errors and "failed" in errors[0]
