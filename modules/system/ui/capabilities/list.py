from __future__ import annotations

from urllib.parse import quote

from democrai.sdk.client import active_sdk as sdk

from modules.system.utils.actions.capabilities.index import (
    list_capabilities,
)
from modules.system.ui.layout import shared_layout
from modules.system.utils.ui.capabilities.list import (
    capability_icon,
    capability_label,
    pane_id_for_capability,
)
from democrai.sdk.ui import merge_builders


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/capabilities/list")
    merge_builders(builder, page_builder)

    capabilities = list_capabilities(sdk)
    tab_defs: list[dict] = []

    for capability in capabilities:
        pane_id = pane_id_for_capability(capability)
        tab_defs.append(
            {
                "id": pane_id,
                "label": capability_label(sdk, capability),
                "icon": capability_icon(capability),
                "route": f"/system/capabilities/{quote(capability, safe='')}/models",
            }
        )

    tabs_component = builder.get_component("capabilities_tabs")
    if tabs_component is not None:
        tabs_component.set_children([])
        tabs_component.set_property("tabs", tab_defs)

    empty_component = builder.get_component("capabilities_empty")
    if empty_component is not None:
        empty_component.set_property("visible", len(capabilities) == 0)
    if tabs_component is not None:
        tabs_component.set_property("visible", len(capabilities) > 0)

    root_ids = [component.id for component in page_builder.get_roots() if component.id]
    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(root_ids)
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
