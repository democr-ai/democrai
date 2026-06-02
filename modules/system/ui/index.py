from .layout import shared_layout

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import merge_builders


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    content = sdk.ui.load("utils/ui/yaml/index")
    merge_builders(builder, content)

    preview = builder.get_component(preview_id)
    preview.set_children(
        [component.id for component in content.get_roots() if component.id]
    )
    preview.set_property("stretch", True)

    return builder
