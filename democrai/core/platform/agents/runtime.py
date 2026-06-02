from __future__ import annotations

import asyncio
import inspect
import sys
from string import Formatter
from typing import Any

from democrai.core.application.ai.engine.base.llm import ai_call_context
from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.application.ai.pipeline_context import emit_ai_pipeline_event
from democrai.core.platform.agents.models import AgentDefinition
from democrai.core.platform.agents.models import AgentRunResult
from democrai.core.platform.agents.execution_context import AgentExecutionContext
from democrai.core.platform.agents.execution_context import current_agent_execution
from democrai.core.platform.agents.execution_context import emit_agent_listener_event
from democrai.core.platform.agents.registry import agent_registry
from democrai.core.platform.agents.registry import agent_tool_registry
from democrai.core.platform.agents.registry import pipeline_registry
from democrai.core.platform.agents.skills import SkillLoader
from democrai.core.platform.agents.tool_runtime import agent_tool_runtime
from democrai.core.platform.agents.model_resolution import resolve_agent_provider
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import AgentModelConfig
from democrai.core.application.ai.security.prompt.builder import PromptContextBuilder
from democrai.core.application.ai.security.prompt.messages import (
    normalize_prompt_messages_with_audit,
)


def _runtime_guard(definition, *, subject_kind: str):
    subject = definition.name.strip() if isinstance(definition.name, str) else ""
    if not subject:
        raise RuntimeError(f"agent_runtime_subject_missing:{subject_kind}")
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

    return process_guard_context(
        subject=subject,
        subject_kind=subject_kind,
        access=definition.access,
    )


