from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer, emit_action_spec
from ....theme.tokens import theme_token


@dataclass(slots=True)
class _Commit:
    id: str
    label: str
    lane: int
    color: str
    branch: str


def _safe_color(raw: Any, fallback: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return fallback
    color = QColor(text)
    return text if color.isValid() else fallback


def _parse_commits(props: Dict[str, Any]) -> tuple[list[_Commit], dict[int, str]]:
    raw_commits = list(props.get("commits") or [])
    palette = ["#60A5FA", "#22D3EE", "#34D399", "#F59E0B", "#A78BFA", "#FB7185"]
    branch_to_lane: dict[str, int] = {}
    lane_labels: dict[int, str] = {}
    commits: list[_Commit] = []
    for index, raw in enumerate(raw_commits):
        if not isinstance(raw, dict):
            continue
        commit_id = str(raw.get("id") or f"c{index + 1}").strip()
        if not commit_id:
            continue
        label = str(raw.get("label") or raw.get("message") or commit_id).strip() or commit_id
        lane_raw = raw.get("lane")
        branch = str(raw.get("branch") or raw.get("laneName") or "").strip()
        if isinstance(lane_raw, int):
            lane = max(0, lane_raw)
            if branch and lane not in lane_labels:
                lane_labels[lane] = branch
        else:
            branch_key = branch.lower()
            if branch_key:
                if branch_key not in branch_to_lane:
                    branch_to_lane[branch_key] = len(branch_to_lane)
                lane = branch_to_lane[branch_key]
                lane_labels.setdefault(lane, branch)
            else:
                lane = 0
                lane_labels.setdefault(0, "main")
        fallback = palette[lane % len(palette)]
        color = _safe_color(raw.get("color"), fallback)
        commits.append(_Commit(id=commit_id, label=label, lane=lane, color=color, branch=branch))
    for lane in {commit.lane for commit in commits}:
        lane_labels.setdefault(lane, f"lane-{lane}")
    return commits, lane_labels


def _parse_edges(props: Dict[str, Any], commits: list[_Commit]) -> list[tuple[str, str]]:
    commit_ids = {commit.id for commit in commits}
    edges: list[tuple[str, str]] = []
    for raw in list(props.get("edges") or []):
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or raw.get("from") or "").strip()
        target = str(raw.get("target") or raw.get("to") or "").strip()
        if source in commit_ids and target in commit_ids:
            edges.append((source, target))
    return edges


def _label_lines(text: str, width: int = 48) -> list[str]:
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
    return lines[:2]


def _link_path(start: QPointF, end: QPointF) -> QPainterPath:
    path = QPainterPath(start)
    if abs(start.x() - end.x()) < 1:
        path.lineTo(end)
        return path
    mid_y = start.y() + (end.y() - start.y()) * 0.45
    path.cubicTo(start.x(), mid_y, end.x(), mid_y, end.x(), end.y())
    return path


