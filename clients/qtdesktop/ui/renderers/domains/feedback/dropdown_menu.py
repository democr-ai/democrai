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
from ...base import BaseRenderer, emit_action_spec, publish_bound_value
from .common import _field_shell, _literal, _parse_qdate

class DropdownMenuRenderer(BaseRenderer):
    component_type = "DropdownMenu"

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        button = QToolButton()
        button.setObjectName(comp_id)
        button.setText(_literal(props.get("label"), "Actions"))
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("ui_role", "advanced_dropdown_btn")
        menu = QMenu(button)
        menu.setProperty("ui_role", "advanced_dropdown_menu")
        for item in props.get("items", []):
            action = QAction(str(item.get("label", "Action")), menu)
            payload = item.get("action", {})
            action.triggered.connect(
                lambda _=False, payload=payload: emit_action_spec(
                    app_instance,
                    payload,
                    {},
                    surface_id,
                    comp_id,
                )
            )
            menu.addAction(action)
        button.setMenu(menu)
        return button
