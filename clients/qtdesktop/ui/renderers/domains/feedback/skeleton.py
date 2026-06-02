from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QLabel,
    QMenu,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)
from ...base import BaseRenderer, emit_action, publish_bound_value
from .common import _field_shell, _literal, _parse_qdate

class SkeletonRenderer(BaseRenderer):
    component_type = "Skeleton"

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        frame = QFrame()
        frame.setObjectName(comp_id)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        widths = props.get("widths", []) or []
        if props.get("avatar"):
            avatar = QFrame()
            avatar.setFixedSize(42, 42)
            avatar.setProperty("ui_role", "advanced_skeleton_avatar")
            layout.addWidget(avatar)

        for index in range(max(1, int(props.get("lines", 3)))):
            line = QFrame()
            width = widths[index] if index < len(widths) else max(120, 300 - (index * 40))
            line.setFixedHeight(12)
            line.setFixedWidth(int(width))
            line.setProperty("ui_role", "advanced_skeleton_line")
            layout.addWidget(line)
        return frame
