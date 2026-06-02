from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import re
from typing import Any, Dict

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ...base import BaseRenderer
from ....theme.tokens import theme_token, themed_status_color


_G = {
    "surface.base": theme_token("data.surface.base"),
    "surface.panel": theme_token("data.surface.panel"),
    "surface.panel_alt": theme_token("data.surface.panel_alt"),
    "surface.row.even": theme_token("data.surface.row.even"),
    "surface.row.odd": theme_token("data.surface.row.odd"),
    "border.grid": theme_token("data.border.grid"),
    "border.soft": theme_token("data.border.soft"),
    "text.primary": theme_token("data.text.primary"),
    "text.muted": theme_token("data.text.muted"),
    "text.subtle": theme_token("data.text.subtle"),
    "accent": theme_token("data.accent"),
    "accent.alt": theme_token("data.accent.alt"),
}

_DAY_SECONDS = 24 * 60 * 60


@dataclass(frozen=True, slots=True)
class ScaleSpec:
    raw: str
    unit_seconds: float
    unit_width: int
    is_day: bool


def _parse_scale(raw: Any) -> ScaleSpec:
    value = str(raw or "1d").strip().lower()
    aliases = {
        "day": "1d",
        "daily": "1d",
        "hour": "1h",
        "hourly": "1h",
        "minute": "1m",
        "minutely": "1m",
        "second": "1s",
        "secondly": "1s",
        "millisecond": "1ms",
    }
    token = aliases.get(value, value or "1d")
    match = re.match(r"^(?P<amount>\d+)\s*(?P<unit>ms|s|m|h|d)$", token)
    if not match:
        return ScaleSpec("1d", float(_DAY_SECONDS), 34, True)
    amount = max(1, int(match.group("amount")))
    unit = match.group("unit")
    multiplier = {"ms": 0.001, "s": 1.0, "m": 60.0, "h": 3600.0, "d": float(_DAY_SECONDS)}[unit]
    width = {"ms": 36, "s": 40, "m": 48, "h": 56, "d": 34}[unit]
    return ScaleSpec(f"{amount}{unit}", amount * multiplier, width, unit == "d")


def _safe_date(raw: Any) -> date | None:
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _safe_datetime(raw: Any, scale: ScaleSpec) -> datetime | None:
    if isinstance(raw, datetime):
        value = raw
    elif isinstance(raw, date):
        value = datetime.combine(raw, datetime.min.time())
    else:
        text = str(raw or "").strip()
        if not text:
            return None
        parsed = None
        for candidate in (text, text.replace("Z", "+00:00")):
            try:
                parsed = datetime.fromisoformat(candidate)
                break
            except ValueError:
                continue
        if parsed is None:
            try:
                parsed = datetime.strptime(text, "%Y-%m-%d")
            except ValueError:
                return None
        value = parsed
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    if scale.is_day:
        value = value.replace(hour=0, minute=0, second=0, microsecond=0)
    return value


