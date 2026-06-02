from __future__ import annotations

import copy
import json
from collections import defaultdict, deque
from typing import Any, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer
from ...base_visibility import evaluate_visibility_rule
from ....theme.tokens import theme_token, themed_status_color


_W = {
    "node.fill": theme_token("workflow.node.fill"),
    "node.stroke": theme_token("workflow.node.stroke"),
    "node.text": theme_token("workflow.node.text"),
    "surface.base": theme_token("data.surface.base"),
    "surface.panel": theme_token("data.surface.panel"),
    "surface.header": theme_token("data.surface.panel_alt"),
    "border.grid": theme_token("data.border.grid"),
    "border.soft": theme_token("data.border.soft"),
    "text.primary": theme_token("data.text.primary"),
    "text.muted": theme_token("data.text.muted"),
    "accent": theme_token("data.accent"),
    "accent.alt": theme_token("data.accent.alt"),
}


def _safe_color(raw: Any, fallback: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return fallback
    color = QColor(text)
    return text if color.isValid() else fallback


def _normalize_param_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for value in raw:
        text = str(value or "").strip()
        if text:
            out.append(text)
    return out


def _normalize_mapping(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        k = str(key or "").strip()
        v = str(value or "").strip()
        if k and v:
            out[k] = v
    return out


def _ensure_component_ids(comp_def: dict[str, Any], suffix: str) -> None:
    if not isinstance(comp_def, dict):
        return
    if "id" in comp_def and isinstance(comp_def["id"], str):
        comp_def["id"] = f"{comp_def['id']}_{suffix}"
    elif "id" not in comp_def:
        comp_def["id"] = f"workflow_embedded_{suffix}"

    component = comp_def.get("component")
    if not isinstance(component, dict) or not component:
        return
    c_type = list(component.keys())[0]
    comp_props = component.get(c_type, {})
    children_node = comp_def.get("children") or comp_props.get("children", {})
    if isinstance(children_node, dict) and "explicitList" in children_node:
        for idx, child in enumerate(children_node["explicitList"]):
            if isinstance(child, dict):
                _ensure_component_ids(child, f"{suffix}_{idx}")


def _resolve_drawer_defs(
    drawer_defs: dict[str, Any],
    *,
    selection_kind: str,
    node_type: str,
) -> list[dict[str, Any]]:
    if not isinstance(drawer_defs, dict):
        return []
    if selection_kind == "edge":
        value = drawer_defs.get("edge", [])
        return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []
    node_types = drawer_defs.get("nodeTypes", {})
    if isinstance(node_types, dict):
        typed = node_types.get(node_type, [])
        if isinstance(typed, list) and typed:
            return [v for v in typed if isinstance(v, dict)]
    value = drawer_defs.get("node", [])
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


def _apply_context_templates(value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, str):
        for key, rep in context.items():
            if value == f"{{{{{key}}}}}":
                return rep
        out = value
        for key, rep in context.items():
            out = out.replace(f"{{{{{key}}}}}", str(rep))
        return out
    if isinstance(value, dict):
        return {k: _apply_context_templates(v, context) for k, v in value.items()}
    if isinstance(value, list):
        return [_apply_context_templates(v, context) for v in value]
    return value


def _normalize_component_catalog(props: Dict[str, Any]) -> list[dict[str, Any]]:
    raw_catalog = props.get("componentCatalog")
    if not isinstance(raw_catalog, list):
        return [
            {
                "id": "generic_component",
                "label": "Generic Component",
                "nodeType": "component",
                "status": "ready",
                "fill": _W["node.fill"],
                "stroke": _W["node.stroke"],
                "textColor": _W["node.text"],
                "config": {},
                "input": {"params": []},
                "outputs": [{"id": "out_1", "label": "out_1", "params": []}],
                "allowAddOutput": True,
            }
        ]

    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_catalog):
        if not isinstance(raw, dict):
            continue
        base_id = str(raw.get("id") or f"template_{index + 1}").strip() or f"template_{index + 1}"
        outputs = []
        if isinstance(raw.get("outputs"), list):
            for out_index, out in enumerate(raw.get("outputs") or []):
                if not isinstance(out, dict):
                    continue
                out_id = str(out.get("id") or f"out_{out_index + 1}").strip()
                if not out_id:
                    continue
                outputs.append(
                    {
                        "id": out_id,
                        "label": str(out.get("label") or out_id).strip() or out_id,
                        "params": _normalize_param_list(out.get("params")),
                    }
                )
        if not outputs:
            outputs = [{"id": "out_1", "label": "out_1", "params": []}]

        input_spec = raw.get("input")
        if not isinstance(input_spec, dict):
            input_spec = {}

        config = raw.get("config")
        if not isinstance(config, dict):
            config = {}

        normalized.append(
            {
                "id": base_id,
                "label": str(raw.get("label") or base_id).strip() or base_id,
                "nodeType": str(raw.get("nodeType") or raw.get("type") or "component").strip() or "component",
                "status": str(raw.get("status") or "ready").strip().lower(),
                "fill": _safe_color(raw.get("fill"), _W["node.fill"]),
                "stroke": _safe_color(raw.get("stroke"), _W["node.stroke"]),
                "textColor": _safe_color(raw.get("textColor"), _W["node.text"]),
                "config": config,
                "input": {"params": _normalize_param_list(input_spec.get("params"))},
                "outputs": outputs,
                "allowAddOutput": bool(raw.get("allowAddOutput", True)),
                "cascadeDeleteConnected": bool(
                    raw.get(
                        "cascadeDeleteConnected",
                        str(raw.get("nodeType") or raw.get("type") or "component").strip().lower() == "component",
                    )
                ),
            }
        )

    if normalized:
        return normalized
    return [
        {
            "id": "generic_component",
            "label": "Generic Component",
            "nodeType": "component",
            "status": "ready",
            "fill": _W["node.fill"],
            "stroke": _W["node.stroke"],
            "textColor": _W["node.text"],
            "config": {},
            "input": {"params": []},
            "outputs": [{"id": "out_1", "label": "out_1", "params": []}],
            "allowAddOutput": True,
        }
    ]


def _default_flow() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes = [
        {
            "id": "trigger",
            "label": "Webhook Trigger",
            "nodeType": "trigger",
            "status": "ready",
            "fill": _W["node.fill"],
            "stroke": themed_status_color("active"),
            "config": {"method": "POST", "path": "/workflow/inbound"},
            "x": 80,
            "y": 220,
            "outputs": [{"id": "payload", "label": "payload", "params": ["body", "headers"]}],
        },
        {
            "id": "normalize",
            "label": "Normalize Payload",
            "nodeType": "transform",
            "status": "running",
            "fill": _W["node.fill"],
            "stroke": themed_status_color("running"),
            "config": {"fields": ["email", "topic", "priority"]},
            "input": {"params": ["body", "headers"]},
            "outputs": [{"id": "normalized", "label": "normalized", "params": ["email", "topic", "priority"]}],
        },
        {
            "id": "route",
            "label": "Route by Priority",
            "nodeType": "router",
            "status": "ready",
            "fill": _W["node.fill"],
            "stroke": themed_status_color("success"),
            "config": {"rules": ["priority=high", "priority=normal"]},
            "input": {"params": ["email", "topic", "priority"]},
            "outputs": [
                {"id": "high", "label": "high", "params": ["ticket_id", "priority", "email"]},
                {"id": "normal", "label": "normal", "params": ["ticket_id", "priority", "email"]},
            ],
            "allowAddOutput": True,
        },
        {
            "id": "human_review",
            "label": "Human Approval",
            "nodeType": "approval",
            "status": "waiting",
            "fill": _W["node.fill"],
            "stroke": themed_status_color("warning"),
            "config": {"requiredRole": "manager"},
            "input": {"params": ["ticket_id", "priority", "email"]},
            "outputs": [{"id": "approved", "label": "approved", "params": ["ticket_id", "priority", "email"]}],
        },
        {
            "id": "notify",
            "label": "Slack Notification",
            "nodeType": "action",
            "status": "ready",
            "fill": _W["node.fill"],
            "stroke": _W["accent"],
            "config": {"channel": "#ops-alerts"},
            "input": {"params": ["ticket_id", "priority", "email"]},
            "outputs": [{"id": "notified", "label": "notified", "params": ["message_id", "ticket_id"]}],
        },
        {
            "id": "store",
            "label": "Persist Run",
            "nodeType": "storage",
            "status": "ready",
            "fill": _W["node.fill"],
            "stroke": themed_status_color("success"),
            "config": {"table": "workflow_runs"},
            "input": {"params": ["message_id", "ticket_id"]},
            "outputs": [{"id": "saved", "label": "saved", "params": ["run_id"]}],
        },
    ]
    edges = [
        {
            "source": "trigger",
            "target": "normalize",
            "sourceOutput": "payload",
            "mapping": {"body": "body", "headers": "headers"},
        },
        {
            "source": "normalize",
            "target": "route",
            "sourceOutput": "normalized",
            "mapping": {"email": "email", "topic": "topic", "priority": "priority"},
        },
        {
            "source": "route",
            "target": "human_review",
            "sourceOutput": "high",
            "label": "high",
            "mapping": {"ticket_id": "ticket_id", "priority": "priority", "email": "email"},
        },
        {
            "source": "route",
            "target": "notify",
            "sourceOutput": "normal",
            "label": "normal",
            "mapping": {"ticket_id": "ticket_id", "priority": "priority", "email": "email"},
        },
        {
            "source": "human_review",
            "target": "notify",
            "sourceOutput": "approved",
            "label": "approved",
            "mapping": {"ticket_id": "ticket_id", "priority": "priority", "email": "email"},
        },
        {
            "source": "notify",
            "target": "store",
            "sourceOutput": "notified",
            "mapping": {"message_id": "message_id", "ticket_id": "ticket_id"},
        },
    ]
    return nodes, edges


def _normalize_nodes(props: Dict[str, Any]) -> list[dict[str, Any]]:
    raw_nodes = list(props.get("nodes") or [])
    if not raw_nodes:
        raw_nodes, _ = _default_flow()
    nodes: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or f"node_{index + 1}").strip()
        if not node_id:
            continue

        outputs_raw = raw.get("outputs")
        outputs: list[dict[str, Any]] = []
        if isinstance(outputs_raw, list):
            for out_index, out in enumerate(outputs_raw):
                if not isinstance(out, dict):
                    continue
                out_id = str(out.get("id") or f"out_{out_index + 1}").strip()
                if not out_id:
                    continue
                outputs.append(
                    {
                        "id": out_id,
                        "label": str(out.get("label") or out_id).strip() or out_id,
                        "params": _normalize_param_list(out.get("params")),
                    }
                )
        if not outputs:
            outputs = [{"id": "out_1", "label": "out_1", "params": []}]

        input_spec = raw.get("input")
        if not isinstance(input_spec, dict):
            input_spec = {}

        node_type = str(raw.get("nodeType") or raw.get("type") or "step").strip() or "step"
        label = str(raw.get("label") or node_type.title()).strip() or node_id
        status = str(raw.get("status") or "ready").strip().lower()
        config = raw.get("config")
        if not isinstance(config, dict):
            config = {}

        x = raw.get("x")
        y = raw.get("y")
        nodes.append(
            {
                "id": node_id,
                "label": label,
                "nodeType": node_type,
                "status": status,
                "fill": _safe_color(raw.get("fill"), _W["node.fill"]),
                "stroke": _safe_color(raw.get("stroke"), _W["node.stroke"]),
                "textColor": _safe_color(raw.get("textColor"), _W["node.text"]),
                "config": config,
                "input": {"params": _normalize_param_list(input_spec.get("params"))},
                "outputs": outputs,
                "allowAddOutput": bool(raw.get("allowAddOutput", True)),
                "cascadeDeleteConnected": bool(
                    raw.get(
                        "cascadeDeleteConnected",
                        str(raw.get("nodeType") or raw.get("type") or "step").strip().lower() == "component",
                    )
                ),
                "x": float(x) if isinstance(x, (int, float)) else None,
                "y": float(y) if isinstance(y, (int, float)) else None,
            }
        )
    return nodes


