from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk

from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.engine.list import (
    provider_catalog,
    section_sort_key,
    section_title,
)
from democrai.sdk.ui import merge_builders


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/models/engine_list")
    merge_builders(builder, page_builder)

    catalog = provider_catalog()

    tabs = builder.get_component("engine_provider_tabs")
    if tabs is not None:
        tab_defs = []
        for section_name in sorted(catalog.keys(), key=section_sort_key):
            safe_section = section_name.replace("-", "_")
            tab_defs.append(
                {
                    "id": f"engine_provider_{safe_section}_tab",
                    "label": section_title(sdk.i18n.t, section_name),
                    "route": f"/system/engine/domain/{section_name}",
                }
            )
        tabs.set_property("tabs", tab_defs)
        tabs.set_children([])

    root_component = builder.get_component("engine_list_page")
    if root_component is not None:
        root_component.set_children(
            [
                "engine_list_breadcrumb",
                "engine_list_header",
                "engine_provider_tabs",
            ]
        )

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["engine_list_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
