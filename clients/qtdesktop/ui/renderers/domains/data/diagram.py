from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
import re
from typing import Any, Dict

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer
from ....theme.tokens import theme_token, themed_status_color

try:
    from PySide6.QtQuickWidgets import QQuickWidget
    from PySide6.QtQml import QQmlContext

    QT_QUICK_AVAILABLE = True
except Exception:
    QQuickWidget = None
    QQmlContext = None
    QT_QUICK_AVAILABLE = False


_FLOW_EDGE_RE = re.compile(
    r"^(?P<src>.+?)\s*(?:-->|---|-.->|==>)\s*(?:\|(?P<label>[^|]+)\|)?\s*(?P<dst>.+)$"
)

_D = {
    "node.fill": theme_token("diagram.node.fill"),
    "node.stroke": theme_token("diagram.node.stroke"),
    "node.text": theme_token("diagram.node.text"),
    "surface.base": theme_token("data.surface.base"),
    "border.soft": theme_token("data.border.soft"),
    "text.muted": theme_token("data.text.muted"),
    "text.primary": theme_token("data.text.primary"),
    "accent": theme_token("data.accent"),
}


def _extract_flow_node(text: str) -> dict[str, str] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    match = re.match(r"^(?P<id>[A-Za-z0-9_.:-]+)", raw)
    if not match:
        return None
    node_id = match.group("id")
    remainder = raw[match.end() :].strip()
    label = node_id
    shape = "process"
    if remainder.startswith("((") and "))" in remainder:
        label = remainder[2 : remainder.index("))")].strip() or node_id
        shape = "terminal"
    elif remainder.startswith("{") and "}" in remainder:
        label = remainder[1 : remainder.index("}")].strip() or node_id
        shape = "diamond"
    elif remainder.startswith("[") and "]" in remainder:
        label = remainder[1 : remainder.index("]")].strip() or node_id
    elif remainder.startswith("(") and ")" in remainder:
        label = remainder[1 : remainder.index(")")].strip() or node_id
    return {"id": node_id, "label": label, "shape": shape}


def _parse_mermaid_flowchart(mermaid: str) -> dict[str, Any]:
    text = str(mermaid or "").strip()
    if not text:
        return {"nodes": [], "edges": [], "direction": "LR"}
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("%%")]
    if not lines:
        return {"nodes": [], "edges": [], "direction": "LR"}

    direction = "LR"
    header = lines[0].lower()
    if header.startswith("flowchart") or header.startswith("graph"):
        parts = lines[0].split()
        if len(parts) > 1:
            raw_dir = parts[1].upper()
            if raw_dir in {"TB", "TD"}:
                direction = "TB"
            elif raw_dir in {"LR", "RL"}:
                direction = "LR"
        lines = lines[1:]

    node_order: list[str] = []
    nodes: dict[str, dict[str, str]] = {}
    edges: list[dict[str, str]] = []
    for line in lines:
        if line.lower().startswith(("subgraph ", "end", "linkstyle ", "classdef ", "class ", "style ")):
            continue
        edge_match = _FLOW_EDGE_RE.match(line)
        if edge_match:
            src_node = _extract_flow_node(edge_match.group("src"))
            dst_node = _extract_flow_node(edge_match.group("dst"))
            if not src_node or not dst_node:
                continue
            for node in (src_node, dst_node):
                if node["id"] not in nodes:
                    nodes[node["id"]] = node
                    node_order.append(node["id"])
            edges.append(
                {
                    "source": src_node["id"],
                    "target": dst_node["id"],
                    "label": str(edge_match.group("label") or "").strip(),
                }
            )
            continue
        node = _extract_flow_node(line)
        if node and node["id"] not in nodes:
            nodes[node["id"]] = node
            node_order.append(node["id"])

    return {
        "nodes": [nodes[node_id] for node_id in node_order],
        "edges": edges,
        "direction": direction,
    }


