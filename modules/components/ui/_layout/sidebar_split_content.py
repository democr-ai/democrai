from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/layout_shell_sidebar_split_content"), components=True)
    builder.merge(
        sdk.ui.load("ui/yaml/layout_sidebar_split_content_showcase"),
        components=True,
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_layout_sidebar_split_content_showcase_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
