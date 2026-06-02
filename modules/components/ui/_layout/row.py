from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from .strategy_examples import collection_examples, static_examples, value_examples
from democrai.sdk.client import active_sdk as sdk


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/layout_row"), components=True)

    builder.set_store("/components_layout/row_spacing", 10, scope="page")
    builder.set_store("/components_layout/row_align", "left", scope="page")
    builder.set_store("/components_layout/row_align", "left", scope="global")
    builder.set_data("/components_layout/row_model/spacing", 14)
    builder.set_data("/components_layout/row_model/align", "left")
    builder.set_data(
        "/components_layout/row_properties",
        [
            {
                "property": "children",
                "type": "list[str | Component]",
                "page_store": sdk.i18n.t("components.layout.strategy.static_only"),
                "global_store": sdk.i18n.t("components.layout.strategy.static_only"),
                "data": sdk.i18n.t("components.layout.strategy.static_only"),
                "direct": 'ui_collection_append/remove("row_id", "children", item_dict)',
            },
            value_examples(
                sdk,
                component="row",
                prop="align",
                type_="string",
                value='"center"',
                direct=None,
            ),
            value_examples(
                sdk,
                component="row",
                prop="spacing",
                type_="int",
                value="24",
                direct='ui_property_update("row_id", "spacing", 24)',
            ),
            value_examples(
                sdk,
                component="row",
                prop="style",
                type_="string",
                value='"padding: 12px;"',
                direct='ui_property_update("row_id", "style", "padding: 12px;")',
            ),
            static_examples(sdk, prop="padding, width, height, stretch", type_="mixed"),
        ],
    )
    builder.set_data(
        "/components_layout/row_bindings",
        [
            {
                "binding": sdk.i18n.t("components.layout.binding.literal"),
                "yaml": "spacing: 8",
                "source": sdk.i18n.t("components.layout.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.store"),
                "yaml": "{type: store, scope: page, path: /components_layout/row_spacing}",
                "source": "builder.set_store(...)",
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.data"),
                "yaml": "@data/components_layout/row_model/spacing",
                "source": "builder.set_data(...)",
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_layout_row_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
