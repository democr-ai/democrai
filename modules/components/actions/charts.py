from __future__ import annotations

from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action


def _state_update(sdk, scope: str, values: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages([{"stateUpdate": {"scope": scope, "values": values}}])
    )


def _data_update(sdk, surface_id: str, data: dict) -> dict:
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [sdk.ui.Builder.build_data_model_update_payload(surface_id=surface_id, data=data)]
        )
    )


_UPDATED_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_UPDATED_SERIES = [30, 24, 58, 46, 76, 62, 94]
_SEQUENCE_PARTICIPANTS = [
    {"id": "client", "label": "Client"},
    {"id": "gateway", "label": "API Gateway"},
    {"id": "orchestrator", "label": "Orchestrator"},
    {"id": "policy", "label": "Policy Engine"},
    {"id": "llm", "label": "Model Provider"},
]
_SEQUENCE_MESSAGES = [
    {"from": "client", "to": "gateway", "text": "POST /agent/run", "type": "sync"},
    {"from": "gateway", "to": "policy", "text": "authorize(action)", "type": "sync"},
    {"from": "policy", "to": "gateway", "text": "allowed", "type": "reply"},
    {"from": "gateway", "to": "orchestrator", "text": "dispatch(run)", "type": "sync"},
    {"from": "orchestrator", "to": "llm", "text": "generate(plan)", "type": "sync"},
    {"from": "llm", "to": "orchestrator", "text": "tool plan", "type": "reply"},
    {"from": "orchestrator", "to": "gateway", "text": "ui patch", "type": "reply"},
    {"from": "gateway", "to": "client", "text": "stream update", "type": "reply"},
]
_GANTT_ITEMS = [
    {
        "id": "foundation",
        "label": "Foundation hardening",
        "group": "foundation",
        "start": "2026-05-01",
        "end": "2026-05-06",
        "status": "done",
        "progress": 100,
        "expanded": True,
        "subtasks": [
            {
                "id": "boundary",
                "label": "Boundary review",
                "group": "foundation",
                "start": "2026-05-01",
                "end": "2026-05-03",
                "status": "done",
                "progress": 100,
            },
            {
                "id": "docs",
                "label": "Documentation sync",
                "group": "foundation",
                "start": "2026-05-04",
                "end": "2026-05-06",
                "status": "done",
                "progress": 100,
            },
        ],
    },
    {
        "id": "client",
        "label": "Client parity",
        "group": "delivery",
        "start": "2026-05-07",
        "end": "2026-05-14",
        "status": "active",
        "progress": 55,
    },
    {
        "id": "security",
        "label": "Security backlog",
        "group": "delivery",
        "start": "2026-05-12",
        "end": "2026-05-20",
        "status": "risk",
        "progress": 25,
    },
    {
        "id": "release",
        "label": "Release validation",
        "group": "release",
        "start": "2026-05-21",
        "end": "2026-05-25",
        "status": "planned",
        "progress": 0,
    },
]
_GIT_COMMITS = [
    {"id": "g1", "label": "41bd86a  Initialize workspace", "branch": "main"},
    {"id": "g2", "label": "62aa0c1  Add module boundary checks", "branch": "main"},
    {"id": "g3", "label": "7d13b8e  Start chart publisher", "branch": "feature/chart-publisher"},
    {"id": "g4", "label": "3e9f4b2  Stream metric samples", "branch": "feature/chart-publisher"},
    {"id": "g5", "label": "d0c6617  Patch permission prompt", "branch": "main"},
    {"id": "g6", "label": "8af530e  Merge chart publisher", "branch": "main"},
    {"id": "g7", "label": "bf4021a  Prepare release branch", "branch": "release/2.4"},
]
_GIT_EDGES = [
    {"source": "g1", "target": "g2"},
    {"source": "g2", "target": "g3"},
    {"source": "g3", "target": "g4"},
    {"source": "g2", "target": "g5"},
    {"source": "g4", "target": "g6"},
    {"source": "g5", "target": "g6"},
    {"source": "g6", "target": "g7"},
]