def _resolve_flow_input(props: Dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    nodes = list(props.get("nodes") or [])
    edges = list(props.get("edges") or [])
    direction = str(props.get("direction") or "LR").upper()
    if nodes or edges:
        return nodes, edges, direction
    parsed = _parse_mermaid_flowchart(str(props.get("mermaid") or ""))
    parsed_direction = str(parsed.get("direction") or direction).upper()
    return list(parsed.get("nodes") or []), list(parsed.get("edges") or []), parsed_direction


def _normalize_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    allowed_shapes = {"process", "diamond", "terminal"}
    for index, raw in enumerate(nodes):
        if not isinstance(raw, dict):
            continue
        node_id = str(raw.get("id") or f"node_{index}").strip()
        if not node_id:
            continue
        shape = str(raw.get("shape") or "process").strip().lower()
        if shape not in allowed_shapes:
            shape = "process"
        normalized.append(
            {
                "id": node_id,
                "label": str(raw.get("label") or node_id).strip() or node_id,
                "fill": str(raw.get("fill") or _D["node.fill"]),
                "stroke": str(raw.get("stroke") or _D["node.stroke"]),
                "textColor": str(raw.get("textColor") or _D["node.text"]),
                "lane": str(raw.get("lane") or "").strip(),
                "status": str(raw.get("status") or "").strip().lower(),
                "shape": shape,
            }
        )
    return normalized


def _normalize_edges(edges: list[dict[str, Any]], node_ids: set[str]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for raw in edges:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or raw.get("from") or "").strip()
        target = str(raw.get("target") or raw.get("to") or "").strip()
        if not source or not target or source not in node_ids or target not in node_ids:
            continue
        normalized.append(
            {
                "source": source,
                "target": target,
                "label": str(raw.get("label") or "").strip(),
            }
        )
    return normalized


def _compute_levels(nodes: list[dict[str, Any]], edges: list[dict[str, str]]) -> dict[str, int]:
    node_ids = [node["id"] for node in nodes]
    incoming: dict[str, int] = {node_id: 0 for node_id in node_ids}
    outgoing: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        outgoing[edge["source"]].append(edge["target"])
        incoming[edge["target"]] = incoming.get(edge["target"], 0) + 1

    levels: dict[str, int] = {node_id: 0 for node_id in node_ids}
    queue = deque(node_id for node_id in node_ids if incoming.get(node_id, 0) == 0)
    visited: set[str] = set()
    while queue:
        node_id = queue.popleft()
        visited.add(node_id)
        for child_id in outgoing.get(node_id, []):
            levels[child_id] = max(levels.get(child_id, 0), levels.get(node_id, 0) + 1)
            incoming[child_id] -= 1
            if incoming[child_id] == 0:
                queue.append(child_id)

    max_level = max(levels.values(), default=0)
    for node_id in node_ids:
        if node_id not in visited:
            max_level += 1
            levels[node_id] = max_level
    return levels


def _compute_branch_order(nodes: list[dict[str, Any]], edges: list[dict[str, str]], levels: dict[str, int]) -> dict[str, float]:
    node_ids = [node["id"] for node in nodes]
    outgoing: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, int] = {node_id: 0 for node_id in node_ids}
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        if levels.get(target, 0) <= levels.get(source, 0):
            continue
        outgoing[source].append(target)
        incoming[target] = incoming.get(target, 0) + 1

    roots = [node_id for node_id in node_ids if incoming.get(node_id, 0) == 0] or list(node_ids)
    leaf_counter = 0
    memo: dict[str, float] = {}
    visiting: set[str] = set()

    def _assign(node_id: str) -> float:
        nonlocal leaf_counter
        if node_id in memo:
            return memo[node_id]
        if node_id in visiting:
            order = float(leaf_counter)
            leaf_counter += 1
            memo[node_id] = order
            return order

        visiting.add(node_id)
        children = [child_id for child_id in outgoing.get(node_id, []) if child_id != node_id]
        if not children:
            order = float(leaf_counter)
            leaf_counter += 1
        else:
            child_orders = [_assign(child_id) for child_id in children]
            order = sum(child_orders) / len(child_orders)
        visiting.remove(node_id)
        memo[node_id] = order
        return order

    for node_id in roots:
        _assign(node_id)
    for node_id in node_ids:
        _assign(node_id)
    return memo