class AgentRuntime:
    def __init__(self, *, skill_loader: SkillLoader | None = None) -> None:
        self.skill_loader = skill_loader or SkillLoader()
        self.agent_registry = agent_registry
        self.agent_tool_registry = agent_tool_registry
        self.agent_tool_runtime = agent_tool_runtime
        self.pipeline_registry = pipeline_registry

    async def run_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        return await self.agent_tool_runtime.run_tool(
            name,
            arguments=arguments,
            context=context,
        )

    async def run_agent(
        self,
        name: str,
        *,
        input: str = "",
        context: dict[str, Any] | None = None,
        provider: Any = None,
        provider_override: Any = None,
        extra_tools: list[str] | tuple[str, ...] | None = None,
        extra_skills: list[str] | tuple[str, ...] | None = None,
        extra_mcp_servers: list[str] | tuple[str, ...] | None = None,
        extra_agents: list[str] | tuple[str, ...] | None = None,
        max_iterations: int | None = None,
        listener: Any = None,
        on_message: Any = None,
    ) -> AgentRunResult:
        definition = self.agent_registry.get(name)
        if definition is None:
            raise ValueError(f"Unknown agent: {name}")

        listener_context = {} if context is None else context
        configured = _agent_runtime_config(definition.name)
        available_skill_names = _merge_names(
            _merge_names(definition.skills, configured["extra_skills"]),
            extra_skills,
        )
        tool_names = _merge_names(
            _merge_names(definition.tools, configured["extra_tools"]),
            extra_tools,
        )
        completion_tool_names = tuple(
            tool_name for tool_name in tool_names if not tool_name.startswith("agent.")
        )
        mcp_server_names = _merge_names(
            _merge_names(definition.mcp_servers, configured["extra_mcp_servers"]),
            extra_mcp_servers,
        )
        agent_names = _normalize_agent_names(
            [
                *(
                    tool_name
                    for tool_name in tool_names
                    if tool_name.startswith("agent.")
                ),
                *configured["extra_agents"],
                *(list(extra_agents) if extra_agents is not None else []),
            ]
        )
        context_tool_names = _merge_names(
            completion_tool_names,
            tuple(f"agent.{agent_name}" for agent_name in agent_names),
        )
        iterations = (
            int(max_iterations)
            if max_iterations is not None
            else int(configured["max_iterations"] or definition.max_iterations)
        )
        parent_execution = current_agent_execution.get()
        effective_listener = (
            listener
            if listener is not None
            else (parent_execution.listener if parent_execution is not None else None)
        )
        token = current_agent_execution.set(
            AgentExecutionContext(
                agent_name=definition.name,
                objective=definition.objective,
                tool_names=context_tool_names,
                skill_names=available_skill_names,
                mcp_servers=mcp_server_names,
                listener=effective_listener,
            )
        )
        await emit_agent_listener_event(
            "agent.run.started",
            input=input,
            context=listener_context,
        )
        try:
            try:
                with _runtime_guard(definition, subject_kind="agent"):
                    if definition.handler is not None:
                        handler_result = await _invoke_callable(
                            definition.handler,
                            payload={"input": input},
                            extra_context={
                                "agent": definition,
                                "context": listener_context,
                            },
                        )
                        normalized = _normalize_agent_run_result(
                            definition,
                            handler_result,
                        )
                        await emit_agent_listener_event(
                            "agent.run.finished",
                            input=input,
                            context=listener_context,
                            result=normalized,
                            content=normalized.content,
                            tool_results=list(normalized.tool_results),
                        )
                        return normalized

                    try:
                        resolved_provider = (
                            provider_override
                            if provider_override is not None
                            else await resolve_agent_provider(definition, provider)
                        )
                        prompt_builder = PromptContextBuilder()
                        messages = await normalize_prompt_messages_with_audit(
                            [
                                prompt_builder.trusted_instruction(
                                    definition.system_prompt or definition.description,
                                    origin=definition.name,
                                ),
                                prompt_builder.user_input(
                                    input, origin=definition.name
                                ),
                            ],
                            stage="agent_runtime",
                        )
                        options = {
                            "tools": list(completion_tool_names),
                            "skills": list(available_skill_names),
                            "mcp": list(mcp_server_names),
                            "agents": list(agent_names),
                            "tool_max_iterations": iterations,
                        }
                        await emit_agent_listener_event(
                            "agent.completion.started",
                            messages=messages,
                            options=options,
                        )
                        await emit_ai_pipeline_event(
                            type="agent.pipeline.started",
                            name=definition.name,
                            payload={
                                "agent_title": definition.title or definition.name,
                                "input": input,
                            },
                        )
                        with ai_call_context(
                            objective=definition.objective,
                            request_kind="agent_completion",
                            agent_id=definition.name,
                        ):
                            effective_on_message = on_message
                            if effective_on_message is None:
                                pipeline_context = current_ai_pipeline_context()
                                effective_on_message = (
                                    None
                                    if pipeline_context is None
                                    else pipeline_context.on_message
                                )
                            if effective_on_message is None:
                                response = await resolved_provider.generate_completion(
                                    messages,
                                    options,
                                )
                            else:
                                response = await resolved_provider.generate_completion(
                                    messages,
                                    options,
                                    on_message=effective_on_message,
                                )
                        await emit_ai_pipeline_event(
                            type="agent.pipeline.finished",
                            name=definition.name,
                            payload={
                                "agent_title": definition.title or definition.name,
                                "response_id": response.id,
                            },
                            status="ok",
                        )
                        result = AgentRunResult(
                            agent_name=definition.name,
                            content=response.content
                            if isinstance(response.content, str)
                            else "",
                            activated_skills=tuple(available_skill_names),
                            raw_response=response,
                            usage_report=_usage_report_for_pipeline(
                                getattr(response, "pipeline_id", None)
                            ),
                        )
                        await emit_agent_listener_event(
                            "agent.run.finished",
                            input=input,
                            context=listener_context,
                            result=result,
                            content=result.content,
                            tool_results=list(result.tool_results),
                        )
                        return result
                    except Exception as exc:
                        await emit_ai_pipeline_event(
                            type="agent.failed",
                            name=definition.name,
                            payload={
                                "agent_title": definition.title or definition.name,
                                "error": str(exc),
                            },
                            status="error",
                        )
                        await emit_agent_listener_event(
                            "agent.run.failed",
                            input=input,
                            context=listener_context,
                            error=str(exc),
                        )
                        raise
            except Exception as exc:
                _log_agent_runtime_error(
                    generator=f"agent:{definition.name}",
                    error=exc,
                )
                raise
        finally:
            current_agent_execution.reset(token)

    async def run_pipeline(
        self,
        name: str,
        *,
        input: str = "",
        context: dict[str, Any] | None = None,
        provider: Any = None,
    ) -> dict[str, Any]:
        definition = self.pipeline_registry.get(name)
        if definition is None:
            raise ValueError(f"Unknown pipeline: {name}")

        try:
            with _runtime_guard(definition, subject_kind="pipeline"):
                state: dict[str, object] = {"input": input}
                if context is not None:
                    state.update(context)

                for step in definition.steps:
                    produced = await self._execute_pipeline_step(
                        step,
                        state=state,
                        provider=provider,
                    )
                    state.update(produced)

                return state
        except Exception as exc:
            _log_agent_runtime_error(
                generator=f"pipeline:{definition.name}",
                error=exc,
            )
            raise

    async def _resolve_provider(self, definition: AgentDefinition) -> Any:
        from democrai.core.application.ai.orchestrator import model_orchestrator

        result = await model_orchestrator.get_provider_for_objective(
            definition.objective
        )

        if result.get("status") != "ok" or "provider" not in result:
            raise RuntimeError(
                result.get("error")
                or f"Provider unavailable for objective '{definition.objective}'"
            )
        return result["provider"]

    async def _run_leaf_pipeline_step(
        self,
        step,
        *,
        state: dict[str, object],
        provider,
    ) -> tuple[str, object, object | None]:
        step_input = _resolve_pipeline_input(step, state)
        if step.kind == "agent":
            result = await self.run_agent(
                step.target,
                input="" if step_input is None else str(step_input),
                context=state,
                provider=provider,
            )
            return step.output_key, result.content, result

        tool_arguments = dict(step.arguments)
        if step_input is not None:
            tool_arguments.setdefault("input", step_input)
        tool_result = await self.run_tool(
            step.target,
            arguments=tool_arguments,
            context=state,
        )
        return step.output_key, tool_result, None

    async def _run_parallel_pipeline_step(
        self,
        step,
        *,
        state: dict[str, object],
        provider,
    ) -> dict[str, object]:
        branches = tuple(step.steps or ())
        if not branches:
            return {}
        max_concurrency = (
            int(step.max_concurrency)
            if isinstance(getattr(step, "max_concurrency", None), int)
            and int(step.max_concurrency) > 0
            else 0
        )
        semaphore = asyncio.Semaphore(max_concurrency) if max_concurrency else None

        async def _run_branch(branch_step):
            branch_state = dict(state)
            if semaphore is None:
                return await self._execute_pipeline_step(
                    branch_step,
                    state=branch_state,
                    provider=provider,
                )
            async with semaphore:
                return await self._execute_pipeline_step(
                    branch_step,
                    state=branch_state,
                    provider=provider,
                )

        if step.error_policy == "collect_errors":
            settled = await asyncio.gather(
                *(_run_branch(branch_step) for branch_step in branches),
                return_exceptions=True,
            )
            outputs: dict[str, object] = {}
            errors: list[dict[str, str]] = []
            for idx, item in enumerate(settled):
                if isinstance(item, Exception):
                    branch_step = branches[idx]
                    _log_agent_runtime_error(
                        generator=(
                            f"pipeline.parallel:{step.output_key}:"
                            f"{branch_step.kind}:{branch_step.target or branch_step.output_key}"
                        ),
                        error=item,
                    )
                    errors.append({"branch_index": str(idx), "error": str(item)})
                    continue
                branch_outputs = item if isinstance(item, dict) else {}
                for output_key, value in branch_outputs.items():
                    if output_key in outputs:
                        raise ValueError(
                            f"Parallel pipeline step produced duplicate output_key '{output_key}'"
                        )
                    outputs[output_key] = value
            if errors:
                outputs[f"{step.output_key}_errors"] = errors
            return outputs

        settled = await asyncio.gather(
            *(_run_branch(branch_step) for branch_step in branches)
        )
        outputs: dict[str, object] = {}
        for item in settled:
            branch_outputs = item if isinstance(item, dict) else {}
            for output_key, value in branch_outputs.items():
                if output_key in outputs:
                    raise ValueError(
                        f"Parallel pipeline step produced duplicate output_key '{output_key}'"
                    )
                outputs[output_key] = value
        return outputs

    async def _execute_pipeline_step(
        self,
        step,
        *,
        state: dict[str, object],
        provider,
    ) -> dict[str, object]:
        local_state = dict(state)
        produced: dict[str, object] = {}

        if step.kind == "parallel":
            parallel_outputs = await self._run_parallel_pipeline_step(
                step,
                state=local_state,
                provider=provider,
            )
            for output_key, value in parallel_outputs.items():
                if output_key == step.output_key:
                    raise ValueError(
                        f"Parallel pipeline output_key '{output_key}' conflicts with parent output key"
                    )
                if output_key in produced:
                    raise ValueError(
                        f"Parallel pipeline merge conflict on key '{output_key}'"
                    )
                produced[output_key] = value
                local_state[output_key] = value
            produced[step.output_key] = dict(parallel_outputs)
            local_state[step.output_key] = produced[step.output_key]
        else:
            output_key, value, agent_result = await self._run_leaf_pipeline_step(
                step,
                state=local_state,
                provider=provider,
            )
            produced[output_key] = value
            local_state[output_key] = value
            if agent_result is not None:
                result_key = f"{output_key}_result"
                produced[result_key] = agent_result
                local_state[result_key] = agent_result

        if step.kind != "parallel":
            for child_step in tuple(step.steps or ()):
                child_outputs = await self._execute_pipeline_step(
                    child_step,
                    state=local_state,
                    provider=provider,
                )
                for key, value in child_outputs.items():
                    if key in produced:
                        raise ValueError(
                            f"Pipeline step '{step.output_key}' produced duplicate key '{key}'"
                        )
                    produced[key] = value
                    local_state[key] = value

        return produced


