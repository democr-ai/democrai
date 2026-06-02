from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from .strategy_examples import collection_examples, static_examples, value_examples
from democrai.sdk.client import active_sdk as sdk


def _badge(component_id: str, text: str, variant: str) -> dict:
    return sdk.ui.Badge(component_id, text, variant=variant).to_dict()


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/layout_header"), components=True)

    builder.set_store(
        "/components_layout/header_right",
        [
            _badge(
                "components_layout_header_store_initial",
                sdk.i18n.t("components.layout.badge.idle"),
                "secondary",
            )
        ],
        scope="page",
    )
    for slot in ("left", "center", "right"):
        builder.set_store(
            f"/components_layout/header_{slot}",
            [
                _badge(
                    f"components_layout_header_page_initial_{slot}",
                    sdk.i18n.t(f"components.layout.header.slot_{slot}"),
                    "secondary",
                )
            ],
            scope="page",
        )
        builder.set_store(
            f"/components_layout/header_{slot}",
            [
                _badge(
                    f"components_layout_header_global_initial_{slot}",
                    sdk.i18n.t(f"components.layout.header.slot_{slot}"),
                    "secondary",
                )
            ],
            scope="global",
        )
    builder.set_data(
        "/components_layout/header_model/right",
        [
            _badge(
                "components_layout_header_data_initial",
                sdk.i18n.t("components.layout.badge.idle"),
                "secondary",
            )
        ],
    )
    for slot in ("left", "center", "right"):
        builder.set_data(
            f"/components_layout/header_model/{slot}",
            [
                _badge(
                    f"components_layout_header_data_initial_{slot}",
                    sdk.i18n.t(f"components.layout.header.slot_{slot}"),
                    "secondary",
                )
            ],
        )
    builder.set_data(
        "/components_layout/header_properties",
        [
            collection_examples(
                sdk, component="header", prop="left", type_="list[str | Component]"
            ),
            collection_examples(
                sdk, component="header", prop="center", type_="list[str | Component]"
            ),
            collection_examples(
                sdk, component="header", prop="right", type_="list[str | Component]"
            ),
            collection_examples(
                sdk, component="header", prop="children", type_="list[str | Component]"
            ),
            value_examples(
                sdk,
                component="header",
                prop="style",
                type_="string",
                value='"padding: 12px;"',
                direct='ui_property_update("header_id", "style", "padding: 12px;")',
            ),
            static_examples(sdk, prop="padding, spacing, stretch", type_="mixed"),
        ],
    )
    builder.set_data(
        "/components_layout/header_bindings",
        [
            {
                "binding": sdk.i18n.t("components.layout.binding.literal"),
                "yaml": "right: [header_status]",
                "source": sdk.i18n.t("components.layout.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.store"),
                "yaml": "{type: store, scope: page, path: /components_layout/header_right}",
                "source": "builder.set_store(...)",
            },
            {
                "binding": sdk.i18n.t("components.layout.binding.data"),
                "yaml": "@data/components_layout/header_model/right",
                "source": "builder.set_data(...)",
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_layout_header_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
