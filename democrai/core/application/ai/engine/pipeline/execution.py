from __future__ import annotations

from typing import Any

from democrai.core.application.ai.engine.pipeline.messages import (
    materialized_pipeline_messages,
)
from democrai.core.application.ai.engine.pipeline.messages import (
    messages_with_selected_skills,
)
from democrai.core.application.ai.engine.pipeline.options import (
    iteration_pipeline_options,
)
from democrai.core.application.ai.engine.pipeline.options import (
    prepare_pipeline_options,
)
from democrai.core.application.ai.engine.pipeline.options import tool_max_iterations
from democrai.core.application.ai.engine.pipeline.tool_aliases import (
    TOOL_ALIAS_MAP_OPTION,
)
from democrai.core.application.ai.engine.pipeline.tool_calls import (
    assistant_stream_tool_call_message,
)
from democrai.core.application.ai.engine.pipeline.tool_calls import (
    assistant_tool_call_message,
)
from democrai.core.application.ai.engine.pipeline.tool_calls import response_tool_calls
from democrai.core.application.ai.engine.pipeline.tool_calls import (
    run_pipeline_tool_call,
)
from democrai.core.application.ai.engine.pipeline.tool_calls import stream_tool_calls
from democrai.core.application.ai.engine.pipeline.tool_calls import tool_response_payload
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import emit_ai_pipeline_event
from democrai.core.application.ai.pipeline_context import mark_step_progress
from democrai.core.application.ai.security.context import guard_prompt_messages


async def generate_completion_pipeline(provider: Any, messages=None, options=None):
    base_messages = await messages_with_selected_skills(
        list(messages or []),
        options,
    )
    async with materialized_pipeline_messages(
        base_messages,
        engine_id=provider.engine_id,
    ) as resolved_messages:
        resolved_options = await prepare_pipeline_options(options)
        tool_alias_map = _tool_alias_map(resolved_options)
        max_iterations = tool_max_iterations(resolved_options)
        response = None
        for iteration in range(max_iterations + 1):
            iteration_options = iteration_pipeline_options(
                resolved_options,
                iteration=iteration,
            )
            await emit_ai_pipeline_event(
                type="llm.request",
                name="generate_completion",
                payload={
                    "iteration": iteration + 1,
                    "messages": len(resolved_messages),
                },
            )
            guarded_messages = await guard_prompt_messages(
                resolved_messages,
                options=iteration_options,
                config=getattr(provider, "config", None),
                stage="generate_completion",
            )
            response = await provider._invoke_with_usage(
                "generate_completion",
                {"messages": guarded_messages, "options": iteration_options},
                metadata={"iteration": iteration + 1},
            )
            diagnostic_raw = getattr(response, "diagnostic_raw", None)
            if isinstance(diagnostic_raw, dict):
                await emit_ai_pipeline_event(
                    type="llm.iteration_diagnostic_raw",
                    name="generate_completion",
                    payload={
                        "iteration": iteration + 1,
                        "diagnostic_raw": diagnostic_raw,
                    },
                )
            await emit_ai_pipeline_event(
                type="llm.response",
                name="generate_completion",
                payload={
                    "iteration": iteration + 1,
                    "content_length": len(response.content or ""),
                    "tool_calls": len(response_tool_calls(response)),
                },
            )
            tool_calls = response_tool_calls(response)
            if not tool_calls:
                return response
            if iteration >= max_iterations:
                raise RuntimeError("tool_call_max_iterations_exceeded")
            await emit_ai_pipeline_event(
                type="tool.detected",
                name="generate_completion",
                payload={
                    "iteration": iteration + 1,
                    "tools": [tool_call.function_name for tool_call in tool_calls],
                },
            )
            tool_messages = []
            tool_responses = []
            for tool_call in tool_calls:
                tool_message = await run_pipeline_tool_call(
                    tool_call,
                    iteration=iteration + 1,
                    tool_alias_map=tool_alias_map,
                    options=iteration_options,
                    config=getattr(provider, "config", None),
                )
                tool_messages.append(tool_message)
                tool_responses.append(tool_response_payload(tool_call, tool_message))
            resolved_messages.append(
                assistant_tool_call_message(
                    response,
                    tool_calls,
                    tool_responses=tool_responses,
                )
            )
            resolved_messages.extend(tool_messages)
        return response