@action("chart_base_update")
@permission_required(["components.documentation.view"])
async def chart_base_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_charts/base/chart_type": "area",
                "/components_charts/base/data": _UPDATED_SERIES,
                "/components_charts/base/labels": _UPDATED_LABELS,
                "/components_charts/base/title": "Updated page-store chart",
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_charts/base/chart_type": "bar",
                "/components_charts/base/data": _UPDATED_SERIES,
                "/components_charts/base/labels": _UPDATED_LABELS,
                "/components_charts/base/title": "Updated global-store chart",
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_charts": {
                    "base_model": {
                        "chart_type": "line",
                        "data": _UPDATED_SERIES,
                        "labels": _UPDATED_LABELS,
                        "title": "Updated data-model chart",
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_charts_base_direct",
                "chartType",
                "area",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_base_direct",
                "data",
                _UPDATED_SERIES,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_base_direct",
                "labels",
                _UPDATED_LABELS,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_base_direct",
                "title",
                "Updated direct chart",
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()


@action("sequence_diagram_update")
@permission_required(["components.documentation.view"])
async def sequence_diagram_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_charts/sequence/title": "Updated page-store lifecycle",
                "/components_charts/sequence/participants": _SEQUENCE_PARTICIPANTS,
                "/components_charts/sequence/messages": _SEQUENCE_MESSAGES,
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_charts/sequence/title": "Updated global-store lifecycle",
                "/components_charts/sequence/participants": _SEQUENCE_PARTICIPANTS,
                "/components_charts/sequence/messages": _SEQUENCE_MESSAGES,
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_charts": {
                    "sequence_model": {
                        "title": "Updated data-model lifecycle",
                        "participants": _SEQUENCE_PARTICIPANTS,
                        "messages": _SEQUENCE_MESSAGES,
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_charts_sequence_direct",
                "title",
                "Updated direct lifecycle",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_sequence_direct",
                "participants",
                _SEQUENCE_PARTICIPANTS,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_sequence_direct",
                "messages",
                _SEQUENCE_MESSAGES,
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()


@action("gantt_update")
@permission_required(["components.documentation.view"])
async def gantt_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_charts/gantt/title": "Updated page-store plan",
                "/components_charts/gantt/items": _GANTT_ITEMS,
                "/components_charts/gantt/start": "2026-05-01",
                "/components_charts/gantt/end": "2026-05-25",
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_charts/gantt/title": "Updated global-store plan",
                "/components_charts/gantt/items": _GANTT_ITEMS,
                "/components_charts/gantt/start": "2026-05-01",
                "/components_charts/gantt/end": "2026-05-25",
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_charts": {
                    "gantt_model": {
                        "title": "Updated data-model plan",
                        "items": _GANTT_ITEMS,
                        "start": "2026-05-01",
                        "end": "2026-05-25",
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_charts_gantt_direct",
                "title",
                "Updated direct plan",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_gantt_direct",
                "items",
                _GANTT_ITEMS,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_gantt_direct",
                "start",
                "2026-05-01",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_gantt_direct",
                "end",
                "2026-05-25",
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()


@action("git_graph_update")
@permission_required(["components.documentation.view"])
async def git_graph_update(ctx: dict, session: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_charts/git/title": "Updated page-store git graph",
                "/components_charts/git/commits": _GIT_COMMITS,
                "/components_charts/git/edges": _GIT_EDGES,
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_charts/git/title": "Updated global-store git graph",
                "/components_charts/git/commits": _GIT_COMMITS,
                "/components_charts/git/edges": _GIT_EDGES,
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_charts": {
                    "git_model": {
                        "title": "Updated data-model git graph",
                        "commits": _GIT_COMMITS,
                        "edges": _GIT_EDGES,
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_charts_git_direct",
                "title",
                "Updated direct git graph",
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_git_direct",
                "commits",
                _GIT_COMMITS,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_charts_git_direct",
                "edges",
                _GIT_EDGES,
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()
