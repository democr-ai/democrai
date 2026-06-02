from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_hooks"), components=True)
    builder.set_data(
        "/components_flow/hooks/concepts",
        [
            {
                "concept": "render_hook_slot",
                "api": "@sdk.render_hook_slot(...)",
                "usage": sdk.i18n.t("components.flow.hooks.concept.slot"),
            },
            {
                "concept": "render_hook",
                "api": "@sdk.render_hook(...)",
                "usage": sdk.i18n.t("components.flow.hooks.concept.provider"),
            },
            {
                "concept": "resolve",
                "api": "await sdk.hooks.resolve_render_hook(...)",
                "usage": sdk.i18n.t("components.flow.hooks.concept.resolve"),
            },
        ],
    )
    builder.set_data(
        "/components_flow/hooks/api",
        [
            {
                "operation": "sdk.hooks.qualify_render_hook_name(name)",
                "usage": sdk.i18n.t("components.flow.hooks.api.qualify"),
            },
            {
                "operation": "sdk.hooks.get_render_hook_slots(module_name=None)",
                "usage": sdk.i18n.t("components.flow.hooks.api.slots"),
            },
            {
                "operation": "sdk.hooks.resolve_render_hook(name, params=..., session=...)",
                "usage": sdk.i18n.t("components.flow.hooks.api.resolve"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_hooks_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