def _merge_names(
    base_names: tuple[str, ...] | None,
    extra_names: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    merged: list[str] = []
    base_values = list(base_names) if base_names is not None else []
    extra_values = list(extra_names) if extra_names is not None else []
    for item in base_values + extra_values:
        text = item.strip() if isinstance(item, str) else ""
        if text and text not in merged:
            merged.append(text)
    return tuple(merged)


def _agent_runtime_config(agent_name: str) -> dict[str, Any]:
    with SessionLocal() as session:
        row = (
            session.query(AgentModelConfig)
            .filter(AgentModelConfig.agent_name == agent_name)
            .first()
        )
        if row is None:
            return {
                "extra_tools": (),
                "extra_skills": (),
                "extra_mcp_servers": (),
                "extra_agents": (),
                "max_iterations": None,
            }
        return {
            "extra_tools": _normalize_string_tuple(row.extra_tools),
            "extra_skills": _normalize_string_tuple(row.extra_skills),
            "extra_mcp_servers": _normalize_string_tuple(row.extra_mcp_servers),
            "extra_agents": _normalize_string_tuple(row.extra_agents),
            "max_iterations": int(row.max_iterations)
            if row.max_iterations is not None
            else None,
        }


def _normalize_string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        value = [value] if value is not None else []
    normalized: list[str] = []
    for item in value:
        text = item.strip() if isinstance(item, str) else ""
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized)