def _wrap_label(text: str, width: int = 16) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        if len(current) + 1 + len(word) <= width:
            current = f"{current} {word}"
            continue
        lines.append(current)
        current = word
    lines.append(current)
    return lines[:3]


def _status_palette(status: str) -> dict[str, str]:
    key = str(status or "").strip().lower()
    if key == "running":
        return {"fill": _D["node.fill"], "stroke": themed_status_color("active")}
    if key == "success":
        return {"fill": _D["node.fill"], "stroke": themed_status_color("success")}
    if key == "warning":
        return {"fill": _D["node.fill"], "stroke": themed_status_color("warning")}
    if key == "error":
        return {"fill": _D["node.fill"], "stroke": themed_status_color("error")}
    if key == "queued":
        return {"fill": _D["node.fill"], "stroke": themed_status_color("planned")}
    return {}


def _measure_node_size(node: dict[str, Any], default_width: int, default_height: int) -> tuple[int, int]:
    lines = _wrap_label(node["label"], width=18)
    longest = max((len(line) for line in lines), default=8)
    width = max(default_width, min(280, 38 + longest * 8))
    height = max(default_height, 42 + len(lines) * 18)
    shape = str(node.get("shape") or "process").lower()
    if shape == "diamond":
        width = int(max(width + 18, height * 1.35))
        height = int(max(height + 10, width * 0.58))
    elif shape == "terminal":
        width = int(width + 12)
    return width, height


