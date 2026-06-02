from __future__ import annotations

import inspect
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class AgentExecutionContext:
    agent_name: str
    objective: str
    tool_names: tuple[str, ...] = ()
    skill_names: tuple[str, ...] = ()
    mcp_servers: tuple[str, ...] = ()
    listener: Callable[[dict[str, Any]], Any] | None = None


current_agent_execution: ContextVar[AgentExecutionContext | None] = ContextVar(
    "current_agent_execution",
    default=None,
)


async def emit_agent_listener_event(event_type: str, **payload: Any) -> None:
    ctx = current_agent_execution.get()
    if ctx is None or ctx.listener is None:
        return
    resolved_type = event_type.strip() if isinstance(event_type, str) else ""
    event = {
        "type": resolved_type,
        "agent_name": ctx.agent_name,
        "objective": ctx.objective,
        **payload,
    }
    result = ctx.listener(event)
    if inspect.isawaitable(result):
        await result
