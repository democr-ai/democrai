from __future__ import annotations

from typing import Any

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.agent_model_config import (
    active_tool_calling_model_options,
    agent_mcp_options,
    agent_rows,
    agent_skill_options,
    agent_subagent_options,
    agent_tool_options,
)


def _csv(values: Any) -> str:
    if not isinstance(values, (list, tuple)):
        values = [values] if values else []
    return ", ".join(str(item or "").strip() for item in values if str(item or "").strip())


def _agent_definition(agent_name: str):
    for agent in sdk.ai.list_agents():
        if agent.name == agent_name:
            return agent
    return None


def _agent_row(agent_name: str) -> dict[str, Any]:
    for row in agent_rows(sdk):
        if str(row.get("name") or "").strip() == agent_name:
            return dict(row)
    return {}


def _select_tag_schema(options: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "select", "options": options or [{"label": "-", "value": ""}]}


def _form_model(agent, model_options: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected_model = model_options[0]["value"] if model_options else ""
    return [
        {
            "name": "model_registry_id",
            "label": sdk.i18n.t("system.agents.test.field.model"),
            "type": "select",
            "value": selected_model,
            "options": model_options,
            "validations": [{"rule": "required"}],
        },
        {
            "name": "prompt",
            "label": sdk.i18n.t("system.agents.test.field.prompt"),
            "type": "textarea",
            "value": sdk.i18n.t("system.agents.test.default_prompt"),
            "validations": [{"rule": "required"}],
        },
        {
            "name": "extra_tools",
            "label": sdk.i18n.t("system.agents.test.field.extra_tools"),
            "type": "tags",
            "value": [],
            "add_label": sdk.i18n.t("system.agents.test.add_tag"),
            "item_schema": _select_tag_schema(agent_tool_options(sdk)),
        },
        {
            "name": "extra_skills",
            "label": sdk.i18n.t("system.agents.test.field.extra_skills"),
            "type": "tags",
            "value": [],
            "add_label": sdk.i18n.t("system.agents.test.add_tag"),
            "item_schema": _select_tag_schema(agent_skill_options(sdk)),
        },
        {
            "name": "extra_mcp_servers",
            "label": sdk.i18n.t("system.agents.test.field.extra_mcp"),
            "type": "tags",
            "value": [],
            "add_label": sdk.i18n.t("system.agents.test.add_tag"),
            "item_schema": _select_tag_schema(agent_mcp_options(sdk)),
        },
        {
            "name": "extra_agents",
            "label": sdk.i18n.t("system.agents.test.field.extra_subagents"),
            "type": "tags",
            "value": [],
            "add_label": sdk.i18n.t("system.agents.test.add_tag"),
            "item_schema": _select_tag_schema(agent_subagent_options(sdk, agent.name)),
        },
        {
            "name": "max_iterations",
            "label": sdk.i18n.t("system.agents.test.field.max_iterations"),
            "type": "integer",
            "value": int(agent.max_iterations),
            "min": 1,
            "validations": [{"rule": "required"}],
        },
    ]


async def render(params: dict, session: dict):
    route_params = (
        params.get("route_params")
        if isinstance(params.get("route_params"), dict)
        else {}
    )
    agent_name = str(route_params.get("agent") or "").strip()

    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/agents/test")
    merge_builders(builder, page_builder)

    agent = _agent_definition(agent_name)
    row = _agent_row(agent_name)
    if agent is not None:
        model_options = active_tool_calling_model_options(sdk)
        title = str(agent.title or agent.name).strip()
        store_payload = {
            "name": agent.name,
            "title": title,
            "description": str(agent.description or ""),
            "module_name": str(agent.module_name or "-"),
            "objective": str(agent.objective or "-"),
            "tools_text": _csv(list(agent.tools)) or "-",
            "skills_text": _csv(list(agent.skills)) or "-",
            "mcp_text": _csv(list(agent.mcp_servers)) or "-",
            "max_iterations": str(agent.max_iterations),
            "model_policy": str(row.get("model_policy") or "-"),
            "model": str(row.get("model") or "-"),
            "configured": bool(row.get("configured")),
            "configured_text": (
                sdk.i18n.t("system.agents.test.configured")
                if bool(row.get("configured"))
                else sdk.i18n.t("system.agents.test.not_configured")
            ),
            "detail_items": [
                {"title": "Objective", "text": str(agent.objective or "-")},
                {"title": "Model policy", "text": str(row.get("model_policy") or "-")},
                {"title": "Model", "text": str(row.get("model") or "-")},
                {"title": "Tools", "text": _csv(list(agent.tools)) or "-"},
                {"title": "Skills", "text": _csv(list(agent.skills)) or "-"},
                {"title": "MCP", "text": _csv(list(agent.mcp_servers)) or "-"},
                {"title": "Max iterations", "text": str(agent.max_iterations)},
            ],
            "form": _form_model(agent, model_options),
            "breadcrumb_segments": [
                {"label": "System", "path": "/system/index"},
                {"label": sdk.i18n.t("system.agents.title"), "path": "/system/agents/list"},
                {"label": title, "current": True},
            ],
            "valid": True,
            "last_status": "",
            "last_result": {
                "output": sdk.i18n.t("system.agents.test.result_empty"),
                "metrics": "",
            },
            "listener_events": [],
        }
    else:
        store_payload = {
            "name": agent_name,
            "title": sdk.i18n.t("system.agents.test.title"),
            "description": "",
            "module_name": "-",
            "objective": "-",
            "tools_text": "-",
            "skills_text": "-",
            "mcp_text": "-",
            "max_iterations": "-",
            "model_policy": "-",
            "model": "-",
            "configured": False,
            "configured_text": "-",
            "detail_items": [],
            "form": [],
            "breadcrumb_segments": [
                {"label": "System", "path": "/system/index"},
                {"label": sdk.i18n.t("system.agents.title"), "path": "/system/agents/list"},
                {"label": sdk.i18n.t("system.agents.test.title"), "current": True},
            ],
            "valid": False,
            "last_status": "",
            "last_result": {"output": "", "metrics": ""},
            "listener_events": [],
        }

    builder.set_store("/system/agents/test", store_payload, scope="page")

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["system_agent_test_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
