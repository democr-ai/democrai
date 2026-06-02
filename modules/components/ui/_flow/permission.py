from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_permission"), components=True)
    builder.set_data(
        "/components_flow/permission/layers",
        [
            {"layer": "Page", "api": "@public", "usage": sdk.i18n.t("components.flow.permission.layer.page")},
            {"layer": "Action", "api": "@permission_required(...)", "usage": sdk.i18n.t("components.flow.permission.layer.action")},
            {"layer": "UI", "api": "show_if / hide_if / required_permissions", "usage": sdk.i18n.t("components.flow.permission.layer.ui")},
            {"layer": "External", "api": "sdk.access.*", "usage": sdk.i18n.t("components.flow.permission.layer.external")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_permission_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
