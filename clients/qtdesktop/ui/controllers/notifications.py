from __future__ import annotations

from typing import Any

from PySide6.QtCore import QTimer

_POLL_INTERVAL_MS = 30_000


class NotificationController:
    """Desktop notification hub: toasts + notification badge (via store)."""

    def __init__(self, window: Any, *, background_tasks: Any | None = None) -> None:
        self.window = window
        self.background_tasks = background_tasks
        self._pending_count: int = 0
        self._poll_timer = QTimer(window)
        self._poll_timer.setInterval(_POLL_INTERVAL_MS)
        self._poll_timer.timeout.connect(self._poll_notifications_count)

    def show_event(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        if self.background_tasks is not None:
            self.background_tasks.event_notification(payload)
        if str(payload.get("kind") or "").lower() != "toast":
            return
        viewport = getattr(self.window, "toast_viewport", None)
        if viewport is None:
            return
        viewport.show_toast(payload)

    def handle_notifications_update(self, count: int) -> None:
        self._pending_count = max(0, int(count or 0))
        store = getattr(self.window, "store", None)
        if store is not None:
            store.set("/core/notifications/pending_count", self._pending_count)

    def start_polling(self) -> None:
        """Start periodic notification count refresh (called on socket connect)."""
        if not self._poll_timer.isActive():
            self.refresh_count()
            self._poll_timer.start()

    def stop_polling(self) -> None:
        """Stop periodic refresh (called on socket disconnect/error)."""
        self._poll_timer.stop()

    def refresh_count(self) -> None:
        """Force an immediate refresh of the notification count."""
        action_ctrl = getattr(self.window, "_action", None)
        if action_ctrl is None:
            return
        renderer = getattr(self.window, "renderer", None)
        if renderer is not None and not getattr(renderer, "is_connected", False):
            return
        try:
            action_ctrl.send_action("get_notifications_count", {}, "main", "")
        except Exception:
            pass

    def _poll_notifications_count(self) -> None:
        # Compatibility shim for existing timer connections if any (though we update it in __init__)
        self.refresh_count()
