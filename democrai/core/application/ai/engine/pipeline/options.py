from __future__ import annotations

from typing import Any

from democrai.core.application.ai.pipeline_context import current_ai_pipeline_context
from democrai.core.application.ai.engine.pipeline.tool_aliases import (
    TOOL_ALIAS_MAP_OPTION,
)
from democrai.core.application.ai.engine.pipeline.tool_aliases import alias_completion_tools
from democrai.core.application.ai.engine.pipeline.tool_aliases import alias_tool_choice
from democrai.core.platform.agents.tool_runtime import agent_tool_runtime


def tool_max_iterations(options: Any) -> int:
    if isinstance(options, dict):
        extra = options.get("extra") if isinstance(options.get("extra"), dict) else {}
        raw = options.get("tool_max_iterations", extra.get("tool_max_iterations"))
        if raw not in (None, ""):
            return max(0, min(16, int(raw)))
    return 4


def string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TypeError("string_list_expected")
    for item in value:
        if not isinstance(item, str):
            raise TypeError("string_list_item_expected")
    return [item for item in value if item]


async def prepare_pipeline_options(options: Any) -> Any:
    if not isinstance(options, dict):
        return options
    resolved = dict(options)
    selected_tools = string_list(resolved.pop("tools", []))
    active_mcp = string_list(resolved.pop("mcp", []))
    selected_agents = string_list(resolved.pop("agents", []))
    selected_skills = string_list(resolved.pop("skills", []))
    local_tool_names = [
        name
        for name in selected_tools
        if not name.startswith("mcp.") and not name.startswith("agent.")
    ]
    if selected_skills and "core.run-skill-script" not in local_tool_names:
        local_tool_names.append("core.run-skill-script")
    selected_mcp_tools = [
        name for name in selected_tools if name.startswith("mcp.")
    ]
    selected_agent_tools = [
        name for name in selected_tools if name.startswith("agent.")
    ]
    if selected_agent_tools:
        selected_agents = [*selected_agents, *selected_agent_tools]
    if selected_mcp_tools and not active_mcp:
        active_mcp = sorted(
            {
                parts[1]
                for parts in (name.split(".") for name in selected_mcp_tools)
                if len(parts) >= 3 and parts[1]
            }
        )
    if selected_tools or active_mcp or selected_agents or selected_skills:
        existing_tools = list(resolved.get("tools") or [])
        tool_definitions = agent_tool_runtime.resolve_tool_definitions(tuple(local_tool_names))
        missing_tools = sorted(
            set(local_tool_names) - {tool.name for tool in tool_definitions}
        )
        if missing_tools:
            raise ValueError(f"tool_not_found:{','.join(missing_tools)}")
        if active_mcp:
            context = current_ai_pipeline_context()
            module_name = context.caller_module if context is not None else "core"
            mcp_tools = await agent_tool_runtime.list_mcp_tool_definitions(
                module_name=module_name,
                server_names=tuple(active_mcp),
            )
            if selected_mcp_tools:
                selected_mcp_set = set(selected_mcp_tools)
                mcp_tools = [tool for tool in mcp_tools if tool.name in selected_mcp_set]
                missing_mcp_tools = sorted(
                    selected_mcp_set - {tool.name for tool in mcp_tools}
                )
                if missing_mcp_tools:
                    raise ValueError(f"tool_not_found:{','.join(missing_mcp_tools)}")
            tool_definitions.extend(mcp_tools)
        if selected_agents:
            tool_definitions.extend(
                agent_tool_runtime.resolve_agent_tool_definitions(
                    tuple(selected_agents)
                )
            )
        completion_tools = [
            _resolved_completion_tool(tool.to_completion_tool(), selected_skills)
            for tool in tool_definitions
        ]
        aliased_tools, alias_map = alias_completion_tools(
            [
                *existing_tools,
                *completion_tools,
            ]
        )
        resolved["tools"] = [
            *aliased_tools,
        ]
        resolved[TOOL_ALIAS_MAP_OPTION] = alias_map
        resolved["tool_choice"] = alias_tool_choice(
            resolved.get("tool_choice"),
            alias_map,
        )
        resolved["tool_choice"] = resolved.get("tool_choice") or "auto"
    return resolved


def iteration_pipeline_options(options: Any, *, iteration: int) -> Any:
    if not isinstance(options, dict):
        return options
    if iteration <= 0:
        return options
    resolved = dict(options)
    if isinstance(resolved.get("tool_choice"), dict):
        resolved["tool_choice"] = "none"
    return resolved


def _tool_name(tool: Any) -> str:
    function = getattr(tool, "function", None)
    name = getattr(function, "name", None)
    if name:
        return str(name)
    if isinstance(tool, dict):
        function = tool.get("function")
        if isinstance(function, dict) and function.get("name"):
            return str(function["name"])
    return ""


def _resolved_completion_tool(tool: Any, selected_skills: list[str]) -> Any:
    if _tool_name(tool) != "core.run-skill-script" or not selected_skills:
        return tool
    if len(selected_skills) != 1:
        return tool

    from democrai.core.platform.agents.registry import skill_registry

    skill_name = selected_skills[0]
    skill = skill_registry.get(skill_name)
    if skill is None:
        return tool

    function = getattr(tool, "function", None)
    parameters = getattr(function, "parameters", None)
    if not isinstance(parameters, dict):
        return tool
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return tool

    resolved_parameters = dict(parameters)
    resolved_properties = dict(properties)
    skill_property = dict(resolved_properties.get("skill") or {})
    skill_property["enum"] = [skill_name]
    resolved_properties["skill"] = skill_property
    scripts = list(skill.metadata.script_paths or ())
    if scripts:
        script_property = dict(resolved_properties.get("script") or {})
        script_property["enum"] = scripts
        resolved_properties["script"] = script_property
    resolved_parameters["properties"] = resolved_properties
    return tool.model_copy(
        update={
            "function": function.model_copy(
                update={"parameters": resolved_parameters}
            )
        }
    )
