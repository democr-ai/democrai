from __future__ import annotations

from collections import defaultdict
from typing import Any

from PySide6.QtCore import QTimer, QSize, Qt
from PySide6.QtGui import QIcon, QTransform
from PySide6.QtWidgets import QPushButton, QToolButton, QWidget
from ..renderers.icon import get_icon


class ActionLockController:
    """Track client-side pending actions and disable matching action widgets."""

    def __init__(self, window: Any) -> None:
        self.window = window
        self._counts: dict[str, int] = defaultdict(int)
        self._requests: dict[str, str] = {}

    def acquire(self, *, request_id: str, action_name: str) -> bool:
        if not request_id or not action_name:
            return True
        if self.is_pending(action_name):
            return False
        self._requests[request_id] = action_name
        self._counts[action_name] = self._counts.get(action_name, 0) + 1
        self._sync_widgets(action_name)
        return True

    def release(self, request_id: str | None) -> None:
        rid = str(request_id or "").strip()
        if not rid:
            return
        action_name = self._requests.pop(rid, "")
        if not action_name:
            return
        next_count = max(0, self._counts.get(action_name, 0) - 1)
        if next_count <= 0:
            self._counts.pop(action_name, None)
        else:
            self._counts[action_name] = next_count
        self._sync_widgets(action_name)

    def clear(self) -> None:
        action_names = list(self._counts.keys())
        self._counts.clear()
        self._requests.clear()
        for action_name in action_names:
            self._sync_widgets(action_name)

    def is_pending(self, action_name: str) -> bool:
        return self._counts.get(str(action_name or "").strip(), 0) > 0

    def sync_all(self) -> None:
        for action_name in list(self._counts.keys()):
            self._sync_widgets(action_name)

    def sync_widget(self, widget: QWidget) -> None:
        tracked_names = self._tracked_action_names(widget)
        pending = any(self.is_pending(name) for name in tracked_names)
        widget.setEnabled(not pending)
        self._sync_loading_feedback(widget, pending)

    def _sync_widgets(self, action_name: str) -> None:
        if not action_name:
            return
        normalized_action = str(action_name or "").strip()
        if not normalized_action:
            return
        for widget in self.window.findChildren(QWidget):
            tracked_names = self._tracked_action_names(widget)
            if normalized_action not in tracked_names:
                continue
            pending = any(self.is_pending(name) for name in tracked_names)
            widget.setEnabled(not pending)
            self._sync_loading_feedback(widget, pending)

    def _tracked_action_names(self, widget: QWidget) -> list[str]:
        raw_tracked = widget.property("_track_loading_names")
        if isinstance(raw_tracked, (list, tuple, set)):
            names = [str(item or "").strip() for item in raw_tracked]
            return [name for name in names if name]

        current = str(widget.property("_action_name") or "").strip()
        return [current] if current else []

    def _sync_loading_feedback(self, widget: QWidget, pending: bool) -> None:
        if not isinstance(widget, (QPushButton, QToolButton)):
            return
        if pending:
            self._start_loading_feedback(widget)
            return
        self._stop_loading_feedback(widget)

    def _start_loading_feedback(self, widget: QPushButton | QToolButton) -> None:
        if bool(widget.property("_loading_feedback_active")):
            return

        setattr(widget, "_loading_original_icon", widget.icon())
        if isinstance(widget, QPushButton):
            setattr(widget, "_loading_original_text", widget.text())
        widget.setProperty("_loading_feedback_active", True)

        timer = QTimer(widget)
        timer.setInterval(90)
        timer.timeout.connect(lambda w=widget: self._advance_spinner_frame(w))
        setattr(widget, "_loading_feedback_timer", timer)
        self._advance_spinner_frame(widget)
        timer.start()

    def _stop_loading_feedback(self, widget: QPushButton | QToolButton) -> None:
        timer = getattr(widget, "_loading_feedback_timer", None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
            setattr(widget, "_loading_feedback_timer", None)

        if not bool(widget.property("_loading_feedback_active")):
            return

        original_icon = getattr(widget, "_loading_original_icon", None)
        if isinstance(original_icon, QIcon):
            widget.setIcon(original_icon)
        if isinstance(widget, QPushButton):
            original_text = getattr(widget, "_loading_original_text", None)
            if isinstance(original_text, str):
                widget.setText(original_text)

        icon_swap = getattr(widget, "_icon_swap", None)
        if icon_swap is not None and hasattr(icon_swap, "apply_current"):
            icon_swap.apply_current()

        widget.setProperty("_loading_feedback_active", False)
        widget.setProperty("_loading_feedback_angle", 0)

    def _advance_spinner_frame(self, widget: QPushButton | QToolButton) -> None:
        current_angle = int(widget.property("_loading_feedback_angle") or 0)
        next_angle = (current_angle + 30) % 360
        widget.setProperty("_loading_feedback_angle", next_angle)

        icon_size = widget.iconSize()
        if not icon_size.isValid():
            icon_size = QSize(18, 18)
        if icon_size.width() <= 0 or icon_size.height() <= 0:
            icon_size = QSize(18, 18)

        spinner_icon = get_icon("ric.loader-4-line", self._spinner_color(widget), max(icon_size.width(), icon_size.height()))
        pixmap = spinner_icon.pixmap(icon_size)
        rotated = pixmap.transformed(QTransform().rotate(next_angle), Qt.SmoothTransformation)
        widget.setIcon(QIcon(rotated))

    def _spinner_color(self, widget: QWidget) -> str:
        variant = str(widget.property("variant") or "").strip()
        appearance = str(widget.property("appearance") or "").strip()
        if appearance == "default" and variant in {
            "primary",
            "destructive",
            "success",
            "warning",
            "info",
        }:
            return "#FAFAFA"
        return "#94A3B8"
