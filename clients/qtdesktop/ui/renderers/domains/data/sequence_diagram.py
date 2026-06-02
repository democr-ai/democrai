from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer


@dataclass(slots=True)
class _Participant:
    id: str
    label: str


@dataclass(slots=True)
class _Message:
    source: str
    target: str
    text: str
    msg_type: str


_PARTICIPANT_RE = re.compile(
    r"^(?:participant|actor)\s+(?P<id>[A-Za-z0-9_.-]+)(?:\s+as\s+(?P<label>.+))?$",
    re.IGNORECASE,
)
_MESSAGE_RE = re.compile(
    r"^(?P<src>[A-Za-z0-9_.-]+?)\s*(?P<arrow>-->>|->>|-->|->|--x|-x|==>>|=>>|==>|=>)\s*(?P<dst>[A-Za-z0-9_.-]+)\s*:\s*(?P<text>.+)$"
)


def _parse_mermaid_sequence(mermaid: str) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    text = str(mermaid or "").strip()
    if not text:
        return [], []
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("%%")]
    if not lines or lines[0].lower() != "sequencediagram":
        return [], []

    participants: list[dict[str, str]] = []
    participant_ids: set[str] = set()
    messages: list[dict[str, str]] = []

    for line in lines[1:]:
        if line.lower().startswith(("autonumber", "note ", "activate ", "deactivate ", "loop ", "alt ", "opt ", "par ", "and ", "else", "end")):
            continue
        participant_match = _PARTICIPANT_RE.match(line)
        if participant_match:
            pid = participant_match.group("id").strip()
            label = str(participant_match.group("label") or pid).strip()
            if pid and pid not in participant_ids:
                participants.append({"id": pid, "label": label})
                participant_ids.add(pid)
            continue
        message_match = _MESSAGE_RE.match(line)
        if not message_match:
            continue
        source = message_match.group("src").strip()
        target = message_match.group("dst").strip()
        arrow = message_match.group("arrow")
        text_value = message_match.group("text").strip()
        msg_type = "reply" if arrow.startswith("--") or arrow.startswith("==") else "sync"
        messages.append({"from": source, "to": target, "text": text_value, "type": msg_type})
        for pid in (source, target):
            if pid not in participant_ids:
                participants.append({"id": pid, "label": pid})
                participant_ids.add(pid)

    return participants, messages


def _normalize_participants_and_messages(props: Dict[str, Any]) -> tuple[list[_Participant], list[_Message]]:
    raw_participants = list(props.get("participants") or [])
    raw_messages = list(props.get("messages") or [])
    if not raw_participants and not raw_messages and str(props.get("mermaid") or "").strip():
        raw_participants, raw_messages = _parse_mermaid_sequence(str(props.get("mermaid") or ""))

    participants: list[_Participant] = []
    by_id: dict[str, _Participant] = {}

    for index, raw in enumerate(raw_participants):
        if isinstance(raw, str):
            pid = raw.strip()
            label = pid
        elif isinstance(raw, dict):
            pid = str(raw.get("id") or raw.get("name") or f"p{index + 1}").strip()
            label = str(raw.get("label") or raw.get("name") or pid).strip()
        else:
            continue
        if not pid:
            continue
        participant = _Participant(id=pid, label=label or pid)
        by_id[pid] = participant
        participants.append(participant)

    messages: list[_Message] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        source = str(raw.get("source") or raw.get("from") or "").strip()
        target = str(raw.get("target") or raw.get("to") or "").strip()
        if not source or not target:
            continue
        text = str(raw.get("text") or raw.get("label") or "").strip()
        msg_type = str(raw.get("type") or "sync").strip().lower()
        messages.append(_Message(source=source, target=target, text=text, msg_type=msg_type))
        if source not in by_id:
            by_id[source] = _Participant(source, source)
            participants.append(by_id[source])
        if target not in by_id:
            by_id[target] = _Participant(target, target)
            participants.append(by_id[target])

    return participants, messages


def _arrow_path(start: QPointF, end: QPointF) -> QPainterPath:
    path = QPainterPath(start)
    path.lineTo(end)
    return path


def _arrow_head(path_end: QPointF, forward: bool) -> QPainterPath:
    size = 7.0
    direction = 1.0 if forward else -1.0
    p1 = QPointF(path_end.x() - size * direction, path_end.y() - size / 2)
    p2 = QPointF(path_end.x() - size * direction, path_end.y() + size / 2)
    head = QPainterPath(path_end)
    head.lineTo(p1)
    head.lineTo(p2)
    head.closeSubpath()
    return head