def layout_diagram(props: Dict[str, Any]) -> dict[str, Any]:
    raw_nodes, raw_edges, resolved_direction = _resolve_flow_input(props)
    nodes = _normalize_nodes(raw_nodes)
    if not nodes:
        return {
            "nodes": [],
            "edges": [],
            "positions": {},
            "scene_rect": QRectF(0.0, 0.0, 480.0, 220.0),
            "node_width": max(96, int(props.get("nodeWidth", 180))),
            "node_height": max(48, int(props.get("nodeHeight", 84))),
            "direction": resolved_direction,
        }

    node_ids = {node["id"] for node in nodes}
    edges = _normalize_edges(raw_edges, node_ids)
    direction = resolved_direction
    horizontal = direction != "TB"
    default_node_width = max(120, int(props.get("nodeWidth", 180)))
    default_node_height = max(68, int(props.get("nodeHeight", 84)))
    x_gap = 108
    y_gap = 68
    padding = 40
    lane_header = 34

    levels = _compute_levels(nodes, edges)
    branch_order = _compute_branch_order(nodes, edges, levels)
    lane_order: dict[str, int] = {}
    next_lane_index = 0
    for node in nodes:
        lane_name = node.get("lane", "")
        if lane_name and lane_name not in lane_order:
            lane_order[lane_name] = next_lane_index
            next_lane_index += 1
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        grouped[levels[node["id"]]].append(node)
    for level_nodes in grouped.values():
        level_nodes.sort(
            key=lambda node: (
                lane_order.get(node.get("lane", ""), 10_000),
                branch_order.get(node["id"], 0.0),
                node["id"],
            )
        )
    ordered_levels = sorted(grouped)
    node_sizes = {
        node["id"]: _measure_node_size(node, default_node_width, default_node_height)
        for node in nodes
    }

    positions: dict[str, QPointF] = {}
    column_widths: dict[int, int] = {
        level: max((node_sizes[node["id"]][0] for node in grouped[level]), default=default_node_width)
        for level in ordered_levels
    }

    if horizontal:
        lane_names = [name for name, _ in sorted(lane_order.items(), key=lambda item: item[1])]
        if not lane_names:
            lane_names = [""]
        lane_heights: dict[str, int] = {}
        for lane_name in lane_names:
            lane_nodes = [node for node in nodes if (node.get("lane", "") or "") == lane_name]
            lane_heights[lane_name] = max(
                (node_sizes[node["id"]][1] for node in lane_nodes),
                default=default_node_height,
            )
        next_unlabeled_lane = len(lane_names)
        lane_row_indexes = dict(lane_order)
    else:
        lane_names = []
        lane_heights = {}
        next_unlabeled_lane = 0
        lane_row_indexes = {}

    x_positions: dict[int, float] = {}
    cursor_x = padding
    for level in ordered_levels:
        x_positions[level] = float(cursor_x)
        cursor_x += column_widths[level] + x_gap

    row_tops: dict[int, float] = {}
    if horizontal:
        lane_height_by_index: dict[int, int] = {}
        for lane_name, lane_index in lane_row_indexes.items():
            lane_height_by_index[lane_index] = lane_heights.get(lane_name, default_node_height)
        for node in nodes:
            lane_name = node.get("lane", "")
            if lane_name:
                continue
            lane_height_by_index.setdefault(next_unlabeled_lane, node_sizes[node["id"]][1])
            next_unlabeled_lane += 1
        cursor_y = padding
        max_lane_index = max(lane_height_by_index, default=0)
        for lane_index in range(max_lane_index + 1):
            row_tops[lane_index] = float(cursor_y)
            cursor_y += lane_header + lane_height_by_index.get(lane_index, default_node_height) + y_gap
    else:
        cursor_y = padding
        for level in ordered_levels:
            max_h = max((node_sizes[node["id"]][1] for node in grouped[level]), default=default_node_height)
            row_tops[level] = float(cursor_y)
            cursor_y += max_h + y_gap

    for level_index, level in enumerate(ordered_levels):
        lane = grouped[level]
        if horizontal and any(node.get("lane") for node in lane):
            used_lane_indexes: set[int] = set()
            fallback_index = max(lane_order.values(), default=-1) + 1
            lane_indexes: dict[str, int] = {}
            for node in lane:
                node_id = node["id"]
                explicit_lane = node.get("lane", "")
                if explicit_lane:
                    lane_indexes[node_id] = lane_order[explicit_lane]
                    used_lane_indexes.add(lane_indexes[node_id])
                    continue
                while fallback_index in used_lane_indexes:
                    fallback_index += 1
                lane_indexes[node_id] = fallback_index
                used_lane_indexes.add(fallback_index)
                fallback_index += 1
        else:
            lane_indexes = {node["id"]: lane_index for lane_index, node in enumerate(lane)}

        for node in lane:
            lane_index = lane_indexes[node["id"]]
            node_w, node_h = node_sizes[node["id"]]
            if horizontal:
                x = x_positions[level] + (column_widths[level] - node_w) / 2
                y = row_tops[lane_index] + lane_header + (lane_heights.get(node.get("lane", ""), default_node_height) - node_h) / 2
            else:
                x = padding + lane_index * (default_node_width + x_gap)
                y = row_tops[level]
            positions[node["id"]] = QPointF(float(x), float(y))

    width = cursor_x - x_gap + padding if ordered_levels else 480
    if horizontal:
        height = cursor_y - y_gap + padding if row_tops else 220
    else:
        height = cursor_y - y_gap + padding if ordered_levels else 220
    min_height = max(220, int(props.get("height", 360)))
    height = max(height, min_height)

    lane_bands: list[dict[str, Any]] = []
    if horizontal:
        lane_items = sorted(lane_row_indexes.items(), key=lambda item: item[1])
        for lane_name, lane_index in lane_items:
            top = row_tops[lane_index]
            band_height = lane_header + lane_heights.get(lane_name, default_node_height)
            lane_bands.append(
                {
                    "name": lane_name,
                    "rect": QRectF(float(padding * 0.5), top, float(max(width - padding, 240)), float(band_height)),
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "positions": positions,
        "scene_rect": QRectF(0.0, 0.0, float(width), float(height)),
        "node_width": default_node_width,
        "node_height": default_node_height,
        "node_sizes": node_sizes,
        "direction": direction,
        "lane_bands": lane_bands,
    }


def _build_quick_model(graph: dict[str, Any]) -> dict[str, Any]:
    nodes = []
    for node in graph["nodes"]:
        pos = graph["positions"][node["id"]]
        node_w, node_h = graph["node_sizes"][node["id"]]
        palette = _status_palette(node.get("status", ""))
        nodes.append(
            {
                "id": node["id"],
                "label": node["label"],
                "lane": node.get("lane", ""),
                "shape": node.get("shape", "process"),
                "x": float(pos.x()),
                "y": float(pos.y()),
                "width": int(node_w),
                "height": int(node_h),
                "fill": palette.get("fill", node["fill"]),
                "stroke": palette.get("stroke", node["stroke"]),
                "textColor": node["textColor"],
                "status": node.get("status", ""),
            }
        )

    edges = []
    for edge in graph["edges"]:
        source = graph["positions"][edge["source"]]
        target = graph["positions"][edge["target"]]
        source_w, source_h = graph["node_sizes"][edge["source"]]
        target_w, target_h = graph["node_sizes"][edge["target"]]
        path, label_pos = _build_edge_path(
            source,
            target,
            source_width=source_w,
            source_height=source_h,
            target_width=target_w,
            target_height=target_h,
            direction=graph["direction"],
        )
        points = []
        for index in range(path.elementCount()):
            element = path.elementAt(index)
            points.append({"x": float(element.x), "y": float(element.y)})
        target_node = next((node for node in graph["nodes"] if node["id"] == edge["target"]), None)
        target_status = str((target_node or {}).get("status") or "").strip().lower()
        edges.append(
            {
                "source": edge["source"],
                "target": edge["target"],
                "label": edge["label"],
                "points": points,
                "labelX": float(label_pos.x()),
                "labelY": float(label_pos.y()),
                "color": _status_palette(target_status).get("stroke", _D["node.stroke"]),
            }
        )

    lane_bands = []
    for band in graph.get("lane_bands", []):
        rect = band["rect"]
        lane_bands.append(
            {
                "name": band["name"],
                "x": float(rect.x()),
                "y": float(rect.y()),
                "width": float(rect.width()),
                "height": float(rect.height()),
            }
        )

    scene_rect = graph["scene_rect"]
    return {
        "width": float(scene_rect.width()),
        "height": float(scene_rect.height()),
        "nodes": nodes,
        "edges": edges,
        "lanes": lane_bands,
        "direction": graph["direction"],
    }


def _build_edge_path(
    source: QPointF,
    target: QPointF,
    *,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
    direction: str,
) -> tuple[QPainterPath, QPointF]:
    horizontal = direction != "TB"
    path = QPainterPath()
    if horizontal:
        start = QPointF(source.x() + source_width, source.y() + source_height / 2)
        end = QPointF(target.x(), target.y() + target_height / 2)
        mid_x = (start.x() + end.x()) / 2
        path.moveTo(start)
        path.lineTo(mid_x, start.y())
        path.lineTo(mid_x, end.y())
        path.lineTo(end)
        label_pos = QPointF(mid_x, min(start.y(), end.y()) - 18)
    else:
        start = QPointF(source.x() + source_width / 2, source.y() + source_height)
        end = QPointF(target.x() + target_width / 2, target.y())
        mid_y = (start.y() + end.y()) / 2
        path.moveTo(start)
        path.lineTo(start.x(), mid_y)
        path.lineTo(end.x(), mid_y)
        path.lineTo(end)
        label_pos = QPointF(max(start.x(), end.x()) + 18, mid_y - 8)
    return path, label_pos


class _DiagramView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(parent)
        self.setScene(scene)
        self._zoom = 0
        self._base_fit_applied = False
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor(_D["surface.base"]))

    def showEvent(self, event):
        super().showEvent(event)
        self._fit_scene()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._zoom == 0:
            self._fit_scene()

    def _fit_scene(self):
        scene = self.scene()
        if scene is None:
            return
        rect = scene.sceneRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            return
        self.fitInView(rect.adjusted(-24, -24, 24, 24), Qt.KeepAspectRatio)
        self._base_fit_applied = True

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
            self._fit_scene()
            event.accept()
            return
        self.scale(step, step)
        event.accept()


