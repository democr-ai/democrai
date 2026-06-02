from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/effect_yaml"), components=True)
    builder.set_store("/components_effects/yaml/local_counter", 0, scope="page")
    builder.set_store("/components_effects/yaml/global_counter", 0, scope="global")

    preview = builder.get_component(preview_id)
    preview.set_children(["components_effect_yaml_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
