from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_page_state"), components=True)
    builder.set_data(
        "/components_flow/page_state/comparison",
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
        "/components_flow/page_state/api",
        [
            {
                "operation": "builder.set_store(..., scope=\"page\")",
                "usage": sdk.i18n.t("components.flow.page_state.api.seed"),
            },
            {
                "operation": "{type: store, scope: page, path: /key}",
                "usage": sdk.i18n.t("components.flow.page_state.api.yaml"),
            },
            {
                "operation": "bound.store(\"/key\", scope=\"page\")",
                "usage": sdk.i18n.t("components.flow.page_state.api.python"),
            },
            {
                "operation": "stateUpdate scope=page",
                "usage": sdk.i18n.t("components.flow.page_state.api.update"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_page_state_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
