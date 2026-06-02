from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_COMMITS = [
    {"id": "c1", "label": "a31f9e2  Init project scaffold", "branch": "main"},
    {"id": "c2", "label": "c9bbd51  Add auth guard", "branch": "main"},
    {"id": "c3", "label": "f8d77a0  Start feature/chat-stream", "branch": "feature/chat-stream"},
    {"id": "c4", "label": "98bbf4d  Improve composer UX", "branch": "feature/chat-stream"},
    {"id": "c5", "label": "a4e1f6b  Hotfix permission check", "branch": "main"},
    {"id": "c6", "label": "91dfe26  Merge feature/chat-stream", "branch": "main"},
    {"id": "c7", "label": "db1a002  Release v2.3.0", "branch": "release/2.3"},
    {"id": "c8", "label": "56c11f8  Patch telemetry tags", "branch": "release/2.3"},
    {"id": "c9", "label": "9ed10aa  Merge release into main", "branch": "main"},
]

_EDGES = [
    {"source": "c1", "target": "c2"},
    {"source": "c2", "target": "c3"},
    {"source": "c3", "target": "c4"},
    {"source": "c2", "target": "c5"},
    {"source": "c4", "target": "c6"},
    {"source": "c5", "target": "c6"},
    {"source": "c6", "target": "c7"},
    {"source": "c7", "target": "c8"},
    {"source": "c8", "target": "c9"},
    {"source": "c6", "target": "c9"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/git"), components=True)

    builder.set_store("/components_charts/git/title", "Page-store branch flow", scope="page")
    builder.set_store("/components_charts/git/commits", _COMMITS, scope="page")
    builder.set_store("/components_charts/git/edges", _EDGES, scope="page")
    builder.set_store("/components_charts/git/title", "Global-store branch flow", scope="global")
    builder.set_store("/components_charts/git/commits", _COMMITS, scope="global")
    builder.set_store("/components_charts/git/edges", _EDGES, scope="global")
    builder.set_data(
        "/components_charts/git_model",
        {
            "title": "Data-model branch flow",
            "commits": _COMMITS,
            "edges": _EDGES,
        },
    )
    builder.set_data(
        "/components_charts/git_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "commits: [...]\nedges: [...]",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_charts/git/commits}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_charts/git/commits}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_charts/git_model/commits",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_charts/git_properties",
        [
            {
                "property": "commits",
                "type": "list[object]",
                "usage": sdk.i18n.t("components.charts.git.property.commits"),
            },
            {
                "property": "edges",
                "type": "list[object]",
                "usage": sdk.i18n.t("components.charts.git.property.edges"),
            },
            {
                "property": "title",
                "type": "str",
                "usage": sdk.i18n.t("components.charts.git.property.title"),
            },
            {
                "property": "lane_width / row_height",
                "type": "int",
                "usage": sdk.i18n.t("components.charts.git.property.spacing"),
            },
            {
                "property": "show_labels / show_branch_names",
                "type": "bool",
                "usage": sdk.i18n.t("components.charts.git.property.flags"),
            },
            {
                "property": "action",
                "type": "ActionSpec",
                "usage": sdk.i18n.t("components.charts.git.property.action"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_charts_git_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
