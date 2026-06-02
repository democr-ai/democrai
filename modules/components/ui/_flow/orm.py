from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    builder.merge(sdk.ui.load("ui/yaml/flow_orm"), components=True)
    builder.set_data(
        "/components_flow/orm/api",
        [
            {"operation": "Base", "usage": sdk.i18n.t("components.flow.orm.api.base")},
            {"operation": "add(obj)", "usage": sdk.i18n.t("components.flow.orm.api.add")},
            {"operation": "get(model, id)", "usage": sdk.i18n.t("components.flow.orm.api.get")},
            {"operation": "list(model, **filters)", "usage": sdk.i18n.t("components.flow.orm.api.list")},
            {"operation": "update(model, id, **updates)", "usage": sdk.i18n.t("components.flow.orm.api.update")},
            {"operation": "delete(model, id)", "usage": sdk.i18n.t("components.flow.orm.api.delete")},
        ],
    )
    builder.set_data(
        "/components_flow/orm/boundaries",
        [
            {
                "rule": sdk.i18n.t("components.flow.orm.boundary.module_owned"),
                "reason": sdk.i18n.t("components.flow.orm.boundary.module_owned_reason"),
            },
            {
                "rule": sdk.i18n.t("components.flow.orm.boundary.scope"),
                "reason": sdk.i18n.t("components.flow.orm.boundary.scope_reason"),
            },
            {
                "rule": sdk.i18n.t("components.flow.orm.boundary.platform"),
                "reason": sdk.i18n.t("components.flow.orm.boundary.platform_reason"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_flow_orm_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
