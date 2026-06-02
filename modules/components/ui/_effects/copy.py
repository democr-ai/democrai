from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/effect_copy"), components=True)

    preview = builder.get_component(preview_id)
    preview.set_children(["components_effect_copy_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
