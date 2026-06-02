from __future__ import annotations

import json
import sys
from typing import Any

from democrai.core.application.ai.engine.schemas.completion import CompletionResponse
from democrai.core.application.ai.engine.schemas.completion import Message
from democrai.core.application.ai.engine.schemas.completion import MessageRole
from democrai.core.application.ai.engine.schemas.completion import StreamChunk
from democrai.core.application.ai.engine.schemas.completion import ToolCall
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.application.ai.pipeline_context import emit_ai_pipeline_event
from democrai.core.application.ai.pipeline_context import pipeline_usage_metadata
from democrai.core.application.ai.security.context import guard_tool_result
from democrai.core.application.ai.security.context import tool_result_budget_chars
from democrai.core.application.ai.security.prompt.builder import PromptContextBuilder
from democrai.core.application.ai.security.prompt.messages import (
    normalize_prompt_messages_with_audit,
)
from democrai.core.platform.agents.tool_runtime import agent_tool_runtime
from democrai.core.application.ai.engine.pipeline.tool_aliases import (
    resolve_tool_call_name,
)
from democrai.core.platform.agents.registry import agent_tool_registry
from democrai.core.platform.agents.registry import agent_registry
from democrai.core.runtime.foundation.app import app_ctx


_PARSE_ERROR_TOOL = "__democrai_tool_parse_error__"


def response_tool_calls(response: Any) -> list[ToolCall]:
    if not isinstance(response, CompletionResponse):
        raise TypeError("completion_response_expected")
    return list(response.tool_calls or [])


def assistant_tool_call_message(
    response: CompletionResponse,
    tool_calls: list[ToolCall],
    *,
    tool_responses: list[dict[str, Any]] | None = None,
) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        content=response.content or "",
        tool_calls=tool_calls,
        tool_responses=tool_responses,
    )


