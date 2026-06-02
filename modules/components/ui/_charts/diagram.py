from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk

from ..layout import shared_layout


_PARTICIPANTS = [
    {"id": "client", "label": "Client"},
    {"id": "gateway", "label": "API Gateway"},
    {"id": "orchestrator", "label": "Orchestrator"},
    {"id": "knowledge", "label": "Knowledge Service"},
    {"id": "llm", "label": "Model Provider"},
]

_MESSAGES = [
    {"from": "client", "to": "gateway", "text": "POST /chat", "type": "sync"},
    {"from": "gateway", "to": "orchestrator", "text": "dispatch(request)", "type": "sync"},
    {"from": "orchestrator", "to": "knowledge", "text": "retrieve_context()", "type": "sync"},
    {"from": "knowledge", "to": "orchestrator", "text": "context_bundle", "type": "reply"},
    {"from": "orchestrator", "to": "llm", "text": "generate(messages+context)", "type": "sync"},
    {"from": "llm", "to": "orchestrator", "text": "completion", "type": "reply"},
    {"from": "orchestrator", "to": "gateway", "text": "surface_update", "type": "reply"},
    {"from": "gateway", "to": "client", "text": "200 + payload", "type": "reply"},
]


@permission_required(["components.documentation.view"])
async def render(_params: dict, _session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    builder.merge(sdk.ui.load("ui/yaml/sequence"), components=True)

    builder.set_store("/components_charts/sequence/title", "Page-store lifecycle", scope="page")
    builder.set_store("/components_charts/sequence/participants", _PARTICIPANTS, scope="page")
    builder.set_store("/components_charts/sequence/messages", _MESSAGES, scope="page")
    builder.set_store("/components_charts/sequence/title", "Global-store lifecycle", scope="global")
    builder.set_store("/components_charts/sequence/participants", _PARTICIPANTS, scope="global")
    builder.set_store("/components_charts/sequence/messages", _MESSAGES, scope="global")
    builder.set_data(
        "/components_charts/sequence_model",
        {
            "title": "Data-model lifecycle",
            "participants": _PARTICIPANTS,
            "messages": _MESSAGES,
        },
    )
    builder.set_data(
        "/components_charts/sequence_bindings",
        [
            {
                "binding": "Literal",
                "yaml": "participants: [...]\nmessages: [...]",
                "source": "YAML or Python constructor",
            },
            {
                "binding": "Page store",
                "yaml": "{type: store, scope: page, path: /components_charts/sequence/messages}",
                "source": 'builder.set_store(..., scope="page")',
            },
            {
                "binding": "Global store",
                "yaml": "{type: store, scope: global, path: /components_charts/sequence/messages}",
                "source": 'builder.set_store(..., scope="global")',
            },
            {
                "binding": "Data model",
                "yaml": "@data/components_charts/sequence_model/messages",
                "source": "builder.set_data(...)",
            },
        ],
    )
    builder.set_data(
        "/components_charts/sequence_properties",
        [
            {
                "property": "participants",
                "type": "list[object]",
                "usage": sdk.i18n.t("components.charts.sequence.property.participants"),
            },
            {
                "property": "messages",
                "type": "list[object]",
                "usage": sdk.i18n.t("components.charts.sequence.property.messages"),
            },
            {
                "property": "mermaid",
                "type": "str",
                "usage": sdk.i18n.t("components.charts.sequence.property.mermaid"),
            },
            {
                "property": "title",
                "type": "str",
                "usage": sdk.i18n.t("components.charts.sequence.property.title"),
            },
            {
                "property": "height",
                "type": "int",
                "usage": sdk.i18n.t("components.charts.sequence.property.height"),
            },
        ],
    )

    preview = builder.get_component(preview_id)
    preview.set_children(["components_charts_sequence_root"])
    preview.set_property("padding", [28, 28, 28, 28])
    preview.set_property("spacing", 22)
    return builder