def _unit_offset(start: datetime, value: datetime, scale: ScaleSpec) -> int:
    seconds = (value - start).total_seconds()
    return max(0, int(seconds // scale.unit_seconds))


def _format_instant(value: datetime, scale: ScaleSpec) -> str:
    if scale.is_day:
        return value.date().isoformat()
    if scale.unit_seconds < 1:
        return value.strftime("%H:%M:%S.%f")[:-3]
    if scale.unit_seconds < 60:
        return value.strftime("%H:%M:%S")
    if scale.unit_seconds < _DAY_SECONDS:
        return value.strftime("%Y-%m-%d %H:%M")
    return value.date().isoformat()


def _format_tick(value: datetime, scale: ScaleSpec) -> str:
    if scale.is_day:
        return value.strftime("%d")
    if scale.unit_seconds < 1:
        return value.strftime("%S.%f")[:6]
    if scale.unit_seconds < 60:
        return value.strftime("%M:%S")
    if scale.unit_seconds < _DAY_SECONDS:
        return value.strftime("%H:%M")
    return value.strftime("%d %b")


def _status_color(status: str, fallback: str) -> str:
    if fallback:
        return fallback
    return themed_status_color(status, fallback=fallback or _G["accent"])


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_") or "task"


def _parse_mermaid_duration(token: str) -> timedelta | None:
    match = re.match(r"^(?P<value>\d+)\s*(?P<unit>[dw])$", token.strip().lower())
    if not match:
        return None
    value = int(match.group("value"))
    unit = match.group("unit")
    return timedelta(days=value * (7 if unit == "w" else 1))


def _parse_mermaid_gantt(mermaid: str) -> dict[str, Any]:
    text = str(mermaid or "").strip()
    if not text:
        return {"items": [], "title": ""}
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("%%")]
    if not lines or lines[0].lower() != "gantt":
        return {"items": [], "title": ""}

    section = ""
    title = ""
    items: list[dict[str, Any]] = []
    by_id: dict[str, tuple[date, date]] = {}
    task_index = 0

    for line in lines[1:]:
        low = line.lower()
        if low.startswith("title "):
            title = line[6:].strip()
            continue
        if low.startswith(("dateformat ", "axisformat ", "tickinterval ", "excludes ")):
            continue
        if low.startswith("section "):
            section = line[8:].strip()
            continue
        if ":" not in line:
            continue

        label_raw, tail = line.split(":", 1)
        label = label_raw.strip()
        tokens = [token.strip() for token in tail.split(",") if token.strip()]
        if not label or not tokens:
            continue

        status = "planned"
        task_id = ""
        start_date: date | None = None
        end_date: date | None = None
        duration_days: timedelta | None = None
        after_ref = ""

        for token in tokens:
            low_token = token.lower()
            parsed_date = _safe_date(token)
            parsed_duration = _parse_mermaid_duration(token)
            if low_token in {"done", "active", "crit", "milestone"}:
                if low_token == "done":
                    status = "done"
                elif low_token == "active":
                    status = "active"
                elif low_token == "crit":
                    status = "risk"
                continue
            if parsed_date is not None:
                if start_date is None:
                    start_date = parsed_date
                else:
                    end_date = parsed_date
                continue
            if parsed_duration is not None:
                duration_days = parsed_duration
                continue
            if low_token.startswith("after "):
                after_ref = token.split(" ", 1)[1].strip()
                continue
            if not task_id and re.match(r"^[A-Za-z0-9_.-]+$", token):
                task_id = token

        if task_id == "":
            task_id = f"{_slug(label)}_{task_index}"
        if start_date is None and after_ref and after_ref in by_id:
            start_date = by_id[after_ref][1] + timedelta(days=1)
        if start_date is None:
            continue
        if end_date is None and duration_days is not None:
            end_date = start_date + duration_days - timedelta(days=1)
        if end_date is None:
            end_date = start_date
        if end_date < start_date:
            end_date = start_date

        items.append(
            {
                "id": task_id,
                "label": label,
                "group": section,
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "status": status,
                "progress": 100 if status == "done" else (55 if status == "active" else 0),
            }
        )
        by_id[task_id] = (start_date, end_date)
        task_index += 1

    return {"items": items, "title": title}


@dataclass(slots=True)
class GanttRow:
    id: str
    label: str
    start: datetime
    end: datetime
    group: str
    status: str
    status_label: str
    progress: int
    color: str
    depth: int = 0
    parent_id: str = ""
    has_children: bool = False
    expanded: bool = False


def _parse_rows(
    raw_items: list[dict[str, Any]],
    scale: ScaleSpec,
    *,
    parent_id: str = "",
    depth: int = 0,
    prefix: str = "",
) -> list[GanttRow]:
    rows: list[GanttRow] = []
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue
        row_id = str(raw.get("id") or f"{prefix}task_{index}").strip() or f"{prefix}task_{index}"
        subtasks = [item for item in list(raw.get("subtasks") or raw.get("children") or []) if isinstance(item, dict)]
        child_rows = _parse_rows(
            subtasks,
            scale,
            parent_id=row_id,
            depth=depth + 1,
            prefix=f"{row_id}_",
        )

        start = _safe_datetime(raw.get("start"), scale)
        end = _safe_datetime(raw.get("end"), scale)
        if start is None and child_rows:
            start = min(child.start for child in child_rows)
        if end is None and child_rows:
            end = max(child.end for child in child_rows)
        if start is None:
            continue
        if end is None or end < start:
            end = start

        rows.append(
            GanttRow(
                id=row_id,
                label=str(raw.get("label") or raw.get("name") or f"Task {index + 1}"),
                start=start,
                end=end,
                group=str(raw.get("group") or "").strip(),
                status=str(raw.get("status") or "").strip().lower(),
                status_label=str(raw.get("status_label") or raw.get("statusLabel") or "").strip(),
                progress=max(0, min(100, int(raw.get("progress", 0) or 0))),
                color=_status_color(str(raw.get("status") or ""), str(raw.get("color") or "")),
                depth=depth,
                parent_id=parent_id,
                has_children=bool(child_rows),
                expanded=bool(raw.get("expanded", False)),
            )
        )
        rows.extend(child_rows)
    return rows


def _visible_rows(rows: list[GanttRow]) -> list[GanttRow]:
    row_index = {row.id: row for row in rows}
    visible: list[GanttRow] = []
    for row in rows:
        parent_id = row.parent_id
        shown = True
        while parent_id:
            parent = row_index.get(parent_id)
            if parent is None or not parent.expanded:
                shown = False
                break
            parent_id = parent.parent_id
        if shown:
            visible.append(row)
    return visible


def build_gantt_model(props: Dict[str, Any]) -> dict[str, Any]:
    scale = _parse_scale(props.get("scale"))
    raw_items = list(props.get("items") or [])
    mermaid = str(props.get("mermaid") or "")
    parsed_mermaid = {"items": [], "title": ""}
    if not raw_items and mermaid:
        parsed_mermaid = _parse_mermaid_gantt(mermaid)
        raw_items = list(parsed_mermaid.get("items") or [])
    rows = _parse_rows(raw_items, scale)

    explicit_start = _safe_datetime(props.get("start"), scale)
    explicit_end = _safe_datetime(props.get("end"), scale)
    default_start = datetime.combine(date.today(), datetime.min.time())
    min_date = explicit_start or min((row.start for row in rows), default=default_start)
    max_date = explicit_end or max((row.end for row in rows), default=min_date + timedelta(days=14))
    if max_date < min_date:
        max_date = min_date

    ticks = []
    cursor = min_date
    while cursor <= max_date:
        ticks.append(cursor)
        cursor += timedelta(seconds=scale.unit_seconds)

    return {
        "rows": rows,
        "visible_rows": _visible_rows(rows),
        "start": min_date,
        "end": max_date,
        "ticks": ticks,
        "scale": scale,
        "title": str(props.get("title") or parsed_mermaid.get("title") or ""),
    }


class _GanttCanvas(QWidget):
    def __init__(self, model: dict[str, Any], parent=None):
        super().__init__(parent)
        self._model = model
        self._left_column = 360
        self._row_height = 54
        self._header_height = 58
        self._padding = 18
        self._toggle_rects: dict[str, QRect] = {}
        self._refresh_geometry()
        self.setSizePolicy(QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.MinimumExpanding)

    def _refresh_geometry(self):
        visible_rows = _visible_rows(self._model["rows"])
        self._model["visible_rows"] = visible_rows
        scale: ScaleSpec = self._model["scale"]
        total_width = self._left_column + max(14, len(self._model["ticks"])) * scale.unit_width + self._padding * 2
        total_height = self._header_height + max(1, len(visible_rows)) * self._row_height + self._padding * 2
        self.setMinimumSize(total_width, total_height)
        self.resize(total_width, total_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(_G["surface.base"]))
        self._toggle_rects = {}

        header_font = QFont()
        header_font.setPointSize(9)
        header_font.setWeight(QFont.DemiBold)
        label_font = QFont()
        label_font.setPointSize(10)
        label_font.setWeight(QFont.DemiBold)
        meta_font = QFont()
        meta_font.setPointSize(8)

        x0 = self._padding
        y0 = self._padding
        timeline_x = x0 + self._left_column
        body_y = y0 + self._header_height

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(_G["surface.panel"]))
        painter.drawRoundedRect(QRectF(x0, y0, self.width() - self._padding * 2, self.height() - self._padding * 2), 18, 18)

        painter.setBrush(QColor(_G["surface.panel_alt"]))
        painter.drawRoundedRect(QRectF(x0, y0, self._left_column, self.height() - self._padding * 2), 18, 18)

        painter.setBrush(QColor(_G["surface.panel_alt"]))
        painter.drawRect(QRectF(timeline_x, y0, self.width() - timeline_x - self._padding, self.height() - self._padding * 2))

        ticks = self._model["ticks"]
        scale: ScaleSpec = self._model["scale"]
        label_every = max(1, (96 + scale.unit_width - 1) // scale.unit_width, len(ticks) // 16)
        for index, tick in enumerate(ticks):
            column_x = timeline_x + index * scale.unit_width
            is_weekend = scale.is_day and tick.weekday() >= 5
            painter.fillRect(
                QRectF(column_x, y0, scale.unit_width, self.height() - self._padding * 2),
                QColor(_G["surface.panel"] if is_weekend else _G["surface.panel_alt"]),
            )
            painter.setPen(QPen(QColor(_G["border.grid"]), 1))
            painter.drawLine(int(column_x), int(y0), int(column_x), int(self.height() - self._padding))
            painter.setPen(QColor(_G["text.subtle"]))
            painter.setFont(header_font)
            if index % label_every == 0:
                top_label = _format_tick(tick, scale)
                bottom_label = tick.strftime("%a")[0] if scale.is_day else scale.raw
                painter.drawText(
                    QRectF(column_x, y0 + 8, scale.unit_width, 18),
                    Qt.AlignCenter,
                    top_label,
                )
                painter.setPen(QColor(_G["text.muted"]))
                painter.drawText(
                    QRectF(column_x, y0 + 27, scale.unit_width, 16),
                    Qt.AlignCenter,
                    bottom_label,
                )

        painter.setPen(QPen(QColor(_G["border.soft"]), 1))
        painter.drawLine(int(timeline_x), int(y0), int(timeline_x), int(self.height() - self._padding))
        painter.drawLine(int(x0), int(body_y), int(self.width() - self._padding), int(body_y))

        for row_index, row in enumerate(self._model["visible_rows"]):
            row_y = body_y + row_index * self._row_height
            depth_tint = min(row.depth * 6, 20)
            row_bg = QColor(_G["surface.row.even"] if row_index % 2 == 0 else _G["surface.row.odd"])
            row_bg = row_bg.lighter(100 + depth_tint)
            painter.fillRect(QRectF(x0, row_y, self.width() - self._padding * 2, self._row_height), row_bg)
            painter.setPen(QPen(QColor(_G["border.grid"]), 1))
            painter.drawLine(int(x0), int(row_y + self._row_height), int(self.width() - self._padding), int(row_y + self._row_height))

            indent = row.depth * 18
            text_x = x0 + 16 + indent
            if row.has_children:
                toggle_rect = QRect(int(text_x), int(row_y + 16), 16, 16)
                self._toggle_rects[row.id] = toggle_rect
                painter.setPen(QPen(QColor(_G["border.soft"]), 1))
                painter.setBrush(QColor(_G["surface.panel"]))
                painter.drawRoundedRect(QRectF(toggle_rect), 4, 4)
                painter.setPen(QColor(_G["text.primary"]))
                painter.drawLine(toggle_rect.left() + 4, toggle_rect.center().y(), toggle_rect.right() - 4, toggle_rect.center().y())
                if not row.expanded:
                    painter.drawLine(toggle_rect.center().x(), toggle_rect.top() + 4, toggle_rect.center().x(), toggle_rect.bottom() - 4)
                text_x += 24

            painter.setPen(QColor(_G["text.primary"]))
            painter.setFont(label_font)
            label_rect = QRectF(text_x, row_y + 10, self._left_column - 32 - indent, 18)
            label_text = QFontMetrics(label_font).elidedText(row.label, Qt.ElideRight, max(1, int(label_rect.width())))
            painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, label_text)

            painter.setFont(meta_font)
            painter.setPen(QColor(_G["text.subtle"]))
            meta_parts = []
            if row.group:
                meta_parts.append(row.group.upper())
            if row.has_children:
                meta_parts.append(f"{len([candidate for candidate in self._model['rows'] if candidate.parent_id == row.id])} SUBTASKS")
            meta_parts.append(f"{_format_instant(row.start, scale)} -> {_format_instant(row.end, scale)}")
            meta_rect = QRectF(text_x, row_y + 29, self._left_column - 32 - indent, 14)
            meta_text = QFontMetrics(meta_font).elidedText("  |  ".join(meta_parts), Qt.ElideRight, max(1, int(meta_rect.width())))
            painter.drawText(
                meta_rect,
                Qt.AlignLeft | Qt.AlignVCenter,
                meta_text,
            )

            start_offset = _unit_offset(self._model["start"], row.start, scale)
            end_offset = max(start_offset, _unit_offset(self._model["start"], row.end, scale))
            bar_x = timeline_x + start_offset * scale.unit_width + 3
            timeline_w = len(ticks) * scale.unit_width
            max_bar_w = max(24, timeline_x + timeline_w - bar_x - 3)
            bar_w = min(max_bar_w, max(24, (end_offset - start_offset + 1) * scale.unit_width - 6))
            bar_rect = QRectF(bar_x, row_y + 11, bar_w, self._row_height - 22)

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(row.color))
            painter.drawRoundedRect(bar_rect, 10, 10)

            progress_width = max(10, bar_rect.width() * (row.progress / 100.0)) if row.progress else 0
            if progress_width:
                painter.setBrush(QColor(255, 255, 255, 34))
                painter.drawRoundedRect(QRectF(bar_rect.x(), bar_rect.y(), progress_width, bar_rect.height()), 10, 10)

            if bar_rect.width() >= 64:
                painter.setPen(QColor(_G["text.primary"]))
                painter.setFont(meta_font)
                painter.drawText(bar_rect.adjusted(10, 0, -10, 0), Qt.AlignVCenter | Qt.AlignLeft, row.status_label or (row.status.upper() if row.status else row.label))

    def mousePressEvent(self, event):
        for row_id, rect in self._toggle_rects.items():
            if rect.contains(event.position().toPoint()):
                for row in self._model["rows"]:
                    if row.id == row_id:
                        row.expanded = not row.expanded
                        self._refresh_geometry()
                        self.update()
                        event.accept()
                        return
        super().mousePressEvent(event)


