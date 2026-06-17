from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.actions.engine.quotas import (
    quota_counter_table_model,
)


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/engine/quota_counters_list")
    table = page_builder.get_component("engine_quota_counters_table")
    if table is not None:
        table.set_property("model", quota_counter_table_model(sdk))

    merge_builders(builder, page_builder)
    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["engine_quota_counters_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)
    return builder
