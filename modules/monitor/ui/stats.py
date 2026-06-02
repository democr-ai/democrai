from __future__ import annotations

import hashlib
import re

from democrai.sdk.auth import permission_required
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.ui import bound


def _node_key(node_id: str) -> str:
    raw = str(node_id or "").strip()
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{slug or 'node'}_{digest}"


def _t(key: str) -> str:
    return sdk.i18n.t(f"monitor.{key}")


def _store(path: str):
    return bound.store(path, scope="page")


def _set_layout(component, **props):
    for key, value in props.items():
        component.set_property(key, value)
    return component


def _register_component_tree(builder, component) -> None:
    builder.add(component)
    for child in list(getattr(component, "children", []) or []):
        if hasattr(child, "to_dict"):
            _register_component_tree(builder, child)


def _node_metric_column(node_key: str, metric: str, label: str):
    column = sdk.ui.Column(
        f"monitor_stats_node_{node_key}_{metric}_summary",
        [
            sdk.ui.Text(
                f"monitor_stats_node_{node_key}_{metric}_label",
                label,
            ),
            sdk.ui.Title(
                f"monitor_stats_node_{node_key}_{metric}_value",
                _store(f"/monitor_stats/nodes/{node_key}/latest/{metric}"),
                level=3,
            ),
        ],
    )
    return _set_layout(column, spacing=4)


def _node_chart(node_key: str, metric: str, title: str, chart_type: str):
    chart = sdk.ui.Chart(
        f"monitor_stats_node_{node_key}_{metric}_chart",
        chart_type=chart_type,
        data=_store(f"/monitor_stats/nodes/{node_key}/{metric}/data"),
        labels=_store(f"/monitor_stats/nodes/{node_key}/{metric}/labels"),
        title=title,
    )
    return _set_layout(chart, max_height=220)


def _node_row(node: dict):
    node_id = str(node.get("node_id") or "").strip()
    node_key = _node_key(node_id)
    label = str(node.get("label") or node_id).strip() or node_id
    status = str(node.get("status") or "").strip()
    hostname = str(node.get("hostname") or "").strip()
    meta = " | ".join(item for item in (status, hostname, node_id) if item)

    binding = sdk.ui.StreamBinding(
        f"monitor_stats_node_{node_key}_binding",
        stream="system.runtime.metrics.events",
        event="runtime.metrics.sample",
        target={"store": "page", "path": f"/monitor_stats/nodes/{node_key}"},
        transformer={
            "name": "monitor.runtime_metrics_sample",
            "context": {"node_id": node_id, "node_key": node_key, "window": 45},
        },
    )

    header = sdk.ui.Row(
        f"monitor_stats_node_{node_key}_header",
        [
            sdk.ui.Column(
                f"monitor_stats_node_{node_key}_identity",
                [
                    sdk.ui.Title(
                        f"monitor_stats_node_{node_key}_title",
                        label,
                        level=3,
                    ),
                    sdk.ui.Text(
                        f"monitor_stats_node_{node_key}_meta",
                        meta,
                    ),
                ],
            )
        ],
    )
    _set_layout(header, align="fill")

    values = sdk.ui.Row(
        f"monitor_stats_node_{node_key}_values",
        [
            _node_metric_column(node_key, "cpu", "CPU"),
            _node_metric_column(node_key, "ram", "RAM"),
            _node_metric_column(node_key, "vram", "VRAM"),
        ],
    )
    _set_layout(values, spacing=14, align="fill")

    charts = sdk.ui.Row(
        f"monitor_stats_node_{node_key}_charts",
        [
            _node_chart(node_key, "cpu", "CPU %", "line"),
            _node_chart(node_key, "ram", "RAM %", "area"),
            _node_chart(node_key, "vram", "VRAM %", "line"),
        ],
    )
    _set_layout(charts, spacing=14, align="fill")

    row = sdk.ui.Card(
        f"monitor_stats_node_{node_key}_row",
        [binding, header, values, charts],
        variant="outlined",
    )
    return _set_layout(row, padding=[18, 18, 18, 18], spacing=14)


@permission_required(["monitor.view"])
async def render(params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/stats")

    active_users = sdk.system.connections.count_active_users()
    active_connections = sdk.system.connections.count_active_connections()
    completed_tasks = int(
        sdk.models.background_tasks.count(filters={"status": "completed"}) or 0
    )
    failed_tasks = int(
        sdk.models.background_tasks.count(filters={"status": "failed"}) or 0
    )
    users_count = int(sdk.models.users.count() or 0)
    runtime_nodes = sdk.system.runtime_nodes.list()

    builder.set_data("/stats/active_users", str(active_users))
    builder.set_data("/stats/active_connections", str(active_connections))
    builder.set_data("/stats/completed_tasks", str(completed_tasks))
    builder.set_data("/stats/failed_tasks", str(failed_tasks))
    builder.set_data("/stats/users_count", str(users_count))
    builder.set_data(
        "/stats/runtime_nodes_note",
        "" if runtime_nodes else _t("stats.runtime_nodes_empty"),
    )

    node_rows = builder.get_component("monitor_stats_node_rows")
    for node in runtime_nodes:
        node_id = str(node.get("node_id") or "").strip()
        if not node_id:
            continue
        node_key = _node_key(node_id)
        for metric in ("cpu", "ram", "vram"):
            builder.set_store(
                f"/monitor_stats/nodes/{node_key}/{metric}/data",
                [],
                scope="page",
            )
            builder.set_store(
                f"/monitor_stats/nodes/{node_key}/{metric}/labels",
                [],
                scope="page",
            )
        builder.set_store(
            f"/monitor_stats/nodes/{node_key}/latest/node_id",
            node_id,
            scope="page",
        )
        builder.set_store(
            f"/monitor_stats/nodes/{node_key}/latest/cpu",
            "-",
            scope="page",
        )
        builder.set_store(
            f"/monitor_stats/nodes/{node_key}/latest/ram",
            "-",
            scope="page",
        )
        builder.set_store(
            f"/monitor_stats/nodes/{node_key}/latest/vram",
            "-",
            scope="page",
        )
        if node_rows is not None:
            row = _node_row(node)
            node_rows.children.append(row)
            _register_component_tree(builder, row)

    return builder
