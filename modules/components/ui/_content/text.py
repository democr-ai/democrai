from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    content = sdk.ui.load("ui/yaml/content_text")
    builder.merge(content, components=True)
    builder.set_data(
        "/components_typography/data_title",
        sdk.i18n.t("components.typography.binding.data_title"),
    )
    builder.set_data(
        "/components_typography/data_text",
        sdk.i18n.t("components.typography.binding.data_text"),
    )
    builder.set_data(
        "/components_typography/data_markdown",
        sdk.i18n.t("components.typography.binding.data_markdown"),
    )
    builder.set_store(
        "/components_typography/store_title",
        sdk.i18n.t("components.typography.binding.store_title"),
        scope="page",
    )
    builder.set_store(
        "/components_typography/store_text",
        sdk.i18n.t("components.typography.binding.store_text"),
        scope="page",
    )
    builder.set_data(
        "/components_typography/binding_rows",
        [
            {
                "binding": sdk.i18n.t("components.typography.binding.literal.name"),
                "yaml": sdk.i18n.t("components.typography.binding.literal.yaml"),
                "source": sdk.i18n.t("components.typography.binding.literal.source"),
            },
            {
                "binding": sdk.i18n.t("components.typography.binding.store.name"),
                "yaml": sdk.i18n.t("components.typography.binding.store.yaml"),
                "source": sdk.i18n.t("components.typography.binding.store.source"),
            },
            {
                "binding": sdk.i18n.t("components.typography.binding.data.name"),
                "yaml": sdk.i18n.t("components.typography.binding.data.yaml"),
                "source": sdk.i18n.t("components.typography.binding.data.source"),
            },
            {
                "binding": sdk.i18n.t("components.typography.binding.explicit.name"),
                "yaml": sdk.i18n.t("components.typography.binding.explicit.yaml"),
                "source": sdk.i18n.t("components.typography.binding.explicit.source"),
            },
        ],
    )
    builder.set_data(
        "/components_typography/properties_rows",
        [
            {
                "component": "Title",
                "properties": "text, level, align, style, show_if, hide_if, required_permissions",
                "bindings": sdk.i18n.t("components.typography.properties.title_bindings"),
            },
            {
                "component": "Text",
                "properties": "text, align, selectable, muted, tone, style, show_if, hide_if, required_permissions",
                "bindings": sdk.i18n.t("components.typography.properties.text_bindings"),
            },
            {
                "component": "Markdown",
                "properties": "text, style, content_style, show_if, hide_if, required_permissions",
                "bindings": sdk.i18n.t("components.typography.properties.markdown_bindings"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_typography_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
