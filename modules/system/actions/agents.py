from __future__ import annotations

import json
import time
from typing import Any

from pydantic import BaseModel, Field, field_validator

from democrai.sdk.ai_constants import AICapability
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action, validate

from modules.system.utils.actions.engine.model_test_support import _test_result
from modules.system.utils.agent_model_config import agent_rows


AGENTS_TABLE_ID = "system_agents_table"


class AgentTestFormPayload(BaseModel):
    model_registry_id: int = Field(gt=0)
    prompt: str = Field(min_length=1)
    extra_tools: list[str] = Field(default_factory=list)
    extra_skills: list[str] = Field(default_factory=list)
    extra_mcp_servers: list[str] = Field(default_factory=list)
    extra_agents: list[str] = Field(default_factory=list)
    max_iterations: int = Field(gt=0)

    @field_validator("prompt")
    @classmethod
    def _clean_prompt(cls, value: str) -> str:
        prompt = value.strip()
        if not prompt:
            raise ValueError("prompt is required")
        return prompt

    @field_validator(
        "extra_tools",
        "extra_skills",
        "extra_mcp_servers",
        "extra_agents",
    )
    @classmethod
    def _clean_name_list(cls, value: list[str]) -> list[str]:
        return _strings(value)


class AgentTestPayload(BaseModel):
    agent_name: str = Field(min_length=1)
    system_agent_test_form: AgentTestFormPayload

    @field_validator("agent_name")
    @classmethod
    def _clean_agent_name(cls, value: str) -> str:
        agent_name = value.strip()
        if not agent_name:
            raise ValueError("agent_name is required")
        return agent_name


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _capabilities(row: dict[str, Any]) -> set[str]:
    raw = row.get("capabilities") or []
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(",") if item.strip()}
    return {str(item or "").strip() for item in raw if str(item or "").strip()}


def _usage_metrics(usage_report: list[dict[str, Any]]) -> str:
    lines = []
    for index, item in enumerate(usage_report, start=1):
        label = str(item.get("agent_id") or item.get("request_kind") or f"step_{index}")
        model_name = str(item.get("model_name") or "-")
        lines.append(
            f"{index}. {label} | model={model_name} | "
            f"prompt_tokens={item.get('prompt_tokens')} | "
            f"completion_tokens={item.get('completion_tokens')} | "
            f"total_tokens={item.get('total_tokens')} | "
            f"duration_ms={item.get('duration_ms')}"
        )
    return "\n".join(lines)


def _agent_test_state_update(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "stateUpdate": {
            "scope": "page",
            "values": {
                "/system/agents/test/last_result": result,
                "/system/agents/test/last_status": str(result.get("status") or ""),
                "/system/agents/test/listener_events": list(
                    result.get("listener_events") or []
                ),
            },
        }
    }


def _agent_test_response(
    module_sdk,
    result: dict[str, Any],
    *,
    error: Exception | None = None,
):
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([_agent_test_state_update(result)]),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "error" if error is not None else "success",
                "message": (
                    str(error)
                    if error is not None
                    else module_sdk.i18n.t("system.agents.test.completed")
                ),
            },
        ),
    )


def _event_value(value: Any) -> str:
    if value in (None, ""):
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return str(value)


def _agent_event_entry(event: dict[str, Any]) -> dict[str, str]:
    event_type = str(event.get("type") or "").strip() or "agent.event"
    agent_name = str(event.get("agent_name") or "").strip()
    status = str(event.get("status") or "").strip()
    title = event_type
    if agent_name:
        title = f"{title} | {agent_name}"
    if status:
        title = f"{title} | {status}"
    details = []
    for key in (
        "name",
        "tool_name",
        "function_name",
        "content",
        "text",
        "error",
    ):
        value = _event_value(event.get(key))
        if value:
            details.append(f"{key}={value}")
    return {"title": title, "text": " | ".join(details) or "-"}


def _agent_pipeline_message_entry(message: Any) -> dict[str, str]:
    event_type = str(
        getattr(message, "type", "")
        or (message.get("type") if isinstance(message, dict) else "")
        or "pipeline.message"
    ).strip()
    name = str(
        getattr(message, "name", "")
        or (message.get("name") if isinstance(message, dict) else "")
        or ""
    ).strip()
    status = str(
        getattr(message, "status", "")
        or (message.get("status") if isinstance(message, dict) else "")
        or ""
    ).strip()
    payload = (
        getattr(message, "payload", None)
        if not isinstance(message, dict)
        else message.get("payload")
    )
    title = event_type
    if name:
        title = f"{title} | {name}"
    if status:
        title = f"{title} | {status}"
    return {"title": title, "text": _event_value(payload) or "-"}


