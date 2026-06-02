from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QTextEdit, QWidget
from ...base import BaseRenderer, emit_action_spec, publish_bound_value
from .common import _collection_items, _literal, _resolve_collection_index

class ScrollToBottomButtonRenderer(BaseRenderer):
    component_type = "ScrollToBottomButton"

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        button = QPushButton(_literal(props.get("label"), "Jump to latest"))
        button.setObjectName(comp_id)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("ui_role", "advanced_scroll_bottom_btn")
        action = props.get("action")
        if action:
            button.clicked.connect(
                lambda: emit_action_spec(
                    app_instance,
                    action,
                    {},
                    surface_id,
                    comp_id,
                )
            )
        return button