def _normalize_edges(
    props: Dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    raw_edges = list(props.get("edges") or [])
    if not raw_edges:
        _, raw_edges = _default_flow()

    edges: list[dict[str, Any]] = []
    for raw in raw_edges:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or raw.get("from") or "").strip()
        target = str(raw.get("target") or raw.get("to") or "").strip()
        if source not in nodes_by_id or target not in nodes_by_id:
            continue

        source_outputs = [o["id"] for o in nodes_by_id[source].get("outputs", [])]
        if not source_outputs:
            continue
        source_output = str(raw.get("sourceOutput") or raw.get("output") or source_outputs[0]).strip()
        if source_output not in source_outputs:
            source_output = source_outputs[0]

        edges.append(
            {
                "source": source,
                "target": target,
                "sourceOutput": source_output,
                "label": str(raw.get("label") or "").strip(),
                "mapping": _normalize_mapping(raw.get("mapping")),
            }
        )
    return edges


def _levels(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, int]:
    incoming: dict[str, int] = {node["id"]: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["source"]].append(edge["target"])
        incoming[edge["target"]] = incoming.get(edge["target"], 0) + 1

    queue = deque([node_id for node_id, count in incoming.items() if count == 0])
    levels: dict[str, int] = {node["id"]: 0 for node in nodes}
    visited: set[str] = set()
    while queue:
        current = queue.popleft()
        visited.add(current)
        for child in outgoing.get(current, []):
            levels[child] = max(levels.get(child, 0), levels.get(current, 0) + 1)
            incoming[child] -= 1
            if incoming[child] == 0:
                queue.append(child)

    max_level = max(levels.values(), default=0)
    for node in nodes:
        node_id = node["id"]
        if node_id in visited:
            continue
        max_level += 1
        levels[node_id] = max_level
    return levels


def _auto_positions(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    node_w: int,
    node_h: int,
) -> dict[str, QPointF]:
    gap_x = max(220, int(node_w * 1.5))
    gap_y = max(140, int(node_h * 1.7))
    levels = _levels(nodes, edges)
    by_level: dict[int, list[str]] = defaultdict(list)
    for node in nodes:
        by_level[levels.get(node["id"], 0)].append(node["id"])

    positions: dict[str, QPointF] = {}
    for level in sorted(by_level):
        for row, node_id in enumerate(by_level[level]):
            positions[node_id] = QPointF(80 + level * gap_x, 80 + row * gap_y)
    return positions


class _WorkflowNodeItem(QGraphicsRectItem):
    def __init__(
        self,
        node: dict[str, Any],
        *,
        width: int,
        height: int,
        on_move,
        on_output_drag_start=None,
        on_output_drag_move=None,
        on_output_drag_release=None,
    ):
        super().__init__(QRectF(0, 0, width, height))
        self.node = node
        self._on_move = on_move
        self._on_output_drag_start = on_output_drag_start
        self._on_output_drag_move = on_output_drag_move
        self._on_output_drag_release = on_output_drag_release
        self._port_items: list[QGraphicsItem] = []

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.OpenHandCursor)
        self.setPen(QPen(QColor(node["stroke"]), 2.0))
        self.setBrush(QBrush(QColor(node["fill"])))
        self.setZValue(10)

        title = QGraphicsSimpleTextItem(node["label"], self)
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setWeight(QFont.DemiBold)
        title.setFont(title_font)
        title.setBrush(QBrush(QColor(node["textColor"])))
        title.setPos(12, 10)

        kind = QGraphicsSimpleTextItem(str(node["nodeType"]).upper(), self)
        kind_font = QFont()
        kind_font.setPointSize(8)
        kind.setFont(kind_font)
        kind.setBrush(QBrush(QColor(_W["text.muted"])))
        kind.setPos(12, 32)

        status = QGraphicsSimpleTextItem(str(node["status"]).upper(), self)
        status_font = QFont()
        status_font.setPointSize(8)
        status.setFont(status_font)
        status.setBrush(QBrush(QColor(node["stroke"])))
        status_bounds = status.boundingRect()
        status.setPos(width - status_bounds.width() - 12, 10)

        self._draw_ports()

    def _draw_ports(self) -> None:
        for item in self._port_items:
            try:
                scene = item.scene()
                if scene is not None:
                    scene.removeItem(item)
            except RuntimeError:
                pass
        self._port_items.clear()

        rect = self.rect()
        in_port = QGraphicsEllipseItem(-6, rect.height() / 2 - 6, 12, 12, self)
        in_port.setPen(QPen(QColor(_W["surface.base"]), 1.2))
        in_port.setBrush(QBrush(QColor(_W["text.primary"])))
        self._port_items.append(in_port)

        outputs = list(self.node.get("outputs") or [])
        count = max(1, len(outputs))
        if count == 1:
            ys = [rect.height() / 2]
        else:
            step = rect.height() / (count + 1)
            ys = [step * (idx + 1) for idx in range(count)]

        for idx, output in enumerate(outputs):
            y = ys[idx]
            output_id = str(output.get("id") or f"out_{idx + 1}")
            dot = _WorkflowOutputPortItem(
                node_item=self,
                output_id=output_id,
                x=rect.width() - 6,
                y=y - 6,
                width=12,
                height=12,
                on_drag_start=self._on_output_drag_start,
                on_drag_move=self._on_output_drag_move,
                on_drag_release=self._on_output_drag_release,
            )
            dot.setPen(QPen(QColor(_W["surface.base"]), 1.2))
            dot.setBrush(QBrush(QColor(self.node["stroke"])))
            self._port_items.append(dot)

            label = QGraphicsSimpleTextItem(str(output["label"]), self)
            label_font = QFont()
            label_font.setPointSize(7)
            label.setFont(label_font)
            label.setBrush(QBrush(QColor(_W["text.muted"])))
            bounds = label.boundingRect()
            label.setPos(rect.width() - bounds.width() - 14, y - bounds.height() - 4)
            self._port_items.append(label)

    def add_output(self, output_def: dict[str, Any]) -> None:
        outputs = self.node.setdefault("outputs", [])
        outputs.append(output_def)
        self._draw_ports()
        if self._on_move:
            self._on_move()

    def out_anchor(self, output_id: str) -> QPointF:
        outputs = list(self.node.get("outputs") or [])
        rect = self.rect()
        if not outputs:
            return self.mapToScene(QPointF(rect.width(), rect.height() / 2))

        index = 0
        for idx, output in enumerate(outputs):
            if str(output.get("id")) == str(output_id):
                index = idx
                break

        count = len(outputs)
        if count == 1:
            y = rect.height() / 2
        else:
            y = (rect.height() / (count + 1)) * (index + 1)
        return self.mapToScene(QPointF(rect.width(), y))

    def in_anchor(self) -> QPointF:
        rect = self.rect()
        return self.mapToScene(QPointF(0, rect.height() / 2))

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self._on_move:
            self._on_move()
        return super().itemChange(change, value)