class GanttRenderer(BaseRenderer):
    component_type = "Gantt"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "items": self.PROPERTY,
            "mermaid": self.PROPERTY,
            "title": self.PROPERTY,
            "height": self.PROPERTY,
            "start": self.PROPERTY,
            "end": self.PROPERTY,
            "scale": self.PROPERTY,
        }

    def _populate(
        self,
        container: QWidget,
        props: Dict[str, Any],
        app_instance: Any,
        comp_id: str,
    ) -> None:
        layout = container.layout()
        if layout is None:
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(10)
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget() if item is not None else None
            if child is not None:
                child.setParent(None)
                child.deleteLater()

        model = build_gantt_model(props)
        title = str(props.get("title") or model.get("title") or "").strip()
        if title:
            title_label = QLabel(title)
            title_label.setProperty("ui_role", "gantt_title")
            layout.addWidget(title_label)
        if not model["rows"]:
            empty = QLabel("No Gantt items")
            empty.setAlignment(Qt.AlignCenter)
            empty.setMinimumHeight(max(220, int(props.get("height", 360))))
            empty.setProperty("ui_role", "gantt_empty")
            layout.addWidget(empty)
            return

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumHeight(max(220, int(props.get("height", 360))))
        scroll.setProperty("ui_role", "gantt_scroll")

        canvas = _GanttCanvas(model)
        canvas.setObjectName(f"{comp_id}_canvas")
        scroll.setWidget(canvas)
        layout.addWidget(scroll)

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        global _G
        _G = {
            "surface.base": theme_token("data.surface.base", app_instance=app_instance),
            "surface.panel": theme_token("data.surface.panel", app_instance=app_instance),
            "surface.panel_alt": theme_token("data.surface.panel_alt", app_instance=app_instance),
            "surface.row.even": theme_token("data.surface.row.even", app_instance=app_instance),
            "surface.row.odd": theme_token("data.surface.row.odd", app_instance=app_instance),
            "border.grid": theme_token("data.border.grid", app_instance=app_instance),
            "border.soft": theme_token("data.border.soft", app_instance=app_instance),
            "text.primary": theme_token("data.text.primary", app_instance=app_instance),
            "text.muted": theme_token("data.text.muted", app_instance=app_instance),
            "text.subtle": theme_token("data.text.subtle", app_instance=app_instance),
            "accent": theme_token("data.accent", app_instance=app_instance),
            "accent.alt": theme_token("data.accent.alt", app_instance=app_instance),
        }

        container = QWidget()
        container.setObjectName(comp_id)
        container._gantt_props = dict(props)  # type: ignore[attr-defined]
        container._gantt_app_instance = app_instance  # type: ignore[attr-defined]
        container._gantt_comp_id = comp_id  # type: ignore[attr-defined]
        self._populate(container, container._gantt_props, app_instance, comp_id)  # type: ignore[attr-defined]
        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        props = dict(getattr(widget, "_gantt_props", {}) or {})
        props[prop] = value
        widget._gantt_props = props  # type: ignore[attr-defined]
        self._populate(
            widget,
            props,
            getattr(widget, "_gantt_app_instance", None),
            str(getattr(widget, "_gantt_comp_id", widget.objectName()) or widget.objectName()),
        )
