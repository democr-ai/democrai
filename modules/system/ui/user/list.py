from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.dataproviders.user import user_table_provider


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/user/list")
    builder.set_data("/system/user/list", user_table_provider(sdk))

    merge_builders(builder, page_builder)

    root_ids = [component.id for component in page_builder.get_roots() if component.id]
    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(root_ids)
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
