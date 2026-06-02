from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_client_runtime"), components=True)
    builder.set_store(
        "/components_flow/client_runtime/store_label",
        sdk.i18n.t("components.flow.client_runtime.seed.store"),
        scope="page",
    )
    builder.set_store(
        "/components_flow/client_runtime/result",
        sdk.i18n.t("components.flow.client_runtime.seed.result"),
        scope="page",
    )
    builder.set_data(
        "/components_flow/client_runtime/data_label",
        sdk.i18n.t("components.flow.client_runtime.seed.data"),
    )
    builder.set_data(
        "/components_flow/client_runtime/method_rows",
        [
            {
                "method": "ask_current_store_value",
                "target": sdk.i18n.t("components.flow.client_runtime.methods.store.target"),
                "returns": sdk.i18n.t("components.flow.client_runtime.methods.store.returns"),
            },
            {
                "method": "ask_current_data_value",
                "target": sdk.i18n.t("components.flow.client_runtime.methods.data.target"),
                "returns": sdk.i18n.t("components.flow.client_runtime.methods.data.returns"),
            },
            {
                "method": "ask_current_component_props",
                "target": sdk.i18n.t("components.flow.client_runtime.methods.props.target"),
                "returns": sdk.i18n.t("components.flow.client_runtime.methods.props.returns"),
            },
            {
                "method": "ask_current_surface_tree",
                "target": sdk.i18n.t("components.flow.client_runtime.methods.tree.target"),
                "returns": sdk.i18n.t("components.flow.client_runtime.methods.tree.returns"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_client_runtime_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