def _log_agent_runtime_error(*, generator: str, error: BaseException) -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        app_ctx().logger.error(
            f"[AI Pipeline] AGENT FAILED {generator} error={error}\n",
            name="AGENT_CALL",
            exc_info=False,
        )
    except Exception:
        pass


def _normalize_agent_names(
    names: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    normalized: list[str] = []
    for item in list(names) if names is not None else ():
        text = (
            item.strip().removeprefix("agent.").strip() if isinstance(item, str) else ""
        )
        if text and text not in normalized:
            normalized.append(text)
    return tuple(normalized)


async def _invoke_callable(
    func: Any,
    *,
    payload: dict[str, Any],
    extra_context: dict[str, Any] | None = None,
) -> Any:
    extra_context = {} if extra_context is None else extra_context
    sig = inspect.signature(func)
    call_args: dict[str, Any] = {}
    used_payload_keys: set[str] = set()

    for param_name, param in sig.parameters.items():
        if param.kind == inspect.Parameter.VAR_KEYWORD:
            continue
        if param_name == "ctx" or (param_name == "input" and "input" not in payload):
            call_args[param_name] = payload
        elif param_name in payload:
            call_args[param_name] = payload[param_name]
            used_payload_keys.add(param_name)
        elif param_name in extra_context:
            call_args[param_name] = extra_context[param_name]
        elif param.default is inspect.Parameter.empty:
            continue

    if any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in sig.parameters.values()
    ):
        for key, value in payload.items():
            if key not in used_payload_keys:
                call_args[key] = value

    result = func(**call_args)
    if inspect.isawaitable(result):
        return await result
    return result


