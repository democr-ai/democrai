from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import inspect
from typing import Any
from typing import Iterator

from democrai.core.application.ai.pipeline_context import emit_ai_pipeline_event
from democrai.core.platform.agents.execution_context import emit_agent_listener_event
from democrai.core.platform.agents.models import AgentToolDefinition
from democrai.core.platform.agents.registry import agent_registry
from democrai.core.platform.agents.registry import agent_tool_registry
from democrai.core.runtime.foundation.app import app_ctx


def _current_module_name() -> str:
    from democrai.core.runtime.foundation.app import req_ctx

    try:
        return req_ctx().module_name or "core"
    except LookupError:
        return "core"


def _tool_runtime_guard(definition: AgentToolDefinition):
    subject = definition.name.strip() if isinstance(definition.name, str) else ""
    if not subject:
        raise RuntimeError("agent_tool_runtime_subject_missing")
    from democrai.core.infrastructure.sandbox.process_guard import process_guard_context

    return process_guard_context(
        subject=subject,
        subject_kind="tool",
        access=definition.access,
    )


def _sdk_for_tool(definition: AgentToolDefinition):
    module_name = (
        definition.module_name.strip()
        if isinstance(definition.module_name, str) and definition.module_name.strip()
        else "core"
    )
    from democrai.sdk.client import SDK
    from democrai.core.runtime.foundation.app import app_ctx
    from democrai.core.runtime.foundation.app import req_ctx
    from democrai.core.application.session_keys import SessionKey

    session: dict[str, Any] = {}
    try:
        request = req_ctx()
        if request.user is not None:
            session[SessionKey.USER] = {
                "id": request.user,
                "organization_id": request.organization_id,
                "access_level": request.access_level,
                "role": request.role,
            }
    except LookupError:
        pass
    module_path = ""
    module = getattr(app_ctx(), "modules", None)
    if module is not None and module_name != "core":
        resolved = module.get_module(module_name)
        if resolved is not None:
            raw_module_path = getattr(resolved, "path", None)
            module_path = raw_module_path if isinstance(raw_module_path, str) else ""
    return SDK(module_path, module_name, session=session)


@contextmanager
def _tool_module_context(definition: AgentToolDefinition) -> Iterator[Any]:
    sdk = _sdk_for_tool(definition)
    from democrai.sdk.client import current_sdk
    from democrai.core.runtime.foundation.app import req_ctx
    from democrai.core.runtime.foundation.app import reset_req_ctx
    from democrai.core.runtime.foundation.app import set_req_ctx

    sdk_token = current_sdk.set(sdk)
    req_token = None
    try:
        request = req_ctx()
        if request.module_name != sdk.module_name:
            action_name = (
                definition.name
                if isinstance(definition.name, str) and definition.name
                else request.action_name
            )
            req_token = set_req_ctx(
                replace(
                    request,
                    module_name=sdk.module_name,
                    action_name=action_name,
                )
            )
    except LookupError:
        pass
    try:
        yield sdk
    finally:
        if req_token is not None:
            reset_req_ctx(req_token)
        current_sdk.reset(sdk_token)


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