class _WorkflowOutputPortItem(QGraphicsEllipseItem):
    def __init__(
        self,
        *,
        node_item: _WorkflowNodeItem,
        output_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
        on_drag_start=None,
        on_drag_move=None,
        on_drag_release=None,
    ):
        super().__init__(x, y, width, height, node_item)
        self.node_item = node_item
        self.output_id = output_id
        self._on_drag_start = on_drag_start
        self._on_drag_move = on_drag_move
        self._on_drag_release = on_drag_release
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CrossCursor)
        self.setZValue(15)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._on_drag_start:
            self._on_drag_start(self.node_item, self.output_id, event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._on_drag_move:
            self._on_drag_move(event.scenePos())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._on_drag_release:
            self._on_drag_release(event.scenePos())
            event.accept()
            return
        super().mouseReleaseEvent(event)


class _WorkflowEdgeItem(QGraphicsPathItem):
    def __init__(
        self,
        *,
        edge: dict[str, Any],
        source: _WorkflowNodeItem,
        target: _WorkflowNodeItem,
    ):
        super().__init__()
        self.edge = edge
        self.source = source
        self.target = target
        self._label_item = QGraphicsSimpleTextItem()
        self._label_item.setBrush(QBrush(QColor(_W["text.muted"])))

        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.PointingHandCursor)
        self.setZValue(1)
        self.update_visual()

    def _label_text(self) -> str:
        output_id = str(self.edge.get("sourceOutput") or "")
        mapping = self.edge.get("mapping") or {}
        mapping_count = len(mapping) if isinstance(mapping, dict) else 0
        label = str(self.edge.get("label") or "").strip()
        base = label or output_id
        if not base:
            return ""
        if mapping_count:
            return f"{base} ({mapping_count} map)"
        return base

    def update_visual(self) -> None:
        color = QColor(_W["accent"]) if self.isSelected() else QColor(_W["text.muted"])
        pen = QPen(color, 2.4 if self.isSelected() else 2.0)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)

    def attach_to_scene(self, scene: QGraphicsScene) -> None:
        scene.addItem(self)
        scene.addItem(self._label_item)
        self.update_path()

    def update_path(self) -> None:
        start = self.source.out_anchor(str(self.edge.get("sourceOutput") or ""))
        end = self.target.in_anchor()
        dx = max(50.0, abs(end.x() - start.x()) * 0.45)
        ctrl1 = QPointF(start.x() + dx, start.y())
        ctrl2 = QPointF(end.x() - dx, end.y())

        path = QPainterPath(start)
        path.cubicTo(ctrl1, ctrl2, end)
        self.setPath(path)

        text = self._label_text()
        self._label_item.setText(text)
        if text:
            t = path.pointAtPercent(0.5)
            bounds = self._label_item.boundingRect()
            self._label_item.setPos(t.x() - bounds.width() / 2, t.y() - bounds.height() - 6)
        else:
            self._label_item.setPos(-9999, -9999)


class _WorkflowView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None):
        super().__init__(parent)
        self.setScene(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor(_W["surface.base"]))
        self._zoom = 0
        self._on_delete_request = None
        self.setFocusPolicy(Qt.StrongFocus)

    def set_delete_handler(self, callback) -> None:
        self._on_delete_request = callback

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        grid = 24
        left = int(rect.left()) - (int(rect.left()) % grid)
        top = int(rect.top()) - (int(rect.top()) % grid)
        painter.setPen(QPen(QColor(39, 39, 42, 160), 1.0))

        x = left
        while x < rect.right():
            painter.drawLine(x, rect.top(), x, rect.bottom())
            x += grid

        y = top
        while y < rect.bottom():
            painter.drawLine(rect.left(), y, rect.right(), y)
            y += grid

    def showEvent(self, event):
        super().showEvent(event)
        self.fit_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom == 0:
            self.fit_scene()

    def fit_scene(self) -> None:
        scene = self.scene()
        if scene is None:
            return
        rect = scene.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self.fitInView(rect.adjusted(-32, -32, 32, 32), Qt.KeepAspectRatio)

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            super().wheelEvent(event)
            return
        step = 1.12 if delta > 0 else 1 / 1.12
        next_zoom = self._zoom + (1 if delta > 0 else -1)
        if next_zoom < -4 or next_zoom > 12:
            event.accept()
            return
        self._zoom = next_zoom
        if self._zoom == 0:
            self.fit_scene()
            event.accept()
            return
        self.scale(step, step)
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self._on_delete_request:
            self._on_delete_request()
            event.accept()
            return
        super().keyPressEvent(event)


