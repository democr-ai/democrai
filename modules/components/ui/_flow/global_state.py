from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_global_state"), components=True)
    builder.set_data(
        "/components_flow/global_state/comparison",
        [
            {
                "topic": sdk.i18n.t("components.flow.state.table.scope"),
                "page": sdk.i18n.t("components.flow.page_state.table.scope"),
                "global": sdk.i18n.t("components.flow.global_state.table.scope"),
            },
            {
                "topic": sdk.i18n.t("components.flow.state.table.navigation"),
                "page": sdk.i18n.t("components.flow.page_state.table.navigation"),
                "global": sdk.i18n.t("components.flow.global_state.table.navigation"),
            },
            {
                "topic": sdk.i18n.t("components.flow.state.table.usage"),
                "page": sdk.i18n.t("components.flow.page_state.table.usage"),
                "global": sdk.i18n.t("components.flow.global_state.table.usage"),
            },
        ],
    )
    builder.set_data(
        "/components_flow/global_state/api",
        [
            {
                "operation": "builder.set_store(..., scope=\"global\")",
                "usage": sdk.i18n.t("components.flow.global_state.api.seed"),
            },
            {
                "operation": "{type: store, scope: global, path: /key}",
                "usage": sdk.i18n.t("components.flow.global_state.api.yaml"),
            },
            {
                "operation": "bound.store(\"/key\", scope=\"global\")",
                "usage": sdk.i18n.t("components.flow.global_state.api.python"),
            },
            {
                "operation": "stateUpdate scope=global",
                "usage": sdk.i18n.t("components.flow.global_state.api.update"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_global_state_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