class _SequenceView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent=None):
        super().__init__(parent)
        self.setScene(scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setFrameShape(QFrame.NoFrame)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#FFFFFF"))


class SequenceDiagramRenderer(BaseRenderer):
    component_type = "SequenceDiagram"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "participants": self.PROPERTY,
            "messages": self.PROPERTY,
            "mermaid": self.PROPERTY,
            "title": self.PROPERTY,
            "height": self.PROPERTY,
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
        container = QWidget()
        container.setObjectName(comp_id)
        container._sequence_diagram_props = dict(props)  # type: ignore[attr-defined]
        container._sequence_diagram_surface_id = surface_id  # type: ignore[attr-defined]
        container._sequence_diagram_app_instance = app_instance  # type: ignore[attr-defined]
        container._sequence_diagram_comp_id = comp_id  # type: ignore[attr-defined]
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        title = str(props.get("title") or "").strip()
        if title:
            title_label = QLabel(title)
            title_label.setProperty("ui_role", "sequence_diagram_title")
            layout.addWidget(title_label)

        participants, messages = _normalize_participants_and_messages(props)
        if not participants:
            empty = QLabel("No sequence diagram data")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(max(220, int(props.get("height", 360))))
            layout.addWidget(empty)
            return container

        left_pad = 60.0
        top_pad = 24.0
        header_w = 150.0
        header_h = 38.0
        col_gap = 190.0
        line_top = top_pad + header_h + 12.0
        msg_start_y = line_top + 26.0
        msg_step = 46.0

        participant_x: dict[str, float] = {}
        for index, participant in enumerate(participants):
            participant_x[participant.id] = left_pad + index * col_gap

        width = int(left_pad * 2 + max(1, len(participants) - 1) * col_gap + header_w)
        height = int(max(280.0, msg_start_y + max(1, len(messages)) * msg_step + 48.0))
        min_height = max(220, int(props.get("height", 360)))

        scene = QGraphicsScene()
        scene.setSceneRect(QRectF(0.0, 0.0, float(width), float(height)))
        scene.setBackgroundBrush(QBrush(QColor("#FFFFFF")))

        lane_pen = QPen(QColor("#9CA3AF"), 1.0, Qt.DashLine)
        node_pen = QPen(QColor("#111827"), 1.2)
        node_fill = QBrush(QColor("#FFFFFF"))
        text_brush = QBrush(QColor("#111827"))
        msg_pen = QPen(QColor("#111827"), 1.6)
        msg_pen_dash = QPen(QColor("#111827"), 1.3, Qt.DashLine)

        header_font = QFont()
        header_font.setPointSize(10)
        header_font.setWeight(QFont.DemiBold)
        text_font = QFont()
        text_font.setPointSize(9)

        for participant in participants:
            x = participant_x[participant.id]
            header_rect = QRectF(x, top_pad, header_w, header_h)
            header_item = QGraphicsRectItem(header_rect)
            header_item.setPen(node_pen)
            header_item.setBrush(node_fill)
            scene.addItem(header_item)

            label_item = QGraphicsSimpleTextItem(participant.label)
            label_item.setFont(header_font)
            label_item.setBrush(text_brush)
            bounds = label_item.boundingRect()
            label_item.setPos(x + (header_w - bounds.width()) / 2, top_pad + (header_h - bounds.height()) / 2)
            scene.addItem(label_item)

            line_item = scene.addLine(
                x + header_w / 2,
                line_top,
                x + header_w / 2,
                height - 24.0,
                lane_pen,
            )
            line_item.setZValue(-1)

        for index, message in enumerate(messages):
            if message.source not in participant_x or message.target not in participant_x:
                continue
            y = msg_start_y + index * msg_step
            sx = participant_x[message.source] + header_w / 2
            tx = participant_x[message.target] + header_w / 2
            forward = tx >= sx
            if message.source == message.target:
                loop = QPainterPath(QPointF(sx, y))
                loop.lineTo(sx + 40, y)
                loop.lineTo(sx + 40, y + 24)
                loop.lineTo(sx, y + 24)
                loop_item = QGraphicsPathItem(loop)
                loop_item.setPen(msg_pen)
                scene.addItem(loop_item)
                head = QGraphicsPathItem(_arrow_head(QPointF(sx, y + 24), False))
                head.setPen(msg_pen)
                head.setBrush(QBrush(QColor("#111827")))
                scene.addItem(head)
                text_x = sx + 44
                text_y = y - 2
            else:
                path = _arrow_path(QPointF(sx, y), QPointF(tx, y))
                line_item = QGraphicsPathItem(path)
                line_item.setPen(msg_pen_dash if message.msg_type in {"reply", "dashed"} else msg_pen)
                scene.addItem(line_item)

                head = QGraphicsPathItem(_arrow_head(QPointF(tx, y), forward))
                head.setPen(msg_pen)
                head.setBrush(QBrush(QColor("#111827")))
                scene.addItem(head)
                text_x = min(sx, tx) + abs(tx - sx) / 2
                text_y = y - 16

            if message.text:
                msg_label = QGraphicsSimpleTextItem(message.text)
                msg_label.setFont(text_font)
                msg_label.setBrush(text_brush)
                bounds = msg_label.boundingRect()
                msg_label.setPos(text_x - bounds.width() / 2, text_y)
                scene.addItem(msg_label)

        view = _SequenceView(scene)
        view.setObjectName(f"{comp_id}_view")
        view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        view.setMinimumHeight(min_height)

        scroll = QScrollArea()
        scroll.setObjectName(f"{comp_id}_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(view)
        scroll.setMinimumHeight(min_height)
        layout.addWidget(scroll)
        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        props = dict(getattr(widget, "_sequence_diagram_props", {}) or {})
        props[prop] = value
        widget._sequence_diagram_props = props  # type: ignore[attr-defined]
        rebuilt = self.render(
            props,
            str(getattr(widget, "_sequence_diagram_surface_id", "main") or "main"),
            getattr(widget, "_sequence_diagram_app_instance", None),
            str(getattr(widget, "_sequence_diagram_comp_id", widget.objectName()) or widget.objectName()),
        )
        self._replace_contents(widget, rebuilt)