async def run_pipeline_tool_call(
    tool_call: ToolCall,
    *,
    iteration: int,
    tool_alias_map: dict[str, str] | None = None,
    options: Any = None,
    config: dict[str, Any] | None = None,
) -> Message:
    context = current_ai_pipeline_context()
    if context is None:
        raise RuntimeError("tool_call_requires_pipeline_context")
    if tool_call.function_name == _PARSE_ERROR_TOOL:
        result = _parse_tool_arguments(tool_call.arguments)
        await emit_ai_pipeline_event(
            type="tool.response",
            name=_PARSE_ERROR_TOOL,
            payload={
                "tool_call_id": tool_call.id,
                "wire_tool": tool_call.function_name,
                "result": result,
                "iteration": iteration,
            },
            status="error",
        )
        return await _tool_output_message(
            result,
            tool_call_id=tool_call.id,
            origin=_PARSE_ERROR_TOOL,
            options=options,
            config=config,
        )
    runtime_tool_name = resolve_tool_call_name(
        tool_call.function_name,
        tool_alias_map,
    )
    tool_title = _tool_title(runtime_tool_name)
    agent_title = _agent_title(runtime_tool_name)
    mcp_name = _mcp_name(runtime_tool_name)
    try:
        arguments = _parse_tool_arguments(tool_call.arguments)
    except Exception as exc:
        app_ctx().logger.error(
            f"[AI Pipeline] CALLED {runtime_tool_name} AT ITERATION {iteration}\n",
            name="TOOL_CALL",
            exc_info=False,
        )

        result = _tool_error_result(exc)
        async with ai_pipeline_step(
            type="tool.call",
            name=runtime_tool_name,
            input={
                "tool": runtime_tool_name,
                "wire_tool": tool_call.function_name,
                "raw_arguments": tool_call.arguments,
            },
            metadata={
                "iteration": iteration,
                "tool_call_id": tool_call.id,
                "wire_tool": tool_call.function_name,
                "tool_title": tool_title,
                "agent_title": agent_title,
                "mcp_name": mcp_name,
            },
        ) as step:
            if isinstance(step, dict):
                step["status"] = "error"
                step["error"] = _tool_result_error(result)
                step["output"] = {"result": result}

        await emit_ai_pipeline_event(
            type="tool.response",
            name=runtime_tool_name,
            payload={
                "tool_call_id": tool_call.id,
                "wire_tool": tool_call.function_name,
                "tool_title": tool_title,
                "agent_title": agent_title,
                "mcp_name": mcp_name,
                "result": result,
                "iteration": iteration,
            },
            status="error",
        )
        return await _tool_output_message(
            result,
            tool_call_id=tool_call.id,
            origin=runtime_tool_name,
            options=options,
            config=config,
        )
    await emit_ai_pipeline_event(
        type="tool.call",
        name=runtime_tool_name,
        payload={
            "tool_call_id": tool_call.id,
            "wire_tool": tool_call.function_name,
            "tool_title": tool_title,
            "agent_title": agent_title,
            "mcp_name": mcp_name,
            "arguments": arguments,
            "iteration": iteration,
        },
    )
    async with ai_pipeline_step(
        type="tool.call",
        name=runtime_tool_name,
        input={
            "tool": runtime_tool_name,
            "wire_tool": tool_call.function_name,
            "tool_title": tool_title,
            "agent_title": agent_title,
            "mcp_name": mcp_name,
            "arguments": arguments,
        },
        metadata={
            "iteration": iteration,
            "tool_call_id": tool_call.id,
            "wire_tool": tool_call.function_name,
            "tool_title": tool_title,
            "agent_title": agent_title,
            "mcp_name": mcp_name,
        },
    ) as step:
        try:
            result = await agent_tool_runtime.run_tool(
                runtime_tool_name,
                arguments=arguments,
                module_name=context.caller_module,
                context={
                    **pipeline_usage_metadata(),
                    "tool_result_budget_chars": tool_result_budget_chars(
                        options=options,
                        config=config,
                    ),
                    "model_registry_id": context.model_registry_id,
                },
            )
            status = _tool_result_status(result)
        except Exception as exc:
            app_ctx().logger.error(
                f"[AI Pipeline] CALLED {runtime_tool_name} AS TOOL WITH FUNCTION {tool_call.function_name} AT ITERATION {iteration} WITH ERROR -> {_tool_error_result(exc)}\n",
                name="TOOL_CALL",
                exc_info=False,
            )

            result = _tool_error_result(exc)
            status = "error"

        if isinstance(step, dict):
            step["output"] = {"result": result}
            if status == "error":
                step["status"] = "error"
                step["error"] = _tool_result_error(result)
    await emit_ai_pipeline_event(
        type="tool.response",
        name=runtime_tool_name,
        payload={
            "tool_call_id": tool_call.id,
            "wire_tool": tool_call.function_name,
            "tool_title": tool_title,
            "agent_title": agent_title,
            "mcp_name": mcp_name,
            "result": result,
            "iteration": iteration,
        },
        status=status,
    )
    return await _tool_output_message(
        result,
        tool_call_id=tool_call.id,
        origin=runtime_tool_name,
        options=options,
        config=config,
    )


def _tool_title(tool_name: str) -> str:
    definition = agent_tool_registry.get(tool_name)
    if definition is None:
        return ""
    return str(definition.title or "").strip()


def _agent_title(tool_name: str) -> str:
    normalized_tool_name = tool_name.strip() if isinstance(tool_name, str) else ""
    agent_name = normalized_tool_name.removeprefix("agent.").strip()
    if agent_name == normalized_tool_name:
        return ""
    definition = agent_registry.get(agent_name)
    if definition is None:
        return ""
    return str(definition.title or definition.name).strip()


def _mcp_name(tool_name: str) -> str:
    parts = tool_name.strip().split(".") if isinstance(tool_name, str) else []
    if len(parts) >= 3 and parts[0] == "mcp":
        return parts[1].strip()
    return ""


