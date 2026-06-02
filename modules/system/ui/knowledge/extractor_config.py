from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.knowledge.extractors import (
    extractor_mime_config_rows,
    extractor_mime_config_table_model,
)


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/knowledge/extractors/config")
    merge_builders(builder, page_builder)

    rows = extractor_mime_config_rows(sdk)
    table = builder.get_component("knowledge_extractor_mime_config_table")
    if table is not None:
        table.set_property("model", extractor_mime_config_table_model(sdk))
        table.set_property("rows", rows)
        table.set_property("total_rows", len(rows))

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(
            [component.id for component in page_builder.get_roots() if component.id]
        )
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
