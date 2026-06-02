from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.ui import Component
from democrai.sdk.client import active_sdk as sdk


# TODO better management in renderer
class Workflow(Component):
    type = "Workflow"

    def __init__(
        self,
        id: str,
        *,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
        triggers: list[dict] | None = None,
        components: list[dict] | None = None,
        pipelines: list[dict] | None = None,
        piplines: list[dict] | None = None,
        component_catalog: list[dict] | None = None,
        toolbar_components: list[dict] | None = None,
        tools_components: list[dict] | None = None,
        selection_drawer_components: dict | None = None,
        title: str = "",
        height: int = 560,
        node_width: int = 214,
        node_height: int = 92,
    ):
        super().__init__(id)
        self.set_prop("nodes", list(nodes or []))
        self.set_prop("edges", list(edges or []))
        resolved_components = list(components or component_catalog or [])
        resolved_pipelines = list(pipelines or piplines or [])
        self.set_prop("triggers", list(triggers or []))
        self.set_prop("components", resolved_components)
        self.set_prop("pipelines", resolved_pipelines)
        self.set_prop("componentCatalog", resolved_components)
        self.set_prop("toolbarComponents", list(toolbar_components or []))
        self.set_prop("toolsComponents", list(tools_components or []))
        self.set_prop(
            "selectionDrawerComponents", dict(selection_drawer_components or {})
        )
        self.set_prop("height", max(240, int(height)))
        self.set_prop("nodeWidth", max(160, int(node_width)))
        self.set_prop("nodeHeight", max(72, int(node_height)))
        if title:
            self.set_prop("title", str(title))


