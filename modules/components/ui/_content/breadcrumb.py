from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_SEGMENTS = [
    {"label": "Components", "path": "/components/index"},
    {"label": "Content", "path": "/components/_content/text"},
    {"label": "Breadcrumb", "current": True},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/breadcrumb"), components=True)

    builder.set_store("/components_content/breadcrumb/segments", _SEGMENTS, scope="page")
    builder.set_store("/components_content/breadcrumb/segments", _SEGMENTS, scope="global")
    builder.set_data("/components_content/breadcrumb_model", {"segments": _SEGMENTS})
    builder.set_data(
        "/components_content/breadcrumb_bindings",
        [
            {
                "binding": sdk.i18n.t("content.binding.literal"),
                "yaml": "segments:\n  - label: Components",
                "source": sdk.i18n.t("content.binding.constructor"),
            },
            {
                "binding": sdk.i18n.t("content.binding.page_store"),
                "yaml": "{type: store, scope: page, path: /components_content/breadcrumb/segments}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": sdk.i18n.t("content.binding.global_store"),
                "yaml": "{type: store, scope: global, path: /components_content/breadcrumb/segments}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": sdk.i18n.t("content.binding.data"),
                "yaml": "@data/components_content/breadcrumb_model/segments",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_content/breadcrumb_properties",
        [
            {
                "property": "segments",
                "type": "list[dict]",
                "usage": sdk.i18n.t("content.breadcrumb.property.segments"),
            },
            {
                "property": "separator",
                "type": "str",
                "usage": sdk.i18n.t("content.breadcrumb.property.separator"),
            },
            {
                "property": "style",
                "type": "str",
                "usage": sdk.i18n.t("content.property.common"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_breadcrumb_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
