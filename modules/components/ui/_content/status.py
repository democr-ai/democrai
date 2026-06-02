from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


def _status_seed(title: str, description: str, variant: str, badge_text: str, badge_variant: str) -> dict:
    return {
        "title": title,
        "description": description,
        "variant": variant,
        "badge_text": badge_text,
        "badge_variant": badge_variant,
    }


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/status"), components=True)

    page = _status_seed(
        "Store-bound status",
        "Status follows page store.",
        "info",
        "Store badge",
        "default",
    )
    global_state = _status_seed(
        "Global status",
        "Status follows global store.",
        "warning",
        "Global badge",
        "warning",
    )
    data = _status_seed(
        "Data-model status",
        "Status follows the surface data model.",
        "success",
        "Data badge",
        "success",
    )
    for key, value in page.items():
        builder.set_store(f"/components_content/status/{key}", value, scope="page")
    for key, value in global_state.items():
        builder.set_store(f"/components_content/status/{key}", value, scope="global")
    builder.set_data("/components_content/status_model", data)
    builder.set_data(
        "/components_content/status_bindings",
        [
            {
                "binding": sdk.i18n.t("components.content.binding.literal"),
                "yaml": 'text: "Static badge"',
                "source": sdk.i18n.t("components.content.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.content.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_content/status/title}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("components.content.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_content/status/title}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("components.content.binding.data"),
                "yaml": "@data/components_content/status_model/title",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_content/status_properties",
        [
            {
                "component": "Badge",
                "property": "text",
                "usage": sdk.i18n.t("components.content.status.property.badge_text"),
            },
            {
                "component": "Badge",
                "property": "variant",
                "usage": sdk.i18n.t("components.content.status.property.badge_variant"),
            },
            {
                "component": "Alert",
                "property": "title",
                "usage": sdk.i18n.t("components.content.status.property.alert_title"),
            },
            {
                "component": "Alert",
                "property": "description",
                "usage": sdk.i18n.t("components.content.status.property.alert_description"),
            },
            {
                "component": "Alert",
                "property": "variant",
                "usage": sdk.i18n.t("components.content.status.property.alert_variant"),
            },
            {
                "component": "Badge / Alert",
                "property": "style, show_if, hide_if, required_permissions",
                "usage": sdk.i18n.t("components.content.property.common"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_status_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