@permission_required(["components.documentation.view"])
async def render(params: dict, session: dict) -> None:
    builder = sdk.ui.Builder()

    from ..layout import shared_layout

    _, preview_id = await shared_layout(builder)

    builder.add(
        sdk.ui.Text(
            "workflow_intro",
            "n8n-style preview with draggable nodes, live edge routing and a right-side property inspector.",
        )
    )
    builder.get_component("workflow_intro").set_property(
        "style", "font-size: 13px;"
    )

    nodes = [
        {
            "id": "webhook",
            "label": "Webhook Trigger",
            "nodeType": "trigger",
            "status": "ready",            "config": {"method": "POST", "path": "/tickets/new"},
            "outputs": [
                {"id": "payload", "label": "payload", "params": ["body", "headers"]}
            ],
        },
        {
            "id": "sanitize",
            "label": "Sanitize Input",
            "nodeType": "transform",
            "status": "running",            "config": {"fields": ["email", "subject", "priority"]},
            "input": {"params": ["body", "headers"]},
            "outputs": [
                {
                    "id": "normalized",
                    "label": "normalized",
                    "params": ["email", "subject", "priority"],
                }
            ],
        },
        {
            "id": "classifier",
            "label": "Priority Classifier",
            "nodeType": "ai",
            "status": "ready",            "config": {"model": "gpt-4.1-mini", "temperature": 0.2},
            "input": {"params": ["email", "subject", "priority"]},
            "outputs": [
                {
                    "id": "high",
                    "label": "high",
                    "params": ["ticket_id", "priority", "email"],
                },
                {
                    "id": "normal",
                    "label": "normal",
                    "params": ["ticket_id", "priority", "email"],
                },
            ],
            "allowAddOutput": True,
        },
        {
            "id": "approval",
            "label": "Manager Approval",
            "nodeType": "approval",
            "status": "waiting",            "config": {"requiredRole": "team_lead"},
            "input": {"params": ["ticket_id", "priority", "email"]},
            "outputs": [
                {
                    "id": "approved",
                    "label": "approved",
                    "params": ["ticket_id", "priority", "email"],
                }
            ],
        },
        {
            "id": "notify",
            "label": "Notify Slack",
            "nodeType": "action",
            "status": "ready",            "config": {"channel": "#incident-response"},
            "input": {"params": ["ticket_id", "priority", "email"]},
            "outputs": [
                {
                    "id": "notified",
                    "label": "notified",
                    "params": ["message_id", "ticket_id"],
                }
            ],
        },
        {
            "id": "store",
            "label": "Store in DB",
            "nodeType": "storage",
            "status": "ready",            "config": {"table": "ticket_workflows"},
            "input": {"params": ["message_id", "ticket_id"]},
            "outputs": [{"id": "saved", "label": "saved", "params": ["run_id"]}],
        },
    ]
    edges = [
        {
            "source": "webhook",
            "target": "sanitize",
            "sourceOutput": "payload",
            "mapping": {"body": "body", "headers": "headers"},
        },
        {
            "source": "sanitize",
            "target": "classifier",
            "sourceOutput": "normalized",
            "mapping": {"email": "email", "subject": "subject", "priority": "priority"},
        },
        {
            "source": "classifier",
            "target": "approval",
            "label": "high",
            "sourceOutput": "high",
            "mapping": {
                "ticket_id": "ticket_id",
                "priority": "priority",
                "email": "email",
            },
        },
        {
            "source": "classifier",
            "target": "notify",
            "label": "normal",
            "sourceOutput": "normal",
            "mapping": {
                "ticket_id": "ticket_id",
                "priority": "priority",
                "email": "email",
            },
        },
        {
            "source": "approval",
            "target": "notify",
            "label": "approved",
            "sourceOutput": "approved",
            "mapping": {
                "ticket_id": "ticket_id",
                "priority": "priority",
                "email": "email",
            },
        },
        {
            "source": "notify",
            "target": "store",
            "sourceOutput": "notified",
            "mapping": {"message_id": "message_id", "ticket_id": "ticket_id"},
        },
    ]
    triggers = [
        {
            "id": "webhook_trigger",
            "label": "Webhook Trigger",
            "nodeType": "trigger",            "input": {"params": []},
            "outputs": [
                {"id": "payload", "label": "payload", "params": ["body", "headers"]}
            ],
            "config": {"method": "POST", "path": "/workflow/inbound"},
            "allowAddOutput": False,
        }
    ]
    components = [
        {
            "id": "http_request",
            "label": "HTTP Request",
            "nodeType": "http",            "input": {"params": ["url", "method", "headers"]},
            "outputs": [
                {
                    "id": "response",
                    "label": "response",
                    "params": ["status", "body", "headers"],
                }
            ],
            "config": {"method": "GET", "timeoutMs": 8000},
            "allowAddOutput": False,
        },
        {
            "id": "json_transform",
            "label": "JSON Transform",
            "nodeType": "transform",            "input": {"params": ["payload"]},
            "outputs": [{"id": "result", "label": "result", "params": ["payload"]}],
            "config": {"expression": "$.items[*]"},
            "allowAddOutput": True,
        },
        {
            "id": "slack_message",
            "label": "Slack Message",
            "nodeType": "notify",            "input": {"params": ["channel", "text"]},
            "outputs": [{"id": "sent", "label": "sent", "params": ["message_id"]}],
            "config": {"channel": "#incident-response"},
            "allowAddOutput": False,
        },
        {
            "id": "evaluator",
            "label": "Evaluator",
            "nodeType": "evaluator",            "input": {"params": ["payload"]},
            "outputs": [{"id": "pass", "label": "pass", "params": ["payload"]}],
            "config": {"default_output": "pass"},
            "allowAddOutput": True,
        },
    ]
    pipelines = [
        {
            "id": "enrich_lead_pipeline",
            "label": "Pipeline: Enrich Lead",
            "nodeType": "pipeline",            "input": {"params": ["lead"]},
            "outputs": [
                {"id": "result", "label": "result", "params": ["lead", "score"]}
            ],
            "config": {"pipeline": "demo.enrich_lead"},
            "allowAddOutput": False,
        },
    ]
    toolbar_components = [
        sdk.ui.Text(
            "wf_toolbar_hint",
            "Single input + multi output per node, with edge parameter mapping",
        ).to_dict(),
        sdk.ui.Select(
            "wf_toolbar_component_picker",
            options=[
                {"label": "HTTP Request", "value": "http_request"},
                {"label": "JSON Transform", "value": "json_transform"},
                {"label": "Slack Message", "value": "slack_message"},
            ],
            value="json_transform",
            max_width=240,
        ).to_dict(),
        sdk.ui.Button(
            "wf_toolbar_add_component_btn",
            "Add Component",
            variant="default",
        ).to_dict(),
        sdk.ui.Button(
            "wf_toolbar_auto_layout_btn",
            "Auto Layout",
            variant="default",
        ).to_dict(),
        sdk.ui.Button(
            "wf_toolbar_fit_btn",
            "Fit",
            variant="default",
        ).to_dict(),
    ]
    tools_components = [
        sdk.ui.Alert(
            "wf_tools_alert",
            "Tooling",
            "Questa area e' renderizzata con componenti A2UI inline.",
            variant="info",
        ).to_dict(),
        sdk.ui.Button(
            "wf_tools_validate",
            "Validate flow",
            variant="secondary",
            action="components.demo_ui_event",
            params={"source": "workflow_tools", "intent": "validate"},
        ).to_dict(),
    ]
    builder.add(
        Workflow(
            "workflow_preview",
            title="Workflow Builder",
            nodes=nodes,
            edges=edges,
            triggers=triggers,
            components=components,
            pipelines=pipelines,
            toolbar_components=toolbar_components,
            tools_components=tools_components,
            height=640,
            node_width=220,
            node_height=96,
        )
    )
    builder.add(
        sdk.ui.Markdown(
            "workflow_code",
            """```python
from democrai.sdk.ui import Component

class Workflow(Component):
    type = "Workflow"

builder.add(
    Workflow(
        "workflow_preview",
        title="Workflow Builder",
        nodes=[
            {
                "id": "router",
                "label": "Router",
                "nodeType": "router",
                "input": {"params": ["email", "priority"]},
                "outputs": [
                    {"id": "high", "params": ["ticket_id", "priority"]},
                    {"id": "normal", "params": ["ticket_id", "priority"]},
                ],
                "allowAddOutput": True,
            }
        ],
        edges=[
            {
                "source": "router",
                "target": "notify",
                "sourceOutput": "high",
                "mapping": {"ticket_id": "ticket_id", "priority": "priority"},
            }
        ],
        triggers=[
            {"id": "webhook_trigger", "label": "Webhook Trigger", "nodeType": "trigger"},
        ],
        components=[
            {"id": "http_request", "label": "HTTP Request", "nodeType": "http"},
            {"id": "json_transform", "label": "JSON Transform", "nodeType": "transform"},
            {"id": "slack_message", "label": "Slack Message", "nodeType": "notify"},
            {"id": "evaluator", "label": "Evaluator", "nodeType": "evaluator"},
        ],
        pipelines=[
            {"id": "enrich_pipeline", "label": "Pipeline: Enrich", "nodeType": "pipeline"},
        ],
        toolbar_components=[
            sdk.ui.Button("wf_zoom", "Zoom to fit", variant="default").to_dict(),
        ],
        tools_components=[
            sdk.ui.Alert("wf_hint", "Hint", "Tool pane from A2UI.", variant="info").to_dict(),
        ],
        height=640,
    )
)
```""",
        )
    )

    root = sdk.ui.Column(
        "workflow_preview_root",
        ["workflow_intro", "workflow_preview", "workflow_code"],
    )
    root.set_property("stretch", True)
    root.set_property("align", "top")
    root.set_property("spacing", 18)
    root.set_property("padding", [20, 20, 20, 20])
    builder.add(root)

    preview_col = builder.get_component(preview_id)
    preview_col.set_children(["workflow_preview_root"])
    return builder
