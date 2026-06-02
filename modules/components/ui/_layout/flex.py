from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from .strategy_examples import static_examples, value_examples
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/layout_flex"), components=True)

    initial_style = "padding: 10px; border: 1px solid #d0d7de; border-radius: 6px;"
    builder.set_store("/components_layout/flex_style", initial_style, scope="page")
    builder.set_store("/components_layout/flex_style", initial_style, scope="global")
    builder.set_data("/components_layout/flex_model/style", initial_style)
    builder.set_data(
        "/components_layout/flex_properties",
        [
            {
                "property": "children",
                "type": "list[str | Component]",
                "page_store": sdk.i18n.t("components.layout.strategy.static_only"),
                "global_store": sdk.i18n.t("components.layout.strategy.static_only"),
                "data": sdk.i18n.t("components.layout.strategy.static_only"),
                "direct": 'ui_collection_append/remove("flex_id", "children", item_dict)',
            },
            value_examples(
                sdk,
                component="flex",
                prop="style",
                type_="str | dict",
                value='"padding: 12px;"',
                direct='ui_property_update("flex_id", "style", "padding: 12px;")',
            ),
            value_examples(
                sdk,
                component="flex",
                prop="visible",
                type_="bool",
                value="False",
                direct='ui_property_update("flex_id", "visible", False)',
            ),
            static_examples(sdk, prop="show_if, hide_if, required_permissions", type_="rule"),
        ],
    )
    builder.set_data(
        "/components_layout/flex_bindings",
        [
            {
                "binding": sdk.i18n.t("components.layout.binding.literal"),
                "yaml": 'style: "padding: 10px;"',
                "source": sdk.i18n.t("components.layout.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.store"),
                "yaml": "{type: store, scope: page, path: /components_layout/flex_style}",
                "source": "builder.set_store(...)",
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.data"),
                "yaml": "@data/components_layout/flex_model/style",
                "source": "builder.set_data(...)",
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_layout_flex_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
