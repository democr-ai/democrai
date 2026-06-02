from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, Optional

from ...base import BaseRenderer

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QSize

from ...icon import get_icon

_STATUS_ICONS = {
    "started": ("ric.time-line", "#71717a"),
    "running": ("ric.loader-line", "#3b82f6"),
    "completed": ("ric.checkbox-circle-line", "#22c55e"),
    "failed": ("ric.close-circle-line", "#ef4444"),
    "interrupted": ("ric.close-circle-line", "#ef4444"),
    "waiting_confirmation": ("ric.question-line", "#eab308"),
}
_ICON_SIZE = 16


class BackgroundTaskCard(QWidget):
    """Standalone widget that shows the state of a single background task.

    Binds to the global store under ``background_tasks.<task_id>`` and
    updates automatically when the store changes.  On first show, if the
    task is not yet in the store, it requests the current state from the
    backend via ``background_task.get``.
    """

    def __init__(
        self,
        task_id: str,
        *,
        event_actions: dict[str, Any] | None = None,
        store: Any,
        app_instance: Any = None,
        surface_id: str = "main",
        comp_id: str = "unknown",
        send_action: Callable[[str, dict, str, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._task_id = task_id
        self._event_actions = dict(event_actions or {})
        self._store = store
        self._app_instance = app_instance
        self._surface_id = surface_id
        self._comp_id = comp_id
        self._send_action = send_action
        self._store_prefix = f"/background_tasks/{task_id}"
        self._listener_id = f"background_task_card:{comp_id}:{uuid.uuid4().hex}"

        self._build_ui()
        self._refresh_from_store()
        self._register_event_listener()

        store.changed.connect(self._on_store_changed)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._unregister_event_listener()
        super().closeEvent(event)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(6)

        # Header row: icon + label
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._icon_label = QLabel()
        self._icon_label.setFixedSize(QSize(_ICON_SIZE, _ICON_SIZE))
        header_layout.addWidget(self._icon_label)

        self._task_label = QLabel()
        self._task_label.setProperty("ui_role", "background_task_label")
        self._task_label.setWordWrap(True)
        self._task_label.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self._task_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        header_layout.addWidget(self._task_label)

        root.addWidget(header)

        # Progress bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setProperty("ui_role", "background_task_progress")
        root.addWidget(self._progress_bar)

        self.setProperty("ui_role", "background_task_card")

    def _register_event_listener(self) -> None:
        tracker = getattr(self._app_instance, "_background_tasks", None)
        if tracker is None or not hasattr(tracker, "register_listener"):
            return
        tracker.register_listener(
            self._listener_id,
            task_id=self._task_id,
            actions=self._event_actions,
            send_action=self._send_action,
            surface_id=self._surface_id,
            comp_id=self._comp_id,
        )

    def _unregister_event_listener(self) -> None:
        tracker = getattr(self._app_instance, "_background_tasks", None)
        if tracker is None or not hasattr(tracker, "unregister_listener"):
            return
        tracker.unregister_listener(self._listener_id)

    # ------------------------------------------------------------------
    # Store binding
    # ------------------------------------------------------------------

    def _on_store_changed(self, path: str, value: Any) -> None:
        if path.startswith(self._store_prefix):
            self._refresh_from_store()

    def _refresh_from_store(self) -> None:
        task = self._store.get(
            f"background_tasks.{self._task_id}", None, "global"
        )
        if task is None:
            self._send_action("background_task.get", {"task_id": self._task_id}, "main", "")
            self._apply_state({"status": "started", "label": self._task_id, "progress": 0})
            return
        self._apply_state(task)

    def _apply_state(self, task: dict) -> None:
        status = str(task.get("status") or "started")
        label = str(task.get("label") or self._task_id)
        progress = float(task.get("progress") or 0.0)

        # Icon
        icon_name, icon_color = _STATUS_ICONS.get(status, ("ric.time-line", "#71717a"))
        self._icon_label.setPixmap(
            get_icon(icon_name, icon_color, _ICON_SIZE).pixmap(QSize(_ICON_SIZE, _ICON_SIZE))
        )

        # Label
        self._task_label.setText(label)

        # Progress bar
        is_done = status in ("completed", "failed", "interrupted")
        self._progress_bar.setVisible(not is_done)
        if not is_done:
            target = int(round(progress * 100))
            anim = QPropertyAnimation(self._progress_bar, b"value")
            anim.setDuration(400)
            anim.setStartValue(self._progress_bar.value())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._progress_bar._anim = anim
            anim.start()


class BackgroundTaskRenderer(BaseRenderer):
    """Renderer for the BackgroundTask component type."""

    component_type = "BackgroundTask"

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ) -> Optional[Any]:
        task_id = str(props.get("task_id") or "")
        event_actions = {
            "on_finish": props.get("on_finish"),
            "on_started": props.get("on_started"),
            "on_progress": props.get("on_progress"),
            "on_completed": props.get("on_completed"),
            "on_error": props.get("on_error"),
            "on_confirmation": props.get("on_confirmation"),
            "on_update": props.get("on_update"),
            "on_event_notification": props.get("on_event_notification"),
        }
        card = BackgroundTaskCard(
            task_id=task_id,
            event_actions=event_actions,
            store=app_instance.store,
            app_instance=app_instance,
            surface_id=surface_id,
            comp_id=comp_id,
            send_action=app_instance._action.send_action,
        )
        card.setObjectName(comp_id)
        return card
