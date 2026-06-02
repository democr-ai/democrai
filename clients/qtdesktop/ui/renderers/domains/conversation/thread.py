from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout, QWidget
from ...base import BaseRenderer, emit_action
from .common import _clear_layout
from .message_list import _message_card


class ThreadRenderer(BaseRenderer):
    component_type = "Thread"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children":   self.COMPONENT,
            "auto_scroll": self.COMPONENT,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        frame = QFrame()
        frame.setObjectName(comp_id)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        frame.setProperty("ui_role", "advanced_thread")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        if props.get("auto_scroll", True):
            QTimer.singleShot(0, lambda: frame.ensurePolished())
        return frame
