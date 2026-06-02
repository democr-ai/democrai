from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QPoint, QTimer, Qt
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .animation import fade_in, fade_out, slide


class ToastChip(QFrame):
    def __init__(self, payload: dict[str, Any], parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("toast_chip")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        title = str(payload.get("title") or payload.get("kind") or "Notification")
        message = str(payload.get("text") or payload.get("message") or payload.get("description") or "")
        variant = str(payload.get("variant") or "info").lower()
        duration = int(payload.get("duration", 2600) or 2600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #F8FAFC; font-size: 13px; font-weight: 700;")
        layout.addWidget(title_label)

        if message:
            body_label = QLabel(message)
            body_label.setWordWrap(True)
            body_label.setStyleSheet("color: #CBD5E1; font-size: 12px;")
            layout.addWidget(body_label)

        bg, border = _toast_palette(variant)
        self.setStyleSheet(
            f"""
            QFrame#toast_chip {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 14px;
            }}
            """
        )
        self.setMaximumWidth(360)

        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.setInterval(max(duration, 600))
        self._dismiss_timer.timeout.connect(self.dismiss)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        end_pos = self.pos()
        slide(self, start=end_pos + self.parent_offset(), end=end_pos, duration=180)
        fade_in(self, duration=180, start=0.0, end=1.0)
        self._dismiss_timer.start()

    def dismiss(self) -> None:
        end_pos = self.pos() + self.parent_offset()
        slide(self, start=self.pos(), end=end_pos, duration=160)
        fade_out(self, duration=160, start=1.0, end=0.0, hide_on_finish=False, finished=self.deleteLater)

    def parent_offset(self):
        return QPoint(36, 0)


class ToastViewport(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast_viewport")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 18, 18, 0)
        self._layout.setSpacing(10)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        parent.installEventFilter(self)
        self.setGeometry(parent.rect())
        self.raise_()

    def eventFilter(self, watched, event):
        if watched is self.parent() and event.type() in {QEvent.Type.Resize, QEvent.Type.Move, QEvent.Type.Show}:
            self.setGeometry(self.parentWidget().rect())
            self.raise_()
        return super().eventFilter(watched, event)

    def show_toast(self, payload: dict[str, Any]) -> None:
        while self._layout.count() >= 4:
            item = self._layout.takeAt(self._layout.count() - 1)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        toast = ToastChip(payload, self)
        self._layout.insertWidget(0, toast)
        self.raise_()
        toast.show()


def _toast_palette(variant: str) -> tuple[str, str]:
    match variant:
        case "success":
            return "#052E1A", "#166534"
        case "warning":
            return "#3B2006", "#B45309"
        case "error" | "destructive":
            return "#3F0D13", "#B91C1C"
        case _:
            return "#0F172A", "#334155"
