from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.utils.agent_model_config import agent_rows
from modules.system.ui.layout import shared_layout


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    page_builder = sdk.ui.load("utils/ui/yaml/agents/list")
    merge_builders(builder, page_builder)
    table = builder.get_component("system_agents_table")
    if table is not None:
        rows = agent_rows(sdk)
        table.set_property("rows", rows)
        table.set_property("total_rows", len(rows))
    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children([component.id for component in page_builder.get_roots() if component.id])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)
    return builder
