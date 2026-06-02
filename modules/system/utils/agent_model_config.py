from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AICapability

from modules.system.utils.ui.model.runtime import available_model_name


POLICY_OPTIONS = [
    {"label": "by system", "value": "by_system"},
    {"label": "by parent", "value": "by_parent"},
    {"label": "specific model", "value": "specific_model"},
]


def active_model_options(sdk) -> list[dict[str, Any]]:
    rows = sdk.models.model_registry.all(filters={"status": "active"}).get("rows") or []
    options: list[dict[str, Any]] = [{"label": "none", "value": ""}]
    for row in rows:
        capabilities = _capabilities(row)
        if not {"chat", "tool_calling"} & capabilities:
            continue
        options.append(
            {
                "label": available_model_name(row) or str(row.get("id")),
                "value": int(row["id"]),
            }
        )
    return options


def active_tool_calling_model_options(sdk) -> list[dict[str, Any]]:
    rows = sdk.models.model_registry.all(
        filters={"status": "active"},
        sort={"field": "name", "direction": "asc"},
    ).get("rows") or []
    options: list[dict[str, Any]] = []
    for row in rows:
        if AICapability.TOOL_CALLING not in _capabilities(row):
            continue
        row_id = row.get("id")
        if row_id in (None, ""):
            continue
        model_name = available_model_name(row) or str(row_id)
        engine_name = _engine_label(sdk, row.get("engine_id"))
        options.append(
            {
                "label": f"{model_name} - {engine_name}",
                "value": int(row_id),
            }
        )
    return options


def agent_tool_options(sdk) -> list[dict[str, Any]]:
    return [_option(tool.name, tool.title or tool.name) for tool in sdk.ai.list_tools()]


def agent_skill_options(sdk) -> list[dict[str, Any]]:
    return [
        _option(skill.metadata.name, skill.metadata.title or skill.metadata.name)
        for skill in sdk.ai.list_skills()
    ]


def agent_mcp_options(sdk) -> list[dict[str, Any]]:
    return [_option(server.name, server.name) for server in sdk.ai.list_mcp_servers()]


def agent_subagent_options(sdk, current_agent_name: str) -> list[dict[str, Any]]:
    return [
        _option(agent.name, agent.title or agent.name)
        for agent in sdk.ai.list_agents()
        if agent.name != current_agent_name
    ]


def agent_rows(sdk) -> list[dict[str, Any]]:
    configs = {
        row["agent_name"]: row
        for row in sdk.models.agent_model_configs.all().get("rows", [])
    }
    model_labels = {}
    for row in sdk.models.model_registry.all(filters={"status": "active"}).get("rows", []):
        model_labels[int(row["id"])] = available_model_name(row) or str(row["id"])
    rows = []
    for agent in sdk.ai.list_agents():
        config = configs.get(agent.name) or {}
        model_id = config.get("model_registry_id")
        rows.append(
            {
                "name": agent.name,
                "module_name": agent.module_name,
                "objective": agent.objective,
                "tools": ", ".join(agent.tools),
                "skills": ", ".join(agent.skills),
                "model_policy": config.get("model_policy") or "by_system",
                "model_registry_id": model_id,
                "model": model_labels.get(int(model_id), "") if model_id else "",
                "max_iterations": config.get("max_iterations") or agent.max_iterations,
                "configured": bool(config),
            }
        )
    return rows


def agent_form_model(sdk, agent_name: str) -> list[dict[str, Any]]:
    config = sdk.models.agent_model_configs.get_info(agent_name) or {}
    agent = sdk.ai.get_agent(agent_name)
    default_max_iterations = int(agent.max_iterations) if agent is not None else ""
    return [
        {
            "name": "model_policy",
            "label": "model policy",
            "type": "select",
            "value": config.get("model_policy") or "by_system",
            "options": POLICY_OPTIONS,
        },
        {
            "name": "model_registry_id",
            "label": "model",
            "type": "select",
            "value": config.get("model_registry_id") or "",
            "options": active_model_options(sdk),
        },
        {
            "name": "extra_tools",
            "label": "additional tools",
            "type": "tags",
            "value": _strings(config.get("extra_tools")),
            "add_label": "Add",
            "item_schema": _select_tag_schema(agent_tool_options(sdk)),
        },
        {
            "name": "extra_skills",
            "label": "additional skills",
            "type": "tags",
            "value": _strings(config.get("extra_skills")),
            "add_label": "Add",
            "item_schema": _select_tag_schema(agent_skill_options(sdk)),
        },
        {
            "name": "extra_mcp_servers",
            "label": "additional MCP",
            "type": "tags",
            "value": _strings(config.get("extra_mcp_servers")),
            "add_label": "Add",
            "item_schema": _select_tag_schema(agent_mcp_options(sdk)),
        },
        {
            "name": "extra_agents",
            "label": "additional subagents",
            "type": "tags",
            "value": _strings(config.get("extra_agents")),
            "add_label": "Add",
            "item_schema": _select_tag_schema(agent_subagent_options(sdk, agent_name)),
        },
        {
            "name": "max_iterations",
            "label": "max iterations",
            "type": "integer",
            "value": config.get("max_iterations") or default_max_iterations,
            "min": 1,
        },
    ]


def _option(value: Any, label: Any = "") -> dict[str, Any]:
    option_value = str(value or "").strip()
    option_label = str(label or option_value).strip() or option_value
    return {"label": option_label, "value": option_value}


def _select_tag_schema(options: list[dict[str, Any]]) -> dict[str, Any]:
    return {"type": "select", "options": options or [{"label": "-", "value": ""}]}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list):
        value = [value] if value else []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _capabilities(row: dict[str, Any]) -> set[str]:
    raw = row.get("capabilities") or []
    if isinstance(raw, str):
        return {item.strip() for item in raw.split(",") if item.strip()}
    return {str(item or "").strip() for item in raw if str(item or "").strip()}


def _engine_label(sdk, engine_id: Any) -> str:
    if engine_id in (None, ""):
        return "-"
    engine = sdk.models.engine_registry.view(int(engine_id))
    if not isinstance(engine, dict):
        return "-"
    return str(engine.get("name") or engine.get("provider") or "-").strip() or "-"