def _normalize_agent_run_result(
    definition: AgentDefinition,
    result: Any,
) -> AgentRunResult:
    if isinstance(result, AgentRunResult):
        return result
    if isinstance(result, dict):
        raw_content = result.get("content", "")
        return AgentRunResult(
            agent_name=definition.name,
            content="" if raw_content is None else str(raw_content),
            tool_results=tuple(result.get("tool_results", ())),
            activated_skills=tuple(result.get("activated_skills", ())),
            raw_response=result,
            usage_report=tuple(result.get("usage_report", ())),
        )
    return AgentRunResult(
        agent_name=definition.name,
        content="" if result is None else str(result),
    )


def _usage_report_for_pipeline(pipeline_id: Any) -> tuple[dict[str, Any], ...]:
    resolved_pipeline_id = pipeline_id.strip() if isinstance(pipeline_id, str) else ""
    if not resolved_pipeline_id:
        return ()
    from democrai.core.runtime.foundation.app import app_ctx

    obs_store = getattr(app_ctx(), "obs_store", None)
    if obs_store is None:
        return ()
    events = obs_store.get_ai_model_usage_events_for_pipeline(
        pipeline_id=resolved_pipeline_id
    )
    report: list[dict[str, Any]] = []
    for event in events:
        row = event.to_dict()
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        report.append(
            {
                "id": row.get("id"),
                "timestamp": row.get("timestamp"),
                "provider": row.get("provider"),
                "engine": row.get("engine"),
                "model_name": row.get("model_name"),
                "request_kind": row.get("request_kind"),
                "agent_id": row.get("agent_id"),
                "prompt_tokens": row.get("prompt_tokens"),
                "completion_tokens": row.get("completion_tokens"),
                "total_tokens": row.get("total_tokens"),
                "duration_ms": row.get("duration_ms"),
                "tokens_per_second": row.get("tokens_per_second"),
                "success": row.get("success"),
                "error": row.get("error"),
                "pipeline_id": metadata.get("pipeline_id"),
                "current_pipeline_id": metadata.get("current_pipeline_id"),
                "parent_pipeline_id": metadata.get("parent_pipeline_id"),
                "step_id": metadata.get("step_id"),
            }
        )
    return tuple(report)


def _resolve_pipeline_input(step: Any, state: dict[str, Any]) -> Any:
    if getattr(step, "input_template", None):
        return _safe_format(step.input_template, state)
    if getattr(step, "input_key", None):
        return state.get(step.input_key)
    return state.get("input")


def _safe_format(template: str, values: dict[str, Any]) -> str:
    formatter = Formatter()
    chunks: list[str] = []
    for literal_text, field_name, format_spec, conversion in formatter.parse(template):
        chunks.append(literal_text)
        if not field_name:
            continue
        value = values.get(field_name, "")
        rendered = str(value)
        if conversion:
            rendered = format(rendered, "")
        if format_spec:
            rendered = format(rendered, format_spec)
        chunks.append(rendered)
    return "".join(chunks)


agent_runtime = AgentRuntime()
