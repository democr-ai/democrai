from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/knowledge/config")
    merge_builders(builder, page_builder)

    builder.set_data(
        "/knowledge/config",
        {"form_model": sdk.knowledge.runtime_config_form_model()},
    )

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(
            [component.id for component in page_builder.get_roots() if component.id]
        )
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
