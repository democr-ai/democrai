from PySide6.QtWidgets import (
    QWidget,
    QGridLayout,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QPushButton,
    QMenu,
)
from PySide6.QtCore import Qt, QMimeData, QPoint
from PySide6.QtGui import QDrag, QColor, QPalette, QPainter, QAction
from typing import Dict, Any, Optional, cast, List, Tuple
from ...base import BaseRenderer, emit_action


class DashboardWidgetRenderer(BaseRenderer):
    component_type = "DashboardWidget"

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        widget = QFrame()
        widget.setObjectName(comp_id)
        widget.setProperty("is_widget", True)

        size = props.get("size", "square")
        title = props.get("title", "Widget")

        # Sizes in terms of grid cells
        w, h = 1, 1
        if size == "rect_h":
            w, h = 2, 1
        elif size == "rect_v":
            w, h = 1, 2

        widget.setProperty("grid_w", w)
        widget.setProperty("grid_h", h)

        layout = QVBoxLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        widget.setLayout(layout)

        header_container = QFrame()
        header_container.setProperty("ui_role", "grid_widget_header")
        header_layout = QHBoxLayout(header_container)
        header_layout.setContentsMargins(8, 4, 8, 4)

        header = QLabel(title)
        header.setProperty("ui_role", "grid_widget_title")
        header_layout.addWidget(header)
        layout.addWidget(header_container)
        widget.header_container = header_container

        content = QFrame()
        content.setObjectName(f"{comp_id}_content")
        content.setProperty("ui_role", "grid_widget_content")
        layout.addWidget(content, 1)
        widget.setProperty("ui_role", "grid_widget_card")

        widget.setProperty("edit_mode", props.get("edit_mode", False))

        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # widget.setFixedSize(w * 150 + (w-1)*4, h * 150 + (h-1)*4)

        coords = props.get("coords")  # [row, col]
        if coords:
            widget.setProperty("grid_pos", tuple(coords))
        else:
            widget.setProperty("grid_pos", None)

        # Drag logic
        widget.mousePressEvent = lambda e: self._mousePressEvent(widget, e)  # type: ignore

        return widget

    def add_child_to_widget(self, parent_widget, child_widget):
        content = parent_widget.findChild(QFrame, f"{parent_widget.objectName()}_content")
        if content:
            if not content.layout():
                clayout = QVBoxLayout(content)
                clayout.setContentsMargins(0, 0, 0, 0)
                clayout.setSpacing(0)
            content.layout().addWidget(child_widget)
        else:
            parent_widget.layout().addWidget(child_widget)

    def _mousePressEvent(self, widget, event):
        if not widget.property("edit_mode"):
            return

        if event.button() == Qt.MouseButton.LeftButton:
            drag = QDrag(widget)
            mime_data = QMimeData()
            mime_data.setData("application/x-dashboard-widget", b"")
            # Store hotspot offset as comma-separated string
            mime_data.setText(f"{event.pos().x()},{event.pos().y()}")
            drag.setMimeData(mime_data)

            # Create a preview image
            pixmap = widget.grab()
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())

            drag.exec(Qt.DropAction.MoveAction)

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        if prop == "coords":
            widget.setProperty("grid_pos", tuple(value) if value else None)
            parent = widget.parentWidget()
            if parent and hasattr(parent, "relayout_widgets"):
                parent.relayout_widgets()
            return
        if prop == "edit_mode":
            widget.setProperty("edit_mode", value)
            return
        if prop == "size":
            w, h = 1, 1
            if value == "rect_h": w, h = 2, 1
            elif value == "rect_v": w, h = 1, 2
            widget.setProperty("grid_w", w)
            widget.setProperty("grid_h", h)
            parent = widget.parentWidget()
            if parent and hasattr(parent, "relayout_widgets"):
                parent.relayout_widgets()
            return
        super().update_widget_property(widget, prop, value)
