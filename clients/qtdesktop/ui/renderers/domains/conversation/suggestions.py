from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QPushButton, QTextEdit, QVBoxLayout, QWidget
from ...base import BaseRenderer, emit_action_spec, publish_bound_value
from .common import _collection_items, _literal, _resolve_collection_index

class SuggestionsRenderer(BaseRenderer):
    component_type = "Suggestions"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "suggestions": self.COMPONENT,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        frame = QFrame()
        frame.setObjectName(comp_id)
        layout = QGridLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        action = props.get("action")

        for index, suggestion in enumerate(props.get("suggestions", [])):
            btn = QPushButton(str(suggestion.get("label", suggestion.get("prompt", "Suggestion"))))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("ui_role", "advanced_suggestion_btn")
            btn.clicked.connect(
                lambda _=False, suggestion=suggestion: emit_action_spec(
                    app_instance,
                    action,
                    suggestion,
                    surface_id,
                    comp_id,
                )
            )
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 6, 0, 6)
            cell_layout.addWidget(btn)
            layout.addWidget(cell, index // 2, index % 2)
        return frame
