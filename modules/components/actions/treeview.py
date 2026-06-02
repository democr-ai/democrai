from __future__ import annotations

from democrai.sdk.auth import permission_required
import json

from democrai.sdk.decorators import action


_PAGE_NODES = [
    {
        "id": "runtime_page_root",
        "label": "Page store tree",
        "expanded": True,
        "selectable": False,
        "children": [
            {"id": "runtime_page_logs", "label": "Runtime logs", "value": "logs", "icon": "ric.terminal-box-line"},
            {"id": "runtime_page_metrics", "label": "Metrics", "value": "metrics", "icon": "ric.line-chart-line"},
        ],
    }
]

_GLOBAL_NODES = [
    {
        "id": "runtime_global_root",
        "label": "Global store tree",
        "expanded": True,
        "selectable": False,
        "children": [
            {"id": "runtime_global_docs", "label": "Documentation", "value": "docs", "icon": "ric.book-open-line"},
            {"id": "runtime_global_support", "label": "Support", "value": "support", "icon": "ric.customer-service-2-line"},
        ],
    }
]

_DATA_NODES = [
    {
        "id": "runtime_data_root",
        "label": "Data-model tree",
        "expanded": True,
        "selectable": False,
        "children": [
            {"id": "runtime_data_pending", "label": "Pending review", "value": "pending"},
            {"id": "runtime_data_approved", "label": "Approved", "value": "approved"},
        ],
    }
]

_DIRECT_NODES = [
    {
        "id": "runtime_direct_root",
        "label": "Direct tree updated",
        "expanded": True,
        "selectable": False,
        "children": [
            {"id": "runtime_direct_alpha", "label": "Direct alpha", "value": "alpha"},
            {"id": "runtime_direct_beta", "label": "Direct beta", "value": "beta"},
        ],
    }
]


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


def _selection_text(ctx: dict) -> str:
    selected_items = ctx.get("selected_items")
    if not isinstance(selected_items, list) or not selected_items:
        return "No selection"
    labels = [
        str(item.get("label") or item.get("id") or "")
        for item in selected_items
        if isinstance(item, dict)
    ]
    return ", ".join(label for label in labels if label) or "No selection"


@action("treeview_update")
@permission_required(["components.documentation.view"])
async def treeview_update(ctx: dict, sdk) -> dict:
    mode = str(ctx.get("mode") or "")
    surface_id = str(ctx.get("_surface_id") or "main").strip() or "main"

    if mode == "page_store":
        return _state_update(
            sdk,
            "page",
            {
                "/components_complex/treeview/nodes": _PAGE_NODES,
                "/components_complex/treeview/active_id": "runtime_page_metrics",
                "/components_complex/treeview/expand_all": True,
                "/components_complex/treeview/click_mode": "none",
                "/components_complex/treeview/selection_mode": "single",
            },
        )
    if mode == "global_store":
        return _state_update(
            sdk,
            "global",
            {
                "/components_complex/treeview/nodes": _GLOBAL_NODES,
                "/components_complex/treeview/active_id": "runtime_global_docs",
                "/components_complex/treeview/expand_all": True,
                "/components_complex/treeview/click_mode": "single",
                "/components_complex/treeview/selection_mode": "single",
            },
        )
    if mode == "data":
        return _data_update(
            sdk,
            surface_id,
            {
                "components_complex": {
                    "treeview_model": {
                        "nodes": _DATA_NODES,
                        "active_id": "runtime_data_pending",
                        "expand_all": True,
                        "click_mode": "none",
                        "selection_mode": "multiple",
                    }
                }
            },
        )
    if mode == "direct":
        return sdk.effects.respond(
            sdk.effects.ui_property_update(
                "components_complex_treeview_direct",
                "nodes",
                _DIRECT_NODES,
                surface_id=surface_id,
            ),
            sdk.effects.ui_property_update(
                "components_complex_treeview_direct",
                "active_id",
                "runtime_direct_beta",
                surface_id=surface_id,
            ),
        )

    return sdk.effects.respond()


@action("treeview_select")
@permission_required(["components.documentation.view"])
async def treeview_select(ctx: dict, sdk) -> dict:
    source = str(ctx.get("source") or "treeview")
    selected = _selection_text(ctx)
    active_id = str(ctx.get("active_id") or "")
    payload = {
        key: value
        for key, value in ctx.items()
        if not str(key).startswith("_") and key not in {"selected_items"}
    }
    text = json.dumps(payload, ensure_ascii=False)

    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/components_complex/treeview/selected": f"{source}: {selected}"
                            + (f" ({active_id})" if active_id else "")
                        },
                    }
                }
            ]
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "TreeView selection",
                "text": f"{selected}\n{text}",
                "variant": "info",
                "duration": 2600,
            },
        ),
    )


@action("treeview_confirm")
@permission_required(["components.documentation.view"])
async def treeview_confirm(ctx: dict, sdk) -> dict:
    source = str(ctx.get("source") or "confirm_tree")
    selected = _selection_text(ctx)
    return sdk.effects.respond(
        sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/components_complex/treeview/selected": f"{source}: confirmed {selected}"
                        },
                    }
                }
            ]
        ),
        sdk.effects.notify(
            "toast",
            {
                "title": "TreeView confirmed",
                "text": selected,
                "variant": "success",
                "duration": 2400,
            },
        ),
    )
