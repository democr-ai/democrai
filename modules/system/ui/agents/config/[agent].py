from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.agent_model_config import agent_form_model


async def render(params: dict, session: dict):
    route_params = (
        params.get("route_params")
        if isinstance(params.get("route_params"), dict)
        else {}
    )
    agent_name = str(route_params.get("agent") or "").strip()
    builder = sdk.ui.load("utils/ui/yaml/agents/config")
    title = builder.get_component("system_agent_config_title")
    form = builder.get_component("system_agent_config_form")
    if title is not None:
        title.set_property("text", f"Agent model: {agent_name}")
    if form is not None:
        form.set_property("model", agent_form_model(sdk, agent_name))
        form.set_property(
            "action",
            {
                "name": "system.save_agent_model_config",
            },
        )
        form.set_property("params", {"agent_name": agent_name})
    return builder
