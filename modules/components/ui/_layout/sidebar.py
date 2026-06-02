from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from .strategy_examples import static_examples, value_examples
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/layout_sidebar"), components=True)

    initial_width = 220
    builder.set_store("/components_layout/sidebar_width", initial_width, scope="page")
    builder.set_store("/components_layout/sidebar_width", initial_width, scope="global")
    builder.set_data("/components_layout/sidebar_model/width", initial_width)
    builder.set_data(
        "/components_layout/sidebar_properties",
        [
            {
                "property": "children",
                "type": "list[str | Component]",
                "page_store": sdk.i18n.t("components.layout.strategy.static_only"),
                "global_store": sdk.i18n.t("components.layout.strategy.static_only"),
                "data": sdk.i18n.t("components.layout.strategy.static_only"),
                "direct": 'ui_collection_append/remove("inner_column_id", "children", item_dict)',
            },
            value_examples(
                sdk,
                component="sidebar",
                prop="width",
                type_="int | string",
                value="280",
                direct='ui_property_update("sidebar_id", "width", 280)',
            ),
            value_examples(
                sdk,
                component="sidebar",
                prop="max_width",
                type_="int | string",
                value="280",
                direct='ui_property_update("sidebar_id", "max_width", 280)',
            ),
            static_examples(sdk, prop="style", type_="string"),
            static_examples(sdk, prop="padding, align", type_="mixed"),
        ],
    )
    builder.set_data(
        "/components_layout/sidebar_bindings",
        [
            {
                "binding": sdk.i18n.t("components.layout.binding.literal"),
                "yaml": "width: 220",
                "source": sdk.i18n.t("components.layout.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.store"),
                "yaml": "{type: store, scope: page, path: /components_layout/sidebar_width}",
                "source": "builder.set_store(...)",
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.data"),
                "yaml": "@data/components_layout/sidebar_model/width",
                "source": "builder.set_data(...)",
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_layout_sidebar_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