class DiagramRenderer(BaseRenderer):
    component_type = "Diagram"

    def _render_quick(
        self,
        props: Dict[str, Any],
        graph: dict[str, Any],
        comp_id: str,
    ):
        if not QT_QUICK_AVAILABLE:
            return None
        qml_path = Path(__file__).with_name("diagram_qtquick.qml")
        if not qml_path.exists():
            return None

        view = QQuickWidget()
        view.setObjectName(f"{comp_id}_quick")
        view.setResizeMode(QQuickWidget.SizeRootObjectToView)
        view.setClearColor(QColor(_D["surface.base"]))
        view.setMinimumHeight(max(220, int(props.get("height", 360))))
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        context = view.rootContext()
        if context is None:
            return None
        context.setContextProperty("diagramModel", _build_quick_model(graph))
        view.setSource(QUrl.fromLocalFile(str(qml_path)))
        if view.status() == QQuickWidget.Error:
            return None
        return view

    def _render_graphics(
        self,
        props: Dict[str, Any],
        graph: dict[str, Any],
        comp_id: str,
    ):
        scene = QGraphicsScene()
        scene.setSceneRect(graph["scene_rect"])
        scene.setBackgroundBrush(QBrush(QColor(_D["surface.base"])))

        if not graph["nodes"]:
            empty = scene.addSimpleText("No diagram data")
            empty.setBrush(QBrush(QColor(_D["text.muted"])))
            empty.setPos(180, 100)
        else:
            node_font = QFont()
            node_font.setPointSize(10)
            node_font.setWeight(QFont.DemiBold)
            label_font = QFont()
            label_font.setPointSize(9)
            lane_font = QFont()
            lane_font.setPointSize(9)
            lane_font.setWeight(QFont.Bold)

            shadow_pen = QPen(QColor(_D["surface.base"]))
            shadow_pen.setWidth(1)
            edge_pen = QPen(QColor(_D["node.stroke"]))
            edge_pen.setWidthF(2.3)
            edge_pen.setCapStyle(Qt.RoundCap)
            edge_pen.setJoinStyle(Qt.RoundJoin)

            for lane_band in graph.get("lane_bands", []):
                band_rect = lane_band["rect"]
                lane_rect = QGraphicsRectItem(band_rect)
                lane_rect.setPen(QPen(QColor(51, 65, 85, 120), 1.0))
                lane_rect.setBrush(QBrush(QColor(15, 23, 42, 70)))
                scene.addItem(lane_rect)

                lane_title = QGraphicsSimpleTextItem(str(lane_band["name"]).upper())
                lane_title.setFont(lane_font)
                lane_title.setBrush(QBrush(QColor(_D["text.muted"])))
                lane_title.setPos(band_rect.x() + 12, band_rect.y() + 8)
                scene.addItem(lane_title)

            for edge in graph["edges"]:
                target_node = next((node for node in graph["nodes"] if node["id"] == edge["target"]), None)
                target_status = str((target_node or {}).get("status") or "").strip().lower()
                edge_color = _status_palette(target_status).get("stroke", _D["node.stroke"])
                path, label_pos = _build_edge_path(
                    graph["positions"][edge["source"]],
                    graph["positions"][edge["target"]],
                    source_width=graph["node_sizes"][edge["source"]][0],
                    source_height=graph["node_sizes"][edge["source"]][1],
                    target_width=graph["node_sizes"][edge["target"]][0],
                    target_height=graph["node_sizes"][edge["target"]][1],
                    direction=graph["direction"],
                )
                edge_item = QGraphicsPathItem(path)
                dynamic_pen = QPen(QColor(edge_color))
                dynamic_pen.setWidthF(edge_pen.widthF())
                dynamic_pen.setCapStyle(edge_pen.capStyle())
                dynamic_pen.setJoinStyle(edge_pen.joinStyle())
                edge_item.setPen(dynamic_pen)
                scene.addItem(edge_item)

                if edge["label"]:
                    label_item = QGraphicsSimpleTextItem(edge["label"])
                    label_item.setFont(label_font)
                    label_item.setBrush(QBrush(QColor(_D["text.muted"])))
                    bounds = label_item.boundingRect()
                    label_item.setPos(label_pos.x() - bounds.width() / 2, label_pos.y())
                    scene.addItem(label_item)

            for node in graph["nodes"]:
                pos = graph["positions"][node["id"]]
                node_w, node_h = graph["node_sizes"][node["id"]]
                palette = _status_palette(node.get("status", ""))
                node_fill = palette.get("fill", node["fill"])
                node_stroke = palette.get("stroke", node["stroke"])
                shadow = QGraphicsRectItem(
                    QRectF(
                        pos.x() + 4,
                        pos.y() + 6,
                        node_w,
                        node_h,
                    )
                )
                shadow.setPen(shadow_pen)
                shadow.setBrush(QBrush(QColor(2, 6, 23, 90)))
                scene.addItem(shadow)

                rect = QGraphicsRectItem(
                    QRectF(
                        pos.x(),
                        pos.y(),
                        node_w,
                        node_h,
                    )
                )
                rect.setPen(QPen(QColor(node_stroke), 2.0))
                rect.setBrush(QBrush(QColor(node_fill)))
                scene.addItem(rect)

                lines = _wrap_label(node["label"])
                line_height = 18
                total_height = len(lines) * line_height
                status = node.get("status", "")
                status_gap = 18 if status else 0
                top = pos.y() + (node_h - total_height - status_gap) / 2
                for index, line in enumerate(lines):
                    text_item = QGraphicsSimpleTextItem(line)
                    text_item.setFont(node_font)
                    text_item.setBrush(QBrush(QColor(node["textColor"])))
                    bounds = text_item.boundingRect()
                    text_item.setPos(
                        pos.x() + (node_w - bounds.width()) / 2,
                        top + index * line_height,
                    )
                    scene.addItem(text_item)

                if status:
                    status_item = QGraphicsSimpleTextItem(status.upper())
                    status_item.setFont(label_font)
                    status_item.setBrush(QBrush(QColor(node_stroke)))
                    status_bounds = status_item.boundingRect()
                    status_item.setPos(
                        pos.x() + (node_w - status_bounds.width()) / 2,
                        pos.y() + node_h - status_bounds.height() - 10,
                    )
                    scene.addItem(status_item)

        view = _DiagramView(scene)
        view.setObjectName(f"{comp_id}_view")
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.setMinimumHeight(max(220, int(props.get("height", 360))))
        return view

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QWidget()
        container.setObjectName(comp_id)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = str(props.get("title") or "").strip()
        if title:
            title_label = QLabel(title)
            title_label.setProperty("ui_role", "diagram_title")
            layout.addWidget(title_label)

        graph = layout_diagram(props)
        view = self._render_quick(props, graph, comp_id) or self._render_graphics(props, graph, comp_id)
        layout.addWidget(view)
        return container
