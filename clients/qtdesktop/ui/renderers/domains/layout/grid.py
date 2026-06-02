from __future__ import annotations
import os
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QScrollArea, QSplitter, QTabWidget, QSizePolicy, QVBoxLayout, QWidget
from ...base import BaseRenderer
from .....utils.paths import resolve_resource

class GridRenderer(BaseRenderer):
    component_type = "Grid"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "columns": self.COMPONENT,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        columns = props.get("columns", 2)
        widget = QFrame()
        widget.setObjectName(comp_id)
        layout = QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        widget.setLayout(layout)

        # We need to track the current grid position
        widget.setProperty("_grid_columns", columns)

        return widget

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def add_child_to_widget(self, parent_widget, child_widget):
        layout = parent_widget.layout()
        if not layout:
            return

        columns = parent_widget.property("_grid_columns") or 2
        count = layout.count()
        row = count // columns
        col = count % columns

        layout.addWidget(child_widget, row, col)
