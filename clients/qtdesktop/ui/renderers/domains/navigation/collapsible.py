from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget
from ...base import BaseRenderer
from .common import _literal

class CollapsibleRenderer(BaseRenderer):
    component_type = "Collapsible"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "title": self.COMPONENT,
            "content": self.COMPONENT,
            "open": self.COMPONENT,
            "children": self.COMPONENT,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        del surface_id, app_instance
        container = QFrame()
        container.setObjectName(comp_id)
        container.setProperty("ui_role", "collapsible_block")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        button = QToolButton()
        button.setText(_literal(props.get("title")))
        button.setCheckable(True)
        button.setChecked(bool(props.get("open", False)))
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        button.setArrowType(Qt.DownArrow if button.isChecked() else Qt.RightArrow)
        button.setProperty("ui_role", "collapsible_trigger")
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        panel = QFrame()
        panel.setProperty("ui_role", "collapsible_content_panel")
        panel.setVisible(button.isChecked())
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.setSpacing(6)

        content = QLabel(_literal(props.get("content")))
        content.setWordWrap(True)
        content.setProperty("ui_role", "collapsible_content")
        panel_layout.addWidget(content)

        button.toggled.connect(
            lambda checked, btn=button: btn.setArrowType(
                Qt.DownArrow if checked else Qt.RightArrow
            )
        )
        button.toggled.connect(panel.setVisible)

        layout.addWidget(button)
        layout.addWidget(panel)
        setattr(container, "_collapsible_panel", panel)
        return container

    def add_child_to_widget(self, widget: QWidget, child_widget: QWidget) -> None:
        panel = getattr(widget, "_collapsible_panel", None)
        if panel is not None:
            panel_layout = panel.layout()
            if panel_layout is not None:
                panel_layout.insertWidget(0, child_widget)
                return
        layout = widget.layout()
        if layout is not None:
            layout.addWidget(child_widget)
