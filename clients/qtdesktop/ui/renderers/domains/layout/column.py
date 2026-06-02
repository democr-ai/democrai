from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QSizePolicy, QVBoxLayout
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer
from .common import apply_children_collection_patch


class ColumnRenderer(BaseRenderer):
    component_type = "Column"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "align": self.COMPONENT,
            "padding": self.PROPERTY,
        }

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
        ui_role = props.get("ui_role")
        if ui_role:
            widget.setProperty("ui_role", str(ui_role))
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        widget.setLayout(layout)

        align = props.get("align", "top")
        match align:
            case "top":
                layout.setAlignment(Qt.AlignmentFlag.AlignTop)
            case "bottom":
                layout.setAlignment(Qt.AlignmentFlag.AlignBottom)
            case "left":
                layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            case "right":
                layout.setAlignment(Qt.AlignmentFlag.AlignRight)
            case "center":
                layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            case "fill":
                pass
            case _:
                pass

        if props.get("width", None):
            widget.setMinimumWidth(int(props.get("width") or 0))
        if props.get("max_width", None):
            widget.setMaximumWidth(int(props.get("max_width") or 0))
        if props.get("style", None):
            widget.setStyleSheet(qss_for_widget_style(props.get("style"), comp_id))
        if props.get("padding", None):
            layout.setContentsMargins(*props.get("padding") or [0, 0, 0, 0])

        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        return widget

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        align = props.get("align", "top")
        if align == "top":
            layout = widget.layout()
            if layout:
                layout.setAlignment(Qt.AlignmentFlag.AlignTop)
                # Only add spacer if no child is already stretching
                has_stretching_child = False
                for i in range(layout.count()):
                    if layout.stretch(i) > 0:
                        has_stretching_child = True
                        break

                if not has_stretching_child:
                    layout.addStretch(1)

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)