@action("list_agents")
@permission_required(["system.engine.model.manage"])
async def list_agents(ctx: dict[str, Any], session: dict, module_sdk):
    rows = agent_rows(module_sdk)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            AGENTS_TABLE_ID,
            "rows",
            rows,
            action="set",
        ),
        module_sdk.effects.ui_property_update(AGENTS_TABLE_ID, "total_rows", len(rows)),
    )


@action("save_agent_model_config")
@permission_required(["system.engine.model.manage"])
async def save_agent_model_config(ctx: dict[str, Any], session: dict, module_sdk):
    agent_name = str(ctx["agent_name"]).strip()
    if not agent_name:
        raise ValueError("agent_name_required")
    payload = dict(ctx[str(ctx["form_id"])])
    payload["agent_name"] = agent_name
    module_sdk.models.agent_model_configs.create(payload)
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
        module_sdk.effects.render(),
    )


@action("test_agent")
@validate(AgentTestPayload, strip_extra=True)
@permission_required(["system.engine.model.manage"])
async def test_agent(ctx: dict[str, Any], session: dict, module_sdk):
    try:
        agent_name = ctx["agent_name"]
        payload = ctx["system_agent_test_form"]
        prompt = payload["prompt"]
        model_registry_id = payload["model_registry_id"]
        model = module_sdk.models.model_registry.view(model_registry_id)
        if not isinstance(model, dict):
            raise ValueError("model_not_found")
        if AICapability.TOOL_CALLING not in _capabilities(model):
            raise ValueError("model_without_tool_calling")
        max_iterations = payload["max_iterations"]
        extra_tools = payload["extra_tools"]
        extra_skills = payload["extra_skills"]
        extra_mcp_servers = payload["extra_mcp_servers"]
        extra_agents = payload["extra_agents"]
        listener_events: list[dict[str, str]] = []
        stream_id = str(ctx.get("stream_id") or "").strip()

        async def _append_trace_entry(entry: dict[str, str]) -> None:
            listener_events.append(entry)
            if stream_id:
                await module_sdk.effects.publish_state_patch(
                    stream_id,
                    "/system/agents/test/listener_events",
                    "append",
                    entry,
                    scope="page",
                )

        async def _listener(event: dict[str, Any]) -> None:
            await _append_trace_entry(_agent_event_entry(event))

        async def _on_message(message: Any) -> None:
            await _append_trace_entry(_agent_pipeline_message_entry(message))

        if stream_id:
            await module_sdk.effects.publish_state_patch(
                stream_id,
                "/system/agents/test/listener_events",
                "set",
                [],
                scope="page",
            )
        started = time.perf_counter()
        result = await module_sdk.ai.run_agent(
            agent_name,
            input=prompt,
            context={"source": "system.agents.test"},
            model_registry_id=model_registry_id,
            extra_tools=extra_tools,
            extra_skills=extra_skills,
            extra_mcp_servers=extra_mcp_servers,
            extra_agents=extra_agents,
            max_iterations=max_iterations,
            listener=_listener,
            on_message=_on_message,
        )
        duration_ms = round((time.perf_counter() - started) * 1000.0, 2)
        output = str(getattr(result, "content", "") or "")
        if not output and isinstance(result, dict):
            output = str(result.get("content") or result)
        usage_report = list(getattr(result, "usage_report", ()) or ())
        payload_result = _test_result(
            status="ok",
            method="agent",
            output=output,
            duration_ms=duration_ms,
            resources={
                "agent": agent_name,
                "model_registry_id": model_registry_id,
                "extra_tools": extra_tools,
                "extra_skills": extra_skills,
                "extra_mcp_servers": extra_mcp_servers,
                "extra_agents": extra_agents,
                "max_iterations": max_iterations,
                "tool_results": list(getattr(result, "tool_results", ()) or ()),
                "activated_skills": list(getattr(result, "activated_skills", ()) or ()),
                "usage_report": usage_report,
                "listener_events": listener_events,
            },
        )
        payload_result["listener_events"] = listener_events
        if usage_report:
            payload_result["metrics"] = _usage_metrics(usage_report)
        return _agent_test_response(module_sdk, payload_result)
    except Exception as exc:
        payload_result = _test_result(status="error", method="agent", output=str(exc))
        if "listener_events" in locals():
            payload_result["listener_events"] = listener_events
            payload_result.setdefault("resources", {})["listener_events"] = listener_events
        return _agent_test_response(module_sdk, payload_result, error=exc)