class AgentToolRuntime:
    def __init__(self) -> None:
        self.agent_tool_registry = agent_tool_registry
        self.agent_registry = agent_registry

    def get_tool(self, name: str) -> AgentToolDefinition | None:
        return self.agent_tool_registry.get(name)

    def list_tools(
        self, *, module_name: str | None = None
    ) -> list[AgentToolDefinition]:
        return self.agent_tool_registry.get_all(module_name=module_name)

    def resolve_tool_definitions(
        self,
        tool_names: tuple[str, ...],
    ) -> list[AgentToolDefinition]:
        tools: list[AgentToolDefinition] = []
        for name in tool_names:
            tool = self.agent_tool_registry.get(name)
            if tool is not None:
                tools.append(tool)
        return tools

    def resolve_agent_tool_definitions(
        self,
        agent_names: tuple[str, ...],
    ) -> list[AgentToolDefinition]:
        definitions: list[AgentToolDefinition] = []
        for name in agent_names:
            agent_name = (
                name.removeprefix("agent.").strip() if isinstance(name, str) else ""
            )
            agent = self.agent_registry.get(agent_name)
            if agent is None:
                raise ValueError(f"agent_not_found:{agent_name}")
            definitions.append(
                AgentToolDefinition(
                    name=f"agent.{agent.name}",
                    func=lambda **_: None,
                    title=agent.title or agent.name,
                    description=agent.description or agent.objective,
                    input_schema={
                        "type": "object",
                        "properties": {
                            "input": {
                                "type": "string",
                                "description": "Task or message for the subagent.",
                            },
                        },
                        "required": ["input"],
                    },
                    module_name=agent.module_name,
                    access=agent.access,
                )
            )
        return definitions

    async def list_mcp_tool_definitions(
        self,
        *,
        module_name: str,
        server_names: tuple[str, ...] = (),
    ) -> list[AgentToolDefinition]:
        from democrai.core.platform.mcp.runtime import mcp_runtime

        return await mcp_runtime.list_agent_tool_definitions_async(
            module_name=module_name,
            server_names=server_names,
        )

    async def run_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None = None,
        module_name: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> Any:
        resolved_name = name.strip() if isinstance(name, str) else ""
        payload = {} if arguments is None else dict(arguments)
        listener_context = {} if context is None else context
        await emit_agent_listener_event(
            "agent.tool.started",
            tool_name=resolved_name,
            arguments=payload,
            context=listener_context,
        )
        if resolved_name.startswith("mcp."):
            result = await self._run_mcp_tool(
                resolved_name,
                arguments=payload,
                module_name=module_name,
                context=listener_context,
            )
            await emit_agent_listener_event(
                "agent.tool.finished",
                tool_name=resolved_name,
                arguments=payload,
                context=listener_context,
                result=result,
            )
            return result
        elif resolved_name.startswith("agent."):
            result = await self._run_agent_tool(
                resolved_name,
                arguments=payload,
                context=listener_context,
            )
            await emit_agent_listener_event(
                "agent.tool.finished",
                tool_name=resolved_name,
                arguments=payload,
                context=listener_context,
                result=result,
            )
            return result
        else:
            result = await self._run_tool(
                resolved_name,
                arguments=payload,
                context=listener_context,
            )
            await emit_agent_listener_event(
                "agent.tool.finished",
                tool_name=resolved_name,
                arguments=payload,
                context=listener_context,
                result=result,
            )
            return result

        # no way

    async def _run_tool(
        self,
        resolved_name: str,
        *,
        arguments: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> Any:
        definition = self.agent_tool_registry.get(resolved_name)
        if definition is None:
            raise ValueError(f"Unknown agent tool: {resolved_name}")
        payload = {} if arguments is None else dict(arguments)
        listener_context = {} if context is None else context
        try:
            with _tool_runtime_guard(definition):
                with _tool_module_context(definition) as tool_sdk:
                    result = await _invoke_callable(
                        definition.func,
                        payload=payload,
                        extra_context={
                            **listener_context,
                            "context": listener_context,
                            "sdk": tool_sdk,
                        },
                    )
                    return result
        except Exception as exc:
            app_ctx().logger.error(
                f"[AI Pipeline] CALLED {resolved_name} AS TOOL RUNTIME WITH ERROR\n",
                name="TOOL_CALL",
                exc_info=False,
            )
            await emit_agent_listener_event(
                "agent.tool.failed",
                tool_name=resolved_name,
                arguments=payload,
                context=listener_context,
                error=str(exc),
            )
            raise

    async def _run_agent_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None,
        context: dict[str, Any] | None,
    ) -> Any:
        from democrai.core.platform.agents.runtime import agent_runtime

        agent_name = (
            name.removeprefix("agent.").strip() if isinstance(name, str) else ""
        )
        agent = self.agent_registry.get(agent_name)
        if agent is not None:
            agent_title = agent.title if agent.title else agent.name
        else:
            agent_title = agent_name
        payload = {} if arguments is None else dict(arguments)
        await emit_ai_pipeline_event(
            type="agent.call",
            name=name,
            payload={
                "agent_title": agent_title,
                "arguments": payload,
            },
        )
        try:
            if "input" not in payload:
                raise ValueError(
                    "agent_tool_input_required: pass the task in the input field"
                )
            result = await agent_runtime.run_agent(
                agent_name,
                input=payload["input"],
                context=context,
            )
        except Exception as exc:
            app_ctx().logger.error(
                f"[AI Pipeline] AGENT CALL FAILED {agent_name} WITH TOOL {name}\n",
                name="TOOL_CALL",
                exc_info=False,
            )

            await emit_ai_pipeline_event(
                type="agent.failed",
                name=name,
                payload={
                    "agent_title": agent_title,
                    "error": str(exc),
                },
                status="error",
            )
            raise
        await emit_ai_pipeline_event(
            type="agent.response",
            name=name,
            payload={
                "content": result.content,
                "agent": result.agent_name,
                "agent_title": agent_title,
            },
            status="ok",
        )
        return {
            "agent": result.agent_name,
            "content": result.content,
        }

    async def _run_mcp_tool(
        self,
        name: str,
        *,
        arguments: dict[str, Any] | None,
        module_name: str | None,
        context: dict[str, Any] | None,
    ) -> Any:
        from democrai.core.platform.mcp.runtime import mcp_runtime

        resolved_name = name.strip() if isinstance(name, str) else ""
        payload = {} if arguments is None else dict(arguments)
        resolved_module_name = (
            module_name.strip()
            if isinstance(module_name, str) and module_name.strip()
            else _current_module_name()
        )
        mcp_name = _mcp_server_name(name)
        try:
            await emit_ai_pipeline_event(
                type="mcp.call",
                name=resolved_name,
                payload={
                    "mcp_name": mcp_name,
                    "arguments": payload,
                },
            )
            result = await mcp_runtime.invoke_tool_async(
                full_name=resolved_name,
                arguments=payload,
                module_name=resolved_module_name,
            )
            await emit_ai_pipeline_event(
                type="mcp.response",
                name=resolved_name,
                payload={
                    "mcp_name": mcp_name,
                    "result": result,
                },
                status="ok",
            )
            return result
        except Exception as exc:
            app_ctx().logger.error(
                f"[AI Pipeline] MCP TOOL FAILED {resolved_name} MCP {mcp_name}\n",
                name="TOOL_CALL",
                exc_info=False,
            )
            await emit_ai_pipeline_event(
                type="mcp.response",
                name=resolved_name,
                payload={
                    "mcp_name": mcp_name,
                    "error": str(exc),
                },
                status="error",
            )
            await emit_agent_listener_event(
                "agent.tool.failed",
                tool_name=resolved_name,
                arguments=payload,
                context={} if context is None else context,
                error=str(exc),
            )
            raise


def _mcp_server_name(name: str) -> str:
    parts = name.strip().split(".") if isinstance(name, str) else []
    if len(parts) >= 3 and parts[0] == "mcp":
        return parts[1].strip()
    return ""


agent_tool_runtime = AgentToolRuntime()
