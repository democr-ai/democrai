from democrai.sdk.auth import permission_required
from ..layout import shared_layout
from democrai.sdk.client import active_sdk as sdk


_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_PAGE_SERIES = [10, 45, 20, 80, 50, 90, 60]
_GLOBAL_SERIES = [24, 30, 42, 38, 55, 72, 68]
_DATA_SERIES = [18, 28, 46, 52, 44, 70, 86]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/chart_base"), components=True)

    builder.set_store("/components_charts/base/chart_type", "bar", scope="page")
    builder.set_store("/components_charts/base/data", _PAGE_SERIES, scope="page")
    builder.set_store("/components_charts/base/labels", _LABELS, scope="page")
    builder.set_store("/components_charts/base/title", "Page-store chart", scope="page")
    builder.set_store("/components_charts/base/chart_type", "line", scope="global")
    builder.set_store("/components_charts/base/data", _GLOBAL_SERIES, scope="global")
    builder.set_store("/components_charts/base/labels", _LABELS, scope="global")
    builder.set_store("/components_charts/base/title", "Global-store chart", scope="global")
    builder.set_store("/components_charts/base/gpu/data", [], scope="page")
    builder.set_store("/components_charts/base/gpu/labels", [], scope="page")
    builder.set_data(
        "/components_charts/base_model",
        {
            "chart_type": "area",
            "data": _DATA_SERIES,
            "labels": _LABELS,
            "title": "Data-model chart",
        },
    )
    builder.set_data(
        "/components_charts/base_bindings",
        [
            {"binding": "Literal", "yaml": "data: [10, 45, 20, 80]", "source": "YAML or Python constructor"},
            {"binding": "Page store", "yaml": "{type: store, scope: page, path: /components_charts/base/data}", "source": 'builder.set_store(..., scope="page")'},
            {"binding": "Global store", "yaml": "{type: store, scope: global, path: /components_charts/base/data}", "source": 'builder.set_store(..., scope="global")'},
            {"binding": "Data model", "yaml": "@data/components_charts/base_model/data", "source": "builder.set_data(...)"},
        ],
    )
    builder.set_data(
        "/components_charts/base_properties",
        [
            {"property": "chart_type / chartType", "type": "str", "usage": sdk.i18n.t("components.charts.base.property.chart_type")},
            {"property": "data", "type": "list[number]", "usage": sdk.i18n.t("components.charts.base.property.data")},
            {"property": "labels", "type": "list[str]", "usage": sdk.i18n.t("components.charts.base.property.labels")},
            {"property": "title", "type": "str", "usage": sdk.i18n.t("components.charts.base.property.title")},
            {"property": "max_height, max_width", "type": "int", "usage": sdk.i18n.t("components.charts.base.property.size")},
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_charts_base_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