async def generate_stream_pipeline(provider: Any, messages=None, options=None):
    base_messages = await messages_with_selected_skills(
        list(messages or []),
        options,
    )
    async with materialized_pipeline_messages(
        base_messages,
        engine_id=provider.engine_id,
    ) as resolved_messages:
        resolved_options = await prepare_pipeline_options(options)
        tool_alias_map = _tool_alias_map(resolved_options)
        max_iterations = tool_max_iterations(resolved_options)
        for iteration in range(max_iterations + 1):
            iteration_options = iteration_pipeline_options(
                resolved_options,
                iteration=iteration,
            )
            await emit_ai_pipeline_event(
                type="llm.request",
                name="generate_stream",
                payload={
                    "iteration": iteration + 1,
                    "messages": len(resolved_messages),
                },
            )
            chunks: list[Any] = []
            async with ai_pipeline_step(
                type="stream",
                name="generate_stream",
                input={"iteration": iteration + 1},
            ) as stream_step:
                guarded_messages = await guard_prompt_messages(
                    resolved_messages,
                    options=iteration_options,
                    config=getattr(provider, "config", None),
                    stage="generate_stream",
                )
                async for item in provider._invoke_stream_with_usage(
                    "generate_stream",
                    {"messages": guarded_messages, "options": iteration_options},
                    metadata={"iteration": iteration + 1},
                    metadata_from_result=lambda result: {
                        "chunks": len(result) if isinstance(result, list) else None
                    },
                ):
                    if item is None:
                        continue
                    if isinstance(getattr(item, "stats", None), dict):
                        yield item
                        continue
                    chunks.append(item)
                    mark_step_progress(stream_step, chunks=len(chunks))
                    yield item
                if isinstance(stream_step, dict):
                    stream_step["output"] = {"chunks": len(chunks)}
            await emit_ai_pipeline_event(
                type="llm.response",
                name="generate_stream",
                payload={
                    "iteration": iteration + 1,
                    "chunks": len(chunks),
                },
            )
            tool_calls = stream_tool_calls(chunks)
            if isinstance(stream_step, dict):
                stream_step["stats"] = {"tool_calls": len(tool_calls)}
            if not tool_calls:
                return
            if iteration >= max_iterations:
                raise RuntimeError("tool_call_max_iterations_exceeded")
            await emit_ai_pipeline_event(
                type="tool.detected",
                name="generate_stream",
                payload={
                    "iteration": iteration + 1,
                    "tools": [tool_call.function_name for tool_call in tool_calls],
                },
            )
            tool_messages = []
            tool_responses = []
            for tool_call in tool_calls:
                tool_message = await run_pipeline_tool_call(
                    tool_call,
                    iteration=iteration + 1,
                    tool_alias_map=tool_alias_map,
                    options=iteration_options,
                    config=getattr(provider, "config", None),
                )
                tool_messages.append(tool_message)
                tool_responses.append(tool_response_payload(tool_call, tool_message))
            resolved_messages.append(
                assistant_stream_tool_call_message(
                    chunks,
                    tool_calls,
                    tool_responses=tool_responses,
                )
            )
            resolved_messages.extend(tool_messages)


def _tool_alias_map(options: Any) -> dict[str, str]:
    if not isinstance(options, dict):
        return {}
    raw = options.get(TOOL_ALIAS_MAP_OPTION)
    if not isinstance(raw, dict):
        return {}
    return {
        str(wire_name): str(runtime_name)
        for wire_name, runtime_name in raw.items()
        if str(wire_name or "").strip() and str(runtime_name or "").strip()
    }