async def _tool_output_message(
    result: Any,
    *,
    tool_call_id: str,
    origin: str,
    options: Any = None,
    config: dict[str, Any] | None = None,
) -> Message:
    try:
        guarded_result = await guard_tool_result(
            result,
            origin=origin,
            options=options,
            config=config,
        )
        prompt_builder = PromptContextBuilder()
        messages = await normalize_prompt_messages_with_audit(
            [
                prompt_builder.tool_output(
                    _serialize_tool_result(guarded_result),
                    tool_call_id=tool_call_id,
                    origin=origin,
                )
            ],
            stage="tool_output",
        )
        return messages[0]
    except Exception as exc:
        try:
            app_ctx().logger.error(
                f"[AI Pipeline] SECURITY FAIL {origin}\n",
                name="TOOL_CALL",
                exc_info=sys.exc_info(),
            )
        except Exception:
            pass
        raise


def stream_tool_calls(chunks: list[StreamChunk]) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    current_by_id: dict[str, ToolCall] = {}
    current: ToolCall | None = None
    for chunk in chunks:
        delta = chunk.tool_call_delta
        if delta is None:
            continue

        if delta.id:
            current = current_by_id.get(delta.id)
            if current is None:
                current = ToolCall(
                    id=delta.id,
                    function_name=delta.function_name,
                    arguments="",
                )
                current_by_id[delta.id] = current
                tool_calls.append(current)
        elif current is None or (
            delta.function_name
            and current.function_name
            and delta.function_name != current.function_name
        ):
            current = ToolCall(
                id=f"stream_tool_call_{len(tool_calls)}",
                function_name=delta.function_name,
                arguments="",
            )
            tool_calls.append(current)

        if delta.id:
            current.id = delta.id
        if delta.function_name:
            current.function_name = delta.function_name
        if delta.arguments:
            current.arguments += delta.arguments

    for tool_call in tool_calls:
        if not tool_call.arguments:
            tool_call.arguments = "{}"
    return tool_calls


def assistant_stream_tool_call_message(
    chunks: list[StreamChunk],
    tool_calls: list[ToolCall],
    *,
    tool_responses: list[dict[str, Any]] | None = None,
) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        content="".join(str(chunk.delta or "") for chunk in chunks),
        tool_calls=tool_calls,
        tool_responses=tool_responses,
    )


def tool_response_payload(tool_call: ToolCall, message: Message) -> dict[str, Any]:
    return {
        "name": tool_call.function_name,
        "response": _tool_response_content(message.content),
    }


def _tool_response_content(content: Any) -> Any:
    if isinstance(content, str):
        return _parse_tool_response_text(_unwrap_untrusted_tool_text(content))
    if isinstance(content, list):
        text = "".join(
            str(part.text or "") for part in content if part.type.value == "text"
        )
        return _parse_tool_response_text(_unwrap_untrusted_tool_text(text))
    return content


def _unwrap_untrusted_tool_text(text: str) -> str:
    stripped = str(text or "").strip()
    if not (
        stripped.startswith("<untrusted-content ")
        and stripped.endswith("</untrusted-content>")
    ):
        return stripped
    _, _, body = stripped.partition(">\n")
    if not body:
        return stripped
    return body[: -len("\n</untrusted-content>")]


def _parse_tool_response_text(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        return text


def _parse_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if not isinstance(raw_arguments, str) or not raw_arguments.strip():
        raise ValueError("tool_arguments_json_required")
    parsed = json.loads(raw_arguments)
    if not isinstance(parsed, dict):
        raise ValueError("tool_arguments_object_required")
    return parsed


def _serialize_tool_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    return json.dumps(result, ensure_ascii=True)


def _tool_error_result(exc: Exception) -> dict[str, Any]:
    return {
        "status": "error",
        "error": str(exc),
        "error_type": type(exc).__name__,
    }


def _tool_result_status(result: Any) -> str:
    if (
        isinstance(result, dict)
        and str(result.get("status") or "").strip().lower() == "error"
    ):
        return "error"
    return "ok"


def _tool_result_error(result: Any) -> str:
    if not isinstance(result, dict):
        return "tool_error"
    error = str(result.get("error") or result.get("message") or "").strip()
    error_type = str(result.get("error_type") or "").strip()
    if error and error_type:
        return f"{error_type}: {error}"
    return error or error_type or "tool_error"
