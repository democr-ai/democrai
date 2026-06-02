from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout
from ....animation import fade_in, slide
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer

class SurfaceHostRenderer(BaseRenderer):
    component_type = "SurfaceHost"

    def binding_strategies(self) -> Dict[str, str]:
        return {**super().binding_strategies(), "children": self.COMPONENT}

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        widget = QFrame()
        widget.setObjectName(comp_id)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        widget.setProperty("surface_host_id", props.get("surface_id"))
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        widget.setLayout(layout)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        if props.get("style", None):
            widget.setStyleSheet(qss_for_widget_style(props.get("style"), comp_id))
        return widget
