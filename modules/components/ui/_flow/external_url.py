from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_external_url"), components=True)
    builder.set_data(
        "/components_flow/external_url/api",
        [
            {"operation": "check_external_access(...)", "usage": sdk.i18n.t("components.flow.external.api.check")},
            {"operation": "require_external_access(...)", "usage": sdk.i18n.t("components.flow.external.api.require")},
            {"operation": "approve_for_session(...)", "usage": sdk.i18n.t("components.flow.external.api.session")},
            {"operation": "approve_permanently(...)", "usage": sdk.i18n.t("components.flow.external.api.permanent")},
            {"operation": "deny_external_access(...)", "usage": sdk.i18n.t("components.flow.external.api.deny")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_external_url_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
