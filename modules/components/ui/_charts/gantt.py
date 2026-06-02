from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_ITEMS = [
    {
        "id": "plan",
        "label": "Planning and alignment",
        "group": "foundation",
        "start": "2026-04-01",
        "end": "2026-04-05",
        "status": "done",
        "progress": 100,
        "expanded": True,
        "subtasks": [
            {
                "id": "scope",
                "label": "Scope definition",
                "group": "foundation",
                "start": "2026-04-01",
                "end": "2026-04-02",
                "status": "done",
                "progress": 100,
            },
            {
                "id": "dependencies",
                "label": "Dependency mapping",
                "group": "foundation",
                "start": "2026-04-03",
                "end": "2026-04-05",
                "status": "done",
                "progress": 100,
            },
        ],
    },
    {
        "id": "api",
        "label": "Backend contract",
        "group": "delivery",
        "start": "2026-04-06",
        "end": "2026-04-11",
        "status": "done",
        "progress": 100,
    },
    {
        "id": "desktop",
        "label": "Desktop renderer",
        "group": "delivery",
        "start": "2026-04-09",
        "end": "2026-04-16",
        "status": "active",
        "progress": 65,
    },
    {
        "id": "web",
        "label": "Web renderer",
        "group": "delivery",
        "start": "2026-04-10",
        "end": "2026-04-18",
        "status": "active",
        "progress": 45,
    },
    {
        "id": "docs",
        "label": "Documentation and examples",
        "group": "enablement",
        "start": "2026-04-17",
        "end": "2026-04-22",
        "status": "planned",
        "progress": 0,
    },
    {
        "id": "launch",
        "label": "Production release",
        "group": "release",
        "start": "2026-04-23",
        "end": "2026-04-25",
        "status": "risk",
        "progress": 10,
    },
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/gantt"), components=True)

    builder.set_store("/components_charts/gantt/title", "Page-store delivery plan", scope="page")
    builder.set_store("/components_charts/gantt/items", _ITEMS, scope="page")
    builder.set_store("/components_charts/gantt/start", "2026-04-01", scope="page")
    builder.set_store("/components_charts/gantt/end", "2026-04-25", scope="page")
    builder.set_store("/components_charts/gantt/title", "Global-store delivery plan", scope="global")
    builder.set_store("/components_charts/gantt/items", _ITEMS, scope="global")
    builder.set_store("/components_charts/gantt/start", "2026-04-01", scope="global")
    builder.set_store("/components_charts/gantt/end", "2026-04-25", scope="global")
    builder.set_data(
        "/components_charts/gantt_model",
        {
            "title": "Data-model delivery plan",
            "items": _ITEMS,
            "start": "2026-04-01",
            "end": "2026-04-25",
        },
    )
    builder.set_data(
        "/components_charts/gantt_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "items: [...]\nstart: \"2026-04-01\"",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_charts/gantt/items}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_charts/gantt/items}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_charts/gantt_model/items",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_charts/gantt_properties",
        [
            {
                "property": "items",
                "type": "list[object]",
                "usage": sdk.i18n.t("components.charts.gantt.property.items"),
            },
            {
                "property": "mermaid",
                "type": "str",
                "usage": sdk.i18n.t("components.charts.gantt.property.mermaid"),
            },
            {
                "property": "title",
                "type": "str",
                "usage": sdk.i18n.t("components.charts.gantt.property.title"),
            },
            {
                "property": "start / end",
                "type": "str",
                "usage": sdk.i18n.t("components.charts.gantt.property.range"),
            },
            {
                "property": "height",
                "type": "int",
                "usage": sdk.i18n.t("components.charts.gantt.property.height"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_charts_gantt_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