class WorkflowRenderer(BaseRenderer):
    component_type = "Workflow"

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QWidget()
        container.setObjectName(comp_id)
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        title = str(props.get("title") or "Workflow Builder").strip()
        if title:
            title_label = QLabel(title)
            title_label.setProperty("ui_role", "workflow_title")
            root.addWidget(title_label)

        toolbar = QWidget()
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(8)
        root.addWidget(toolbar)

        frame = QWidget()
        frame_layout = QHBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(12)

        scene = QGraphicsScene()
        scene.setBackgroundBrush(QBrush(QColor(_W["surface.base"])))
        view = _WorkflowView(scene)
        view.setObjectName(f"{comp_id}_view")
        view.setMinimumHeight(max(260, int(props.get("height", 560))))
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame_layout.addWidget(view, 1)

        root.addWidget(frame, 1)

        node_w = max(170, int(props.get("nodeWidth", 214)))
        node_h = max(82, int(props.get("nodeHeight", 92)))
        nodes = _normalize_nodes(props)
        nodes_by_id = {node["id"]: node for node in nodes}
        edges = _normalize_edges(props, nodes_by_id)
        def _normalize_group_templates(raw_group: Any, *, default_node_type: str) -> list[dict[str, Any]]:
            if not isinstance(raw_group, list) or not raw_group:
                return []
            prepared: list[dict[str, Any]] = []
            for index, item in enumerate(raw_group):
                if not isinstance(item, dict):
                    continue
                template = copy.deepcopy(item)
                if not isinstance(template.get("nodeType"), str) or not str(template.get("nodeType") or "").strip():
                    template["nodeType"] = default_node_type
                if not isinstance(template.get("id"), str) or not str(template.get("id") or "").strip():
                    template["id"] = f"{default_node_type}_{index + 1}"
                prepared.append(template)
            if not prepared:
                return []
            return _normalize_component_catalog({"componentCatalog": prepared})

        trigger_templates = _normalize_group_templates(props.get("triggers"), default_node_type="trigger")
        component_templates = _normalize_group_templates(props.get("components"), default_node_type="component")
        pipeline_templates = _normalize_group_templates(
            props.get("pipelines") if props.get("pipelines") is not None else props.get("piplines"),
            default_node_type="pipeline",
        )
        if not trigger_templates and not component_templates and not pipeline_templates:
            component_templates = _normalize_component_catalog(props)

        catalog_groups: dict[str, list[dict[str, Any]]] = {
            "triggers": trigger_templates,
            "components": component_templates,
            "pipelines": pipeline_templates,
        }
        template_lookup: dict[str, dict[str, Any]] = {}
        for group_name, templates in catalog_groups.items():
            for index, template in enumerate(templates):
                template_id = str(template.get("id") or f"template_{index + 1}")
                key = f"{group_name}::{template_id}"
                template_lookup[key] = template

        catalog_by_id = {
            str(template.get("id") or f"template_{index + 1}"): template
            for index, template in enumerate(component_templates)
        }
        toolbar_components = list(props.get("toolbarComponents") or [])
        tools_components = list(props.get("toolsComponents") or [])
        selection_drawer_components = props.get("selectionDrawerComponents")
        if not isinstance(selection_drawer_components, dict):
            selection_drawer_components = {}
        if not toolbar_components:
            picker_options = [
                {"label": str(template.get("label") or template_id), "value": template_id}
                for template_id, template in catalog_by_id.items()
            ]
            first_template_id = str(next(iter(catalog_by_id.keys()), ""))
            toolbar_components = [
                {
                    "id": "wf_toolbar_hint",
                    "component": {
                        "Text": {
                            "text": {"literalString": "Single input + multi output per node, with edge parameter mapping"},
                            "style": f"color: {_W['text.muted']}; font-size: 12px;",
                        }
                    },
                },
                {
                    "id": "wf_toolbar_component_picker",
                    "component": {
                        "Select": {
                            "label": {"literalString": ""},
                            "options": picker_options,
                            "value": first_template_id,
                            "max_width": 240,
                            "placeholder": "Select component",
                        }
                    },
                },
                {
                    "id": "wf_toolbar_add_component_btn",
                    "component": {
                        "Button": {
                            "label": {"literalString": "Add Component"},
                            "variant": "default",
                        }
                    },
                },
                {
                    "id": "wf_toolbar_auto_layout_btn",
                    "component": {
                        "Button": {
                            "label": {"literalString": "Auto Layout"},
                            "variant": "default",
                        }
                    },
                },
                {
                    "id": "wf_toolbar_fit_btn",
                    "component": {
                        "Button": {
                            "label": {"literalString": "Fit"},
                            "variant": "default",
                        }
                    },
                },
            ]

        positions = _auto_positions(nodes, edges, node_w=node_w, node_h=node_h)
        if all(node.get("x") is not None and node.get("y") is not None for node in nodes):
            positions = {node["id"]: QPointF(float(node["x"]), float(node["y"])) for node in nodes}

        node_items: dict[str, _WorkflowNodeItem] = {}
        edge_items: list[_WorkflowEdgeItem] = []
        selected_node_item: _WorkflowNodeItem | None = None
        selected_edge_item: _WorkflowEdgeItem | None = None
        selected_kind: str = "none"
        active_drag_source: _WorkflowNodeItem | None = None
        active_drag_output: str = ""
        active_drag_path: QGraphicsPathItem | None = None

        def add_embedded_components(
            host_layout: QVBoxLayout | QHBoxLayout,
            items: list[Any],
            slot: str,
            *,
            preserve_ids: bool = False,
        ) -> None:
            if not items:
                return
            renderer = getattr(app_instance, "renderer", None)
            surfaces = getattr(app_instance, "surfaces", {})
            if renderer is None or not hasattr(renderer, "build_widget"):
                return

            for index, raw in enumerate(items):
                if not isinstance(raw, dict):
                    continue
                comp_def = copy.deepcopy(raw)
                if not preserve_ids:
                    _ensure_component_ids(comp_def, f"{comp_id}_{slot}_{index}")
                widget = renderer.build_widget(
                    surface_id,
                    surfaces,
                    comp_def=comp_def,
                    app_instance=app_instance,
                    seen_dialogs=set(),
                )
                if widget is not None:
                    host_layout.addWidget(widget)

        def refresh_scene_rect() -> None:
            rect = scene.itemsBoundingRect()
            if rect.width() <= 0 or rect.height() <= 0:
                scene.setSceneRect(0, 0, 640, 420)
                return
            scene.setSceneRect(rect.adjusted(-80, -80, 80, 80))

        def refresh_edges() -> None:
            for edge_item in edge_items:
                edge_item.update_path()
                edge_item.update_visual()
            refresh_scene_rect()

        def _get_drawer_widget(widget_id: str) -> QWidget | None:
            getter = getattr(app_instance, "_get_widget_by_id", None)
            if callable(getter):
                try:
                    widget = getter(widget_id)
                    if isinstance(widget, QWidget):
                        return widget
                except Exception:
                    return None
            return None

        def _get_drawer_select(widget_id: str) -> QComboBox | None:
            widget = _get_drawer_widget(widget_id)
            if isinstance(widget, QComboBox):
                return widget
            if widget is None:
                return None
            return widget.findChild(QComboBox, f"{widget_id}__input")

        def _get_drawer_text_field(widget_id: str) -> QLineEdit | None:
            widget = _get_drawer_widget(widget_id)
            if isinstance(widget, QLineEdit):
                return widget
            return None

        def _close_add_modal() -> None:
            surfaces = getattr(app_instance, "_surfaces", None)
            if surfaces is None:
                return
            try:
                surfaces.handle_delete_surface({"surfaceId": "modal"})
            except Exception:
                pass

        def _build_modal_options(group_name: str) -> list[dict[str, str]]:
            templates = catalog_groups.get(group_name, [])
            options: list[dict[str, str]] = []
            for index, template in enumerate(templates):
                template_id = str(template.get("id") or f"template_{index + 1}")
                label = str(template.get("label") or template_id)
                options.append({"label": label, "value": f"{group_name}::{template_id}"})
            return options

        def _get_modal_selected_key() -> str:
            tabs = _get_drawer_widget("workflow_add_modal_tabs")
            select_ids = [
                "workflow_add_modal_triggers_select",
                "workflow_add_modal_components_select",
                "workflow_add_modal_pipelines_select",
            ]
            active_index = 0
            if isinstance(tabs, QTabWidget):
                active_index = max(0, min(tabs.currentIndex(), len(select_ids) - 1))
            preferred = _get_drawer_select(select_ids[active_index])
            if preferred is not None and preferred.currentData() is not None:
                return str(preferred.currentData() or "")
            for select_id in select_ids:
                combo = _get_drawer_select(select_id)
                if combo is not None and combo.currentData() is not None:
                    return str(combo.currentData() or "")
            return ""

        def _bind_add_modal_handlers() -> None:
            confirm_btn = _get_drawer_widget("workflow_add_modal_confirm_btn")
            cancel_btn = _get_drawer_widget("workflow_add_modal_cancel_btn")
            if isinstance(confirm_btn, QPushButton) and not bool(confirm_btn.property("_wf_bound")):
                confirm_btn.clicked.connect(add_component_from_modal)
                confirm_btn.setProperty("_wf_bound", True)
            if isinstance(cancel_btn, QPushButton) and not bool(cancel_btn.property("_wf_bound")):
                cancel_btn.clicked.connect(_close_add_modal)
                cancel_btn.setProperty("_wf_bound", True)

        def open_add_component_modal() -> None:
            surfaces = getattr(app_instance, "_surfaces", None)
            if surfaces is None:
                add_component_from_ui()
                return

            trigger_options = _build_modal_options("triggers")
            component_options = _build_modal_options("components")
            pipeline_options = _build_modal_options("pipelines")
            all_options = trigger_options + component_options + pipeline_options
            if not all_options:
                return

            trigger_default = trigger_options[0]["value"] if trigger_options else ""
            component_default = component_options[0]["value"] if component_options else ""
            pipeline_default = pipeline_options[0]["value"] if pipeline_options else ""

            components: list[dict[str, Any]] = [
                {
                    "id": "workflow_add_modal_triggers_select",
                    "component": {
                        "Select": {
                            "label": {"literalString": ""},
                            "options": trigger_options,
                            "value": trigger_default,
                            "placeholder": "No triggers available",
                        }
                    },
                },
                {
                    "id": "workflow_add_modal_components_select",
                    "component": {
                        "Select": {
                            "label": {"literalString": ""},
                            "options": component_options,
                            "value": component_default,
                            "placeholder": "No components available",
                        }
                    },
                },
                {
                    "id": "workflow_add_modal_pipelines_select",
                    "component": {
                        "Select": {
                            "label": {"literalString": ""},
                            "options": pipeline_options,
                            "value": pipeline_default,
                            "placeholder": "No pipelines available",
                        }
                    },
                },
                {
                    "id": "workflow_add_modal_triggers_tab",
                    "component": {"Column": {"spacing": 8}},
                    "children": {"explicitList": ["workflow_add_modal_triggers_select"]},
                },
                {
                    "id": "workflow_add_modal_components_tab",
                    "component": {"Column": {"spacing": 8}},
                    "children": {"explicitList": ["workflow_add_modal_components_select"]},
                },
                {
                    "id": "workflow_add_modal_pipelines_tab",
                    "component": {"Column": {"spacing": 8}},
                    "children": {"explicitList": ["workflow_add_modal_pipelines_select"]},
                },
                {
                    "id": "workflow_add_modal_tabs",
                    "component": {
                        "Tabs": {
                            "tabs": [
                                {"id": "workflow_add_modal_triggers_tab", "label": "Triggers"},
                                {"id": "workflow_add_modal_components_tab", "label": "Components"},
                                {"id": "workflow_add_modal_pipelines_tab", "label": "Pipelines"},
                            ]
                        }
                    },
                    "children": {
                        "explicitList": [
                            "workflow_add_modal_triggers_tab",
                            "workflow_add_modal_components_tab",
                            "workflow_add_modal_pipelines_tab",
                        ]
                    },
                },
                {
                    "id": "workflow_add_modal_confirm_btn",
                    "component": {"Button": {"label": {"literalString": "Add"}, "variant": "default"}},
                },
                {
                    "id": "workflow_add_modal_cancel_btn",
                    "component": {"Button": {"label": {"literalString": "Cancel"}, "variant": "default"}},
                },
                {
                    "id": "workflow_add_modal_actions",
                    "component": {"Row": {"spacing": 8}},
                    "children": {
                        "explicitList": [
                            "workflow_add_modal_confirm_btn",
                            "workflow_add_modal_cancel_btn",
                        ]
                    },
                },
                {
                    "id": "workflow_add_modal_body",
                    "component": {"Column": {"spacing": 10, "padding": [12, 12, 12, 12]}},
                    "children": {
                        "explicitList": [
                            "workflow_add_modal_tabs",
                            "workflow_add_modal_actions",
                        ]
                    },
                },
                {
                    "id": "workflow_add_modal_dialog",
                    "component": {
                        "Dialog": {
                            "title": "Add Workflow Element",
                        }
                    },
                    "children": {"explicitList": ["workflow_add_modal_body"]},
                },
            ]
            try:
                surfaces.handle_surface_update({"surfaceId": "modal", "components": components})
                surfaces.handle_begin_rendering(
                    {"surfaceId": "modal", "root": "workflow_add_modal_dialog"}
                )
                _bind_add_modal_handlers()
            except Exception:
                return

        def _build_connection_options(source_node: dict[str, Any] | None) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
            if not isinstance(source_node, dict):
                return [], []
            source_options: list[dict[str, str]] = []
            for out in list(source_node.get("outputs") or []):
                out_id = str(out.get("id") or "").strip()
                if not out_id:
                    continue
                source_options.append(
                    {
                        "label": str(out.get("label") or out_id),
                        "value": out_id,
                    }
                )

            source_id = str(source_node.get("id") or "")
            target_options: list[dict[str, str]] = []
            for target_node in nodes:
                target_id = str(target_node.get("id") or "").strip()
                if not target_id or target_id == source_id:
                    continue
                target_options.append(
                    {
                        "label": str(target_node.get("label") or target_id),
                        "value": target_id,
                    }
                )
            return source_options, target_options

        def _bind_drawer_handlers() -> None:
            apply_btn = _get_drawer_widget("workflow_apply_mapping_btn")
            if isinstance(apply_btn, QPushButton) and not bool(apply_btn.property("_wf_bound")):
                apply_btn.clicked.connect(apply_edge_mapping)
                apply_btn.setProperty("_wf_bound", True)

            connect_btn_widget = _get_drawer_widget("workflow_connect_btn")
            if isinstance(connect_btn_widget, QPushButton) and not bool(connect_btn_widget.property("_wf_bound")):
                connect_btn_widget.clicked.connect(connect_selected_output)
                connect_btn_widget.setProperty("_wf_bound", True)

            add_output_btn = _get_drawer_widget("workflow_add_conditional_output_btn")
            if isinstance(add_output_btn, QPushButton) and not bool(add_output_btn.property("_wf_bound")):
                add_output_btn.clicked.connect(add_conditional_output)
                add_output_btn.setProperty("_wf_bound", True)

            mapping_input = _get_drawer_text_field("workflow_edge_mapping")
            if mapping_input is not None:
                mapping_input.setEnabled(selected_kind == "edge")

            source_combo = _get_drawer_select("workflow_connect_source_output")
            target_combo = _get_drawer_select("workflow_connect_target_node")
            connection_enabled = selected_kind == "node" and selected_node_item is not None
            node_type = (
                str((selected_node_item.node or {}).get("nodeType") or "").strip().lower()
                if selected_node_item is not None
                else ""
            )
            evaluator_selected = selected_kind == "node" and node_type == "evaluator"
            if source_combo is not None:
                source_combo.setEnabled(connection_enabled and source_combo.count() > 0)
            if target_combo is not None:
                target_combo.setEnabled(connection_enabled and target_combo.count() > 0)
            if isinstance(connect_btn_widget, QPushButton):
                allow_connect = bool(source_combo and target_combo and source_combo.count() > 0 and target_combo.count() > 0)
                connect_btn_widget.setEnabled(connection_enabled and allow_connect)
            if isinstance(apply_btn, QPushButton):
                apply_btn.setEnabled(selected_kind == "edge" and selected_edge_item is not None)
            output_id_input = _get_drawer_text_field("workflow_new_output_id")
            output_value1_input = _get_drawer_text_field("workflow_new_output_value1")
            output_value2_input = _get_drawer_text_field("workflow_new_output_value2")
            output_mode_select = _get_drawer_select("workflow_new_output_mode")
            output_operator_select = _get_drawer_select("workflow_new_output_operator")
            if output_id_input is not None:
                output_id_input.setEnabled(evaluator_selected)
            if output_value1_input is not None:
                output_value1_input.setEnabled(evaluator_selected)
            if output_value2_input is not None:
                output_value2_input.setEnabled(evaluator_selected)
            if output_mode_select is not None:
                output_mode_select.setEnabled(evaluator_selected)
            if output_operator_select is not None:
                output_operator_select.setEnabled(evaluator_selected)
            if isinstance(add_output_btn, QPushButton):
                add_output_btn.setEnabled(evaluator_selected)

        def update_system_drawer(*, selection_kind: str, node: dict[str, Any] | None = None, edge: dict[str, Any] | None = None) -> None:
            nonlocal selected_kind
            surfaces = getattr(app_instance, "_surfaces", None)
            if surfaces is None:
                return

            normalized_kind = selection_kind if selection_kind in {"node", "edge"} else "none"
            selected_kind = normalized_kind
            if normalized_kind == "none":
                try:
                    surfaces.handle_delete_surface({"surfaceId": "drawer"})
                except Exception:
                    pass
                return

            node_type = ""
            if normalized_kind == "node":
                node_type = str((node or {}).get("nodeType") or "")
            defs = (
                _resolve_drawer_defs(selection_drawer_components, selection_kind=normalized_kind, node_type=node_type)
                if normalized_kind in {"node", "edge"}
                else []
            )

            source_options, target_options = _build_connection_options(node if normalized_kind == "node" else None)
            source_default = source_options[0]["value"] if source_options else ""
            target_default = target_options[0]["value"] if target_options else ""

            if not defs:
                defs = [
                    {"id": "wf_drawer_title", "component": {"Text": {"text": {"literalString": "Selection"}}}},
                    {"id": "workflow_selection_kind", "component": {"Text": {"text": {"literalString": "Type: {{selection.kind}}"}}}},
                    {"id": "workflow_prop_id", "component": {"Text": {"text": {"literalString": "ID: {{selection.id_label}}"}}}},
                    {"id": "workflow_prop_type", "component": {"Text": {"text": {"literalString": "Node Type: {{selection.node_type_label}}"}}}},
                    {"id": "workflow_prop_status", "component": {"Text": {"text": {"literalString": "Status: {{selection.status}}"}}}},
                    {"id": "workflow_prop_io", "component": {"Text": {"text": {"literalString": "I/O: {{selection.io_label}}"}}}},
                    {"id": "workflow_edge_info", "component": {"Text": {"text": {"literalString": "Connection: {{selection.connection_label}}"}}}},
                    {"id": "workflow_cfg_title", "component": {"Text": {"text": {"literalString": "Node Config"}}}},
                    {"id": "workflow_prop_config", "component": {"Markdown": {"text": {"literalString": "```json\n{{selection.config_json}}\n```"}}}},
                    {"id": "workflow_mapping_title", "component": {"Text": {"text": {"literalString": "Edge Param Mapping"}}}},
                    {
                        "id": "workflow_edge_mapping",
                        "component": {
                            "TextField": {
                                "label": {"literalString": ""},
                                "value": "{{selection.mapping_json_inline}}",
                                "placeholder": '{"target_param":"source_param"}',
                            }
                        },
                    },
                    {"id": "workflow_apply_mapping_btn", "component": {"Button": {"label": {"literalString": "Apply Mapping"}, "variant": "default"}}},
                    {"id": "workflow_connect_title", "component": {"Text": {"text": {"literalString": "Create Connection"}}}},
                    {
                        "id": "workflow_connect_source_output",
                        "component": {
                            "Select": {
                                "label": {"literalString": ""},
                                "options": "{{selection.connect_source_options}}",
                                "value": "{{selection.connect_source_value}}",
                                "placeholder": "Select source output",
                            }
                        },
                    },
                    {
                        "id": "workflow_connect_target_node",
                        "component": {
                            "Select": {
                                "label": {"literalString": ""},
                                "options": "{{selection.connect_target_options}}",
                                "value": "{{selection.connect_target_value}}",
                                "placeholder": "Select target node",
                            }
                        },
                    },
                    {"id": "workflow_connect_btn", "component": {"Button": {"label": {"literalString": "Connect Output"}, "variant": "default"}}},
                    {"id": "workflow_conditional_outputs_title", "component": {"Text": {"text": {"literalString": "Conditional Outputs (Evaluator)"}}}},
                    {
                        "id": "workflow_new_output_id",
                        "component": {
                            "TextField": {
                                "label": {"literalString": ""},
                                "value": "",
                                "placeholder": "Output id (es. high_priority)",
                            }
                        },
                    },
                    {
                        "id": "workflow_new_output_mode",
                        "component": {
                            "Select": {
                                "label": {"literalString": ""},
                                "options": [
                                    {"label": "AND", "value": "AND"},
                                    {"label": "OR", "value": "OR"},
                                ],
                                "value": "AND",
                                "placeholder": "Mode",
                            }
                        },
                    },
                    {
                        "id": "workflow_new_output_value1",
                        "component": {
                            "TextField": {
                                "label": {"literalString": ""},
                                "value": "",
                                "placeholder": "Value 1 (es. payload.score)",
                            }
                        },
                    },
                    {
                        "id": "workflow_new_output_operator",
                        "component": {
                            "Select": {
                                "label": {"literalString": ""},
                                "options": [
                                    {"label": "==", "value": "=="},
                                    {"label": "!=", "value": "!="},
                                    {"label": ">", "value": ">"},
                                    {"label": "<", "value": "<"},
                                    {"label": ">=", "value": ">="},
                                    {"label": "<=", "value": "<="},
                                    {"label": "in", "value": "in"},
                                    {"label": "contains", "value": "contains"},
                                ],
                                "value": "==",
                                "placeholder": "Operator",
                            }
                        },
                    },
                    {
                        "id": "workflow_new_output_value2",
                        "component": {
                            "TextField": {
                                "label": {"literalString": ""},
                                "value": "",
                                "placeholder": "Value 2 (es. 80)",
                            }
                        },
                    },
                    {
                        "id": "workflow_add_conditional_output_btn",
                        "component": {
                            "Button": {
                                "label": {"literalString": "Add Conditional Output"},
                                "variant": "default",
                            }
                        },
                    },
                ]
                for tool_def in tools_components:
                    if isinstance(tool_def, dict):
                        defs.append(copy.deepcopy(tool_def))

            context = {
                "selection.kind": normalized_kind if normalized_kind != "none" else "-",
                "selection.id": str((node or {}).get("id") or ""),
                "selection.id_label": str((node or {}).get("id") or "-") if normalized_kind == "node" else (f"{str((edge or {}).get('source') or '')} -> {str((edge or {}).get('target') or '')}" if normalized_kind == "edge" else "-"),
                "selection.node_type": str((node or {}).get("nodeType") or ""),
                "selection.node_type_label": str((node or {}).get("nodeType") or "-") if normalized_kind == "node" else (f"output={str((edge or {}).get('sourceOutput') or '')}" if normalized_kind == "edge" else "-"),
                "selection.status": str((node or {}).get("status") or "-"),
                "selection.config_json": json.dumps((node or {}).get("config") or {}, indent=2, sort_keys=True) if normalized_kind == "node" else "Select a node to inspect config",
                "selection.source": str((edge or {}).get("source") or ""),
                "selection.target": str((edge or {}).get("target") or ""),
                "selection.source_output": str((edge or {}).get("sourceOutput") or ""),
                "selection.mapping_json": json.dumps((edge or {}).get("mapping") or {}, indent=2, sort_keys=True) if normalized_kind == "edge" else "{}",
                "selection.mapping_json_inline": json.dumps((edge or {}).get("mapping") or {}, sort_keys=True) if normalized_kind == "edge" else "",
                "selection.connect_source_options": source_options,
                "selection.connect_target_options": target_options,
                "selection.connect_source_value": source_default,
                "selection.connect_target_value": target_default,
                "selection.io_label": "",
                "selection.connection_label": "",
            }
            if normalized_kind == "node":
                input_params = list((node or {}).get("input", {}).get("params") or [])
                output_ids = [str(o.get("id") or "") for o in list((node or {}).get("outputs") or [])]
                context["selection.io_label"] = (
                    "in(" + ", ".join(input_params or ["-"]) + ") -> out(" + ", ".join(output_ids or ["-"]) + ")"
                )
                context["selection.connection_label"] = "-"
            elif normalized_kind == "edge":
                source_node = nodes_by_id.get(str((edge or {}).get("source") or ""), {})
                target_node = nodes_by_id.get(str((edge or {}).get("target") or ""), {})
                source_out = str((edge or {}).get("sourceOutput") or "")
                source_params: list[str] = []
                for output in list(source_node.get("outputs") or []):
                    if str(output.get("id") or "") == source_out:
                        source_params = list(output.get("params") or [])
                        break
                target_params = list(((target_node.get("input") or {}).get("params") or []))
                context["selection.io_label"] = (
                    "out(" + ", ".join(source_params or ["-"]) + ") -> in(" + ", ".join(target_params or ["-"]) + ")"
                )
                context["selection.connection_label"] = "map target_param <- source_param"
            else:
                context["selection.io_label"] = "-"
                context["selection.connection_label"] = "-"

            components: list[dict[str, Any]] = []
            child_ids: list[str] = []
            for index, raw in enumerate(defs):
                comp_def = _apply_context_templates(copy.deepcopy(raw), context)
                if not isinstance(comp_def, dict):
                    continue
                if not isinstance(comp_def.get("id"), str) or not str(comp_def.get("id") or "").strip():
                    _ensure_component_ids(comp_def, f"{comp_id}_drawer_{selection_kind}_{index}")
                cid = str(comp_def.get("id") or "")
                if not cid:
                    continue
                child_ids.append(cid)
                components.append(comp_def)

            if not child_ids:
                return

            content_id = f"{comp_id}_drawer_content"
            content = {
                "id": content_id,
                "component": {
                    "Column": {
                        "spacing": 10,
                    }
                },
                "children": {"explicitList": child_ids},
            }
            components.append(content)

            root_id = f"{comp_id}_drawer_root"
            root = {
                "id": root_id,
                "component": {
                    "ScrollArea": {
                        "style": (
                            f"background-color: {_W['surface.panel']}; "
                            f"border-left: 1px solid {_W['border.soft']};"
                        ),
                        "content_style": (
                            f"background-color: {_W['surface.panel']}; "
                            "padding: 16px;"
                        ),
                    }
                },
                "children": {"explicitList": [content_id]},
            }
            components.append(root)

            try:
                surfaces.handle_surface_update({"surfaceId": "drawer", "components": components})
                surfaces.handle_begin_rendering({"surfaceId": "drawer", "root": root_id})
                _bind_drawer_handlers()
            except Exception:
                return

        def remove_edge_item(edge_item: _WorkflowEdgeItem) -> None:
            nonlocal selected_edge_item
            if edge_item in edge_items:
                edge_items.remove(edge_item)
            edge = edge_item.edge
            if edge in edges:
                edges.remove(edge)
            if selected_edge_item is edge_item:
                selected_edge_item = None
            try:
                scene.removeItem(edge_item)
            except RuntimeError:
                pass
            try:
                scene.removeItem(edge_item._label_item)
            except RuntimeError:
                pass

        def remove_node_item(node_item: _WorkflowNodeItem) -> None:
            nonlocal selected_node_item
            node_id = str(node_item.node.get("id") or "")
            connected_edges = [
                edge_item
                for edge_item in list(edge_items)
                if str(edge_item.edge.get("source")) == node_id or str(edge_item.edge.get("target")) == node_id
            ]
            for edge_item in connected_edges:
                remove_edge_item(edge_item)
            if node_id in node_items:
                node_items.pop(node_id, None)
            nodes_by_id.pop(node_id, None)
            nodes[:] = [node for node in nodes if str(node.get("id") or "") != node_id]
            if selected_node_item is node_item:
                selected_node_item = None
            try:
                scene.removeItem(node_item)
            except RuntimeError:
                pass

        def create_edge(
            *,
            source_item: _WorkflowNodeItem,
            source_output: str,
            target_id: str,
            auto_select: bool = True,
        ) -> bool:
            source_node = source_item.node
            source_id = str(source_node.get("id") or "")
            if not source_id or not source_output or not target_id or target_id not in nodes_by_id:
                return False
            if target_id == source_id:
                return False

            for edge in edges:
                if (
                    str(edge.get("source")) == source_id
                    and str(edge.get("target")) == target_id
                    and str(edge.get("sourceOutput") or "") == source_output
                ):
                    return False

            source_output_params: list[str] = []
            for output in list(source_node.get("outputs") or []):
                if str(output.get("id") or "") == source_output:
                    source_output_params = list(output.get("params") or [])
                    break
            target_input_params = list((nodes_by_id[target_id].get("input") or {}).get("params") or [])
            mapping: dict[str, str] = {}
            for target_param in target_input_params:
                if target_param in source_output_params:
                    mapping[str(target_param)] = str(target_param)

            edge = {
                "source": source_id,
                "target": target_id,
                "sourceOutput": source_output,
                "label": source_output,
                "mapping": mapping,
            }
            edges.append(edge)

            target_item = node_items.get(target_id)
            if target_item is None:
                return False
            edge_item = _WorkflowEdgeItem(edge=edge, source=source_item, target=target_item)
            edge_item.attach_to_scene(scene)
            edge_items.append(edge_item)
            refresh_edges()
            if auto_select:
                scene.clearSelection()
                edge_item.setSelected(True)
            return True

        def _resolve_drop_target(scene_pos: QPointF) -> _WorkflowNodeItem | None:
            for item in scene.items(scene_pos):
                if isinstance(item, _WorkflowNodeItem):
                    return item
                parent = item.parentItem()
                while parent is not None:
                    if isinstance(parent, _WorkflowNodeItem):
                        return parent
                    parent = parent.parentItem()
            return None

        def _update_drag_path(scene_pos: QPointF) -> None:
            if active_drag_source is None or not active_drag_output:
                return
            start = active_drag_source.out_anchor(active_drag_output)
            end = scene_pos
            dx = max(50.0, abs(end.x() - start.x()) * 0.45)
            ctrl1 = QPointF(start.x() + dx, start.y())
            ctrl2 = QPointF(end.x() - dx, end.y())
            path = QPainterPath(start)
            path.cubicTo(ctrl1, ctrl2, end)
            if active_drag_path is None:
                return
            active_drag_path.setPath(path)

        def _on_output_drag_start(node_item: _WorkflowNodeItem, output_id: str, scene_pos: QPointF) -> None:
            nonlocal active_drag_source, active_drag_output, active_drag_path
            active_drag_source = node_item
            active_drag_output = str(output_id or "")
            if active_drag_path is not None:
                try:
                    scene.removeItem(active_drag_path)
                except RuntimeError:
                    pass
                active_drag_path = None
            active_drag_path = QGraphicsPathItem()
            drag_pen = QPen(QColor(_W["accent.alt"]), 2.0, Qt.PenStyle.DashLine)
            drag_pen.setCapStyle(Qt.RoundCap)
            drag_pen.setJoinStyle(Qt.RoundJoin)
            active_drag_path.setPen(drag_pen)
            active_drag_path.setZValue(3)
            scene.addItem(active_drag_path)
            _update_drag_path(scene_pos)

        def _on_output_drag_move(scene_pos: QPointF) -> None:
            _update_drag_path(scene_pos)

        def _on_output_drag_release(scene_pos: QPointF) -> None:
            nonlocal active_drag_source, active_drag_output, active_drag_path
            source_item = active_drag_source
            source_output = active_drag_output
            target_item = _resolve_drop_target(scene_pos)
            if active_drag_path is not None:
                try:
                    scene.removeItem(active_drag_path)
                except RuntimeError:
                    pass
            active_drag_path = None
            active_drag_source = None
            active_drag_output = ""
            if source_item is None or not source_output or target_item is None:
                return
            target_id = str(target_item.node.get("id") or "")
            create_edge(source_item=source_item, source_output=source_output, target_id=target_id, auto_select=True)

        for node in nodes:
            item = _WorkflowNodeItem(
                node,
                width=node_w,
                height=node_h,
                on_move=refresh_edges,
                on_output_drag_start=_on_output_drag_start,
                on_output_drag_move=_on_output_drag_move,
                on_output_drag_release=_on_output_drag_release,
            )
            pos = positions.get(node["id"], QPointF(80, 80))
            item.setPos(pos)
            scene.addItem(item)
            node_items[node["id"]] = item

        for edge in edges:
            source = node_items.get(edge["source"])
            target = node_items.get(edge["target"])
            if source is None or target is None:
                continue
            edge_item = _WorkflowEdgeItem(edge=edge, source=source, target=target)
            edge_item.attach_to_scene(scene)
            edge_items.append(edge_item)

        def set_default_panel() -> None:
            update_system_drawer(selection_kind="none")

        def set_node_panel(item: _WorkflowNodeItem) -> None:
            node = item.node
            update_system_drawer(selection_kind="node", node=node)

        def set_edge_panel(item: _WorkflowEdgeItem) -> None:
            edge = item.edge
            update_system_drawer(selection_kind="edge", edge=edge)

        def on_selection_changed() -> None:
            nonlocal selected_node_item, selected_edge_item
            try:
                selected_node_item = None
                selected_edge_item = None
                for edge_item in edge_items:
                    edge_item.update_visual()

                selected = scene.selectedItems()
                for item in selected:
                    if isinstance(item, _WorkflowNodeItem):
                        selected_node_item = item
                        set_node_panel(item)
                        return
                    if isinstance(item, _WorkflowEdgeItem):
                        selected_edge_item = item
                        item.update_visual()
                        set_edge_panel(item)
                        return
                set_default_panel()
            except RuntimeError:
                return

        def apply_auto_layout() -> None:
            layout_positions = _auto_positions(nodes, edges, node_w=node_w, node_h=node_h)
            for node in nodes:
                item = node_items.get(node["id"])
                if item is not None:
                    item.setPos(layout_positions[node["id"]])
            refresh_edges()
            view.fit_scene()

        def fit_canvas() -> None:
            view.resetTransform()
            view._zoom = 0
            view.fit_scene()

        def add_component_from_template(template: dict[str, Any] | None) -> None:
            if template is None:
                return
            index = len(nodes) + 1
            base_id = str(template.get("id") or "component").strip() or "component"
            node_id = f"{base_id}_{index}"
            existing = {node["id"] for node in nodes}
            while node_id in existing:
                index += 1
                node_id = f"{base_id}_{index}"

            center_scene = view.mapToScene(view.viewport().rect().center())
            input_spec = template.get("input")
            if not isinstance(input_spec, dict):
                input_spec = {}
            outputs = template.get("outputs")
            if not isinstance(outputs, list) or not outputs:
                outputs = [{"id": "out_1", "label": "out_1", "params": []}]
            node = {
                "id": node_id,
                "label": str(template.get("label") or f"Component {index}"),
                "nodeType": str(template.get("nodeType") or "component"),
                "status": str(template.get("status") or "ready"),
                "fill": _safe_color(template.get("fill"), _W["node.fill"]),
                "stroke": _safe_color(template.get("stroke"), _W["node.stroke"]),
                "textColor": _safe_color(template.get("textColor"), _W["node.text"]),
                "config": copy.deepcopy(template.get("config") or {}),
                "input": {"params": _normalize_param_list(input_spec.get("params"))},
                "outputs": copy.deepcopy(outputs),
                "allowAddOutput": bool(template.get("allowAddOutput", True)),
                "cascadeDeleteConnected": bool(
                    template.get(
                        "cascadeDeleteConnected",
                        str(template.get("nodeType") or "component").strip().lower() == "component",
                    )
                ),
                "x": center_scene.x(),
                "y": center_scene.y(),
            }

            nodes.append(node)
            nodes_by_id[node_id] = node
            item = _WorkflowNodeItem(
                node,
                width=node_w,
                height=node_h,
                on_move=refresh_edges,
                on_output_drag_start=_on_output_drag_start,
                on_output_drag_move=_on_output_drag_move,
                on_output_drag_release=_on_output_drag_release,
            )
            item.setPos(QPointF(center_scene.x() - node_w / 2, center_scene.y() - node_h / 2))
            scene.addItem(item)
            node_items[node_id] = item
            scene.clearSelection()
            item.setSelected(True)
            refresh_edges()

        def add_component_from_modal() -> None:
            selected_key = _get_modal_selected_key()
            template = copy.deepcopy(template_lookup.get(selected_key))
            if template is None:
                return
            add_component_from_template(template)
            _close_add_modal()

        def add_component_from_ui() -> None:
            template: dict[str, Any] | None = None
            if toolbar_picker_combo is not None:
                selected = toolbar_picker_combo.currentData()
                if isinstance(selected, str) and selected in catalog_by_id:
                    template = copy.deepcopy(catalog_by_id[selected])
                elif isinstance(selected, dict):
                    template = copy.deepcopy(selected)
            if template is None and component_templates:
                template = copy.deepcopy(component_templates[0])
            add_component_from_template(template)

        def connect_selected_output() -> None:
            nonlocal selected_node_item
            source_item = selected_node_item
            if source_item is None:
                return
            source_combo = _get_drawer_select("workflow_connect_source_output")
            target_combo = _get_drawer_select("workflow_connect_target_node")
            source_output = str(source_combo.currentData() if source_combo is not None else "").strip()
            target_id = str(target_combo.currentData() if target_combo is not None else "").strip()
            create_edge(source_item=source_item, source_output=source_output, target_id=target_id, auto_select=True)

        def add_conditional_output() -> None:
            nonlocal selected_node_item
            source_item = selected_node_item
            if source_item is None:
                return
            node = source_item.node
            node_type = str(node.get("nodeType") or "").strip().lower()
            if node_type != "evaluator":
                return

            output_id_input = _get_drawer_text_field("workflow_new_output_id")
            output_mode_select = _get_drawer_select("workflow_new_output_mode")
            output_value1_input = _get_drawer_text_field("workflow_new_output_value1")
            output_operator_select = _get_drawer_select("workflow_new_output_operator")
            output_value2_input = _get_drawer_text_field("workflow_new_output_value2")
            raw_output_id = str(output_id_input.text() if output_id_input is not None else "").strip()
            mode = str(output_mode_select.currentData() if output_mode_select is not None else "AND").strip().upper()
            value1 = str(output_value1_input.text() if output_value1_input is not None else "").strip()
            operator = str(output_operator_select.currentData() if output_operator_select is not None else "==").strip()
            value2 = str(output_value2_input.text() if output_value2_input is not None else "").strip()
            if not raw_output_id:
                return

            candidate = raw_output_id.replace(" ", "_")
            existing_ids = {
                str(out.get("id") or "").strip()
                for out in list(node.get("outputs") or [])
                if isinstance(out, dict)
            }
            output_id = candidate
            suffix = 2
            while output_id in existing_ids:
                output_id = f"{candidate}_{suffix}"
                suffix += 1

            output_def = {
                "id": output_id,
                "label": output_id,
                "params": [],
            }
            if value1 and value2 and operator:
                condition_rule = {
                    "operator": mode if mode in {"AND", "OR"} else "AND",
                    "conditions": [
                        {
                            "value1": value1,
                            "operator": operator,
                            "value2": value2,
                        }
                    ],
                }
                # Reuse the existing evaluator helper to keep rule shape compatible.
                _ = evaluate_visibility_rule(condition_rule, app_instance, None, default=True)
                output_def["when"] = condition_rule

            source_item.add_output(output_def)
            refresh_edges()
            update_system_drawer(selection_kind="node", node=node)

            if output_id_input is not None:
                output_id_input.setText("")
            if output_value1_input is not None:
                output_value1_input.setText("")
            if output_value2_input is not None:
                output_value2_input.setText("")

        def apply_edge_mapping() -> None:
            nonlocal selected_edge_item
            item = selected_edge_item
            if item is None:
                return
            mapping_input = _get_drawer_text_field("workflow_edge_mapping")
            raw = str(mapping_input.text() if mapping_input is not None else "").strip()
            if not raw:
                item.edge["mapping"] = {}
                item.update_path()
                set_edge_panel(item)
                return
            try:
                parsed = json.loads(raw)
            except Exception:
                return
            if not isinstance(parsed, dict):
                return
            item.edge["mapping"] = _normalize_mapping(parsed)
            item.update_path()
            set_edge_panel(item)

        def delete_selection() -> None:
            nonlocal selected_node_item, selected_edge_item
            try:
                selected_items = list(scene.selectedItems())
            except RuntimeError:
                return
            selected_nodes = [item for item in selected_items if isinstance(item, _WorkflowNodeItem)]
            selected_edges = [item for item in selected_items if isinstance(item, _WorkflowEdgeItem)]

            if selected_nodes:
                node_ids_to_remove: set[str] = set()
                for node_item in selected_nodes:
                    node_id = str(node_item.node.get("id") or "")
                    if node_id:
                        node_ids_to_remove.add(node_id)
                    cascade = bool(
                        node_item.node.get(
                            "cascadeDeleteConnected",
                            str(node_item.node.get("nodeType") or "").strip().lower() == "component",
                        )
                    )
                    if not cascade:
                        continue
                    for edge in list(edges):
                        source_id = str(edge.get("source") or "")
                        target_id = str(edge.get("target") or "")
                        if source_id == node_id and target_id:
                            node_ids_to_remove.add(target_id)
                        elif target_id == node_id and source_id:
                            node_ids_to_remove.add(source_id)

                for node_id in list(node_ids_to_remove):
                    node_item = node_items.get(node_id)
                    if node_item is not None:
                        remove_node_item(node_item)

                scene.clearSelection()
                selected_node_item = None
                selected_edge_item = None
                refresh_edges()
                set_default_panel()
                return

            if selected_edges:
                for edge_item in list(selected_edges):
                    remove_edge_item(edge_item)
                scene.clearSelection()
                selected_edge_item = None
                refresh_edges()
                set_default_panel()

        add_embedded_components(toolbar_layout, toolbar_components, "toolbar", preserve_ids=True)

        toolbar_picker_combo = toolbar.findChild(QComboBox, "wf_toolbar_component_picker__input")
        toolbar_add_btn = toolbar.findChild(QPushButton, "wf_toolbar_add_component_btn")
        toolbar_auto_btn = toolbar.findChild(QPushButton, "wf_toolbar_auto_layout_btn")
        toolbar_fit_btn = toolbar.findChild(QPushButton, "wf_toolbar_fit_btn")

        if toolbar_picker_combo is None:
            toolbar_picker_combo = QComboBox()
            toolbar_picker_combo.setObjectName("wf_toolbar_component_picker__input")
            for template_id, template in catalog_by_id.items():
                toolbar_picker_combo.addItem(str(template.get("label") or template_id), template_id)
            toolbar_layout.insertWidget(1, toolbar_picker_combo)
        toolbar_picker_combo.setMinimumWidth(180)

        if toolbar_add_btn is None:
            toolbar_add_btn = QPushButton("Add Component")
            toolbar_add_btn.setObjectName("wf_toolbar_add_component_btn")
            toolbar_layout.addWidget(toolbar_add_btn)
        if toolbar_auto_btn is None:
            toolbar_auto_btn = QPushButton("Auto Layout")
            toolbar_auto_btn.setObjectName("wf_toolbar_auto_layout_btn")
            toolbar_layout.addWidget(toolbar_auto_btn)
        if toolbar_fit_btn is None:
            toolbar_fit_btn = QPushButton("Fit")
            toolbar_fit_btn.setObjectName("wf_toolbar_fit_btn")
            toolbar_layout.addWidget(toolbar_fit_btn)

        scene.selectionChanged.connect(on_selection_changed)
        if toolbar_auto_btn is not None:
            toolbar_auto_btn.clicked.connect(apply_auto_layout)
        if toolbar_fit_btn is not None:
            toolbar_fit_btn.clicked.connect(fit_canvas)
        if toolbar_add_btn is not None:
            toolbar_add_btn.clicked.connect(open_add_component_modal)
        view.set_delete_handler(delete_selection)

        refresh_edges()
        set_default_panel()
        return container