class _GitGraphView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, *, background_color: str, parent=None):
        super().__init__(parent)
        self.setScene(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setBackgroundBrush(QColor(background_color))
        self._zoom = 0

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
        if rect.width() <= 0 or rect.height() <= 0:
            return
        self.fitInView(rect.adjusted(-24, -24, 24, 24), Qt.KeepAspectRatio)

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


class _CommitNodeItem(QGraphicsEllipseItem):
    def __init__(
        self,
        rect: QRectF,
        *,
        on_click,
    ):
        super().__init__(rect)
        self._on_click = on_click
        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.LeftButton and self._on_click:
            self._on_click()
            event.accept()
            return
        super().mousePressEvent(event)


class GitGraphRenderer(BaseRenderer):
    component_type = "GitGraph"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "commits": self.PROPERTY,
            "edges": self.PROPERTY,
            "title": self.PROPERTY,
            "height": self.PROPERTY,
            "laneWidth": self.PROPERTY,
            "lane_width": self.PROPERTY,
            "rowHeight": self.PROPERTY,
            "row_height": self.PROPERTY,
            "showLabels": self.PROPERTY,
            "show_labels": self.PROPERTY,
            "showBranchNames": self.PROPERTY,
            "show_branch_names": self.PROPERTY,
        }

    def _replace_contents(self, widget: QWidget, rebuilt: QWidget) -> None:
        layout = widget.layout()
        if layout is None:
            layout = QVBoxLayout(widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget() if item is not None else None
            if child is not None:
                child.setParent(None)
                child.deleteLater()
        rebuilt_layout = rebuilt.layout()
        if rebuilt_layout is not None:
            while rebuilt_layout.count():
                item = rebuilt_layout.takeAt(0)
                child = item.widget() if item is not None else None
                if child is not None:
                    child.setParent(widget)
                    layout.addWidget(child)
        rebuilt.setParent(None)
        rebuilt.deleteLater()

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        panel_bg = theme_token("data.surface.panel", app_instance=app_instance)
        border_soft = theme_token("data.border.soft", app_instance=app_instance)
        text_muted = theme_token("data.text.muted", app_instance=app_instance)
        text_primary = theme_token("data.text.primary", app_instance=app_instance)
        accent_alt = theme_token("data.accent.alt", app_instance=app_instance)

        container = QWidget()
        container.setObjectName(comp_id)
        container._git_graph_props = dict(props)  # type: ignore[attr-defined]
        container._git_graph_surface_id = surface_id  # type: ignore[attr-defined]
        container._git_graph_app_instance = app_instance  # type: ignore[attr-defined]
        container._git_graph_comp_id = comp_id  # type: ignore[attr-defined]
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = str(props.get("title") or "").strip()
        if title:
            title_label = QLabel(title)
            title_label.setProperty("ui_role", "git_graph_title")
            layout.addWidget(title_label)

        commits, lane_labels = _parse_commits(props)
        if not commits:
            empty = QLabel("No git graph data")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(max(220, int(props.get("height", 360))))
            layout.addWidget(empty)
            return container

        lane_width = max(48, int(props.get("laneWidth", 80)))
        row_height = max(34, int(props.get("rowHeight", 56)))
        show_labels = bool(props.get("showLabels", True))
        show_branch_names = bool(props.get("showBranchNames", True))
        action = props.get("action")
        if isinstance(action, dict):
            action_name = str(action.get("name") or "").strip()
        else:
            action_name = str(action or "").strip()
        base_params = dict(props.get("params") or {})

        max_lane = max((commit.lane for commit in commits), default=0)
        left_pad = 44.0
        right_pad = 38.0
        top_pad = 30.0 if not show_branch_names else 44.0
        bottom_pad = 24.0
        commit_radius = 7.0
        label_x_offset = 18.0

        width = left_pad + (max_lane + 1) * lane_width + (420.0 if show_labels else 80.0) + right_pad
        height = top_pad + max(1, len(commits) - 1) * row_height + bottom_pad + 18.0
        min_height = max(220, int(props.get("height", 360)))
        height = max(height, float(min_height))

        positions: dict[str, QPointF] = {}
        for index, commit in enumerate(commits):
            x = left_pad + commit.lane * lane_width
            y = top_pad + index * row_height
            positions[commit.id] = QPointF(float(x), float(y))

        scene = QGraphicsScene()
        scene.setSceneRect(QRectF(0.0, 0.0, float(width), float(height)))
        scene.setBackgroundBrush(QBrush(QColor(panel_bg)))

        lane_color = QColor(border_soft)
        lane_color.setAlpha(160)
        lane_pen = QPen(lane_color, 1.4)
        lane_pen.setCapStyle(Qt.RoundCap)
        lane_top = top_pad - 14
        lane_bottom = top_pad + max(1, len(commits) - 1) * row_height + 14
        for lane in range(max_lane + 1):
            lane_x = left_pad + lane * lane_width
            lane_path = QPainterPath(QPointF(lane_x, lane_top))
            lane_path.lineTo(lane_x, lane_bottom)
            lane_item = QGraphicsPathItem(lane_path)
            lane_item.setPen(lane_pen)
            scene.addItem(lane_item)
            if show_branch_names:
                lane_name = str(lane_labels.get(lane) or f"lane-{lane}")
                lane_label = QGraphicsSimpleTextItem(lane_name)
                lane_font = QFont()
                lane_font.setPointSize(8)
                lane_font.setWeight(QFont.DemiBold)
                lane_label.setFont(lane_font)
                lane_label.setBrush(QBrush(QColor(text_muted)))
                lane_label.setPos(lane_x - 16, 8)
                scene.addItem(lane_label)

        commit_index = {commit.id: idx for idx, commit in enumerate(commits)}
        edges = _parse_edges(props, commits)
        if not edges:
            for i in range(len(commits) - 1):
                edges.append((commits[i].id, commits[i + 1].id))

        for source_id, target_id in edges:
            source_idx = commit_index.get(source_id, -1)
            target_idx = commit_index.get(target_id, -1)
            if source_idx < 0 or target_idx < 0 or source_id == target_id:
                continue
            start_id = source_id
            end_id = target_id
            if source_idx > target_idx:
                start_id, end_id = target_id, source_id
            start = positions[start_id]
            end = positions[end_id]
            path = _link_path(start, end)

            end_commit = next((commit for commit in commits if commit.id == end_id), None)
            edge_color = QColor(end_commit.color if end_commit else accent_alt)
            edge_pen = QPen(edge_color, 2.2)
            edge_pen.setCapStyle(Qt.RoundCap)
            edge_pen.setJoinStyle(Qt.RoundJoin)
            edge_item = QGraphicsPathItem(path)
            edge_item.setPen(edge_pen)
            scene.addItem(edge_item)

        label_font = QFont()
        label_font.setPointSize(9)
        label_font.setWeight(QFont.DemiBold)

        for commit in commits:
            pos = positions[commit.id]
            commit_dot = _CommitNodeItem(
                QRectF(
                    pos.x() - commit_radius,
                    pos.y() - commit_radius,
                    commit_radius * 2,
                    commit_radius * 2,
                ),
                on_click=lambda c=commit: emit_action_spec(
                    app_instance,
                    action,
                    {
                        **base_params,
                        "source": "git_graph",
                        "componentId": comp_id,
                        "commitId": c.id,
                        "label": c.label,
                        "branch": c.branch,
                        "lane": c.lane,
                    },
                    surface_id,
                    comp_id,
                )
                if action_name
                else None,
            )
            commit_dot.setPen(QPen(QColor(panel_bg), 1.4))
            commit_dot.setBrush(QBrush(QColor(commit.color)))
            scene.addItem(commit_dot)

            if show_labels:
                lines = _label_lines(commit.label)
                for line_index, line in enumerate(lines):
                    label_item = QGraphicsSimpleTextItem(line)
                    label_item.setFont(label_font)
                    label_item.setBrush(QBrush(QColor(text_primary)))
                    label_item.setPos(
                        pos.x() + label_x_offset,
                        pos.y() - 14 + line_index * 15,
                    )
                    scene.addItem(label_item)

        view = _GitGraphView(scene, background_color=panel_bg)
        view.setObjectName(f"{comp_id}_view")
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.setMinimumHeight(min_height)
        layout.addWidget(view)
        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        props = dict(getattr(widget, "_git_graph_props", {}) or {})
        props[prop] = value
        widget._git_graph_props = props  # type: ignore[attr-defined]
        rebuilt = self.render(
            props,
            str(getattr(widget, "_git_graph_surface_id", "main") or "main"),
            getattr(widget, "_git_graph_app_instance", None),
            str(getattr(widget, "_git_graph_comp_id", widget.objectName()) or widget.objectName()),
        )
        self._replace_contents(widget, rebuilt)
