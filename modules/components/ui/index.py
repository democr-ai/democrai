from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from .demo_helpers import mount_preview
from .layout import shared_layout


_SECTIONS = [
    {
        "id": "layout",
        "title": "Layout",
        "text": "Components and application shell layouts",
        "icon": "ric.layout-2-fill",
        "route": "/components/_layout/header",
    },
    {
        "id": "content",
        "title": "Content",
        "text": "Components for content display",
        "icon": "ric.kanban-view",
        "route": "/components/_content/text",
    },
    {
        "id": "complex",
        "title": "Complex elements",
        "text": "Components with complex build",
        "icon": "ric.brackets-fill",
        "route": "/components/_complex/treeview",
    },
    {
        "id": "forms",
        "title": "Forms",
        "text": "Forms input and model management",
        "icon": "ric.input-field",
        "route": "/components/_forms/buttons",
    },
    {
        "id": "effects",
        "title": "Effects",
        "text": "Dynamic effects",
        "icon": "ric.brain-ai-3-fill",
        "route": "/components/_effects/toast",
    },
    {
        "id": "charts",
        "title": "Charts & Diagrams",
        "text": "Dynamic effects",
        "icon": "ric.bar-chart-fill",
        "route": "/components/_charts/base",
    },
    {
        "id": "ai",
        "title": "Ai",
        "text": "Components for ai integrations",
        "icon": "ric.ai",
        "route": "/components/_ai/input",
    },
    {
        "id": "flow",
        "title": "Flow & Effects",
        "text": "Docs for state and data management",
        "icon": "ric.flow-chart",
        "route": "/components/_flow/external_path",
    },
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/index"), components=True)
    builder.set_data("components_index/sections", _SECTIONS)
    mount_preview(builder, preview_id, "components_root")
    return builder
