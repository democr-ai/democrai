from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer
from .common import _to_px, apply_children_collection_patch


class RowRenderer(BaseRenderer):
    component_type = "Row"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "align": self.COMPONENT,
            "spacing": self.PROPERTY,
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
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        spacing = props.get("spacing", 0)
        layout.setSpacing(spacing)
        widget.setLayout(layout)

        align = props.get("align", "left")
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

        width_px = _to_px(props.get("width"))
        if width_px is not None:
            widget.setFixedWidth(width_px)
        height_px = _to_px(props.get("height"))
        if height_px is not None:
            widget.setFixedHeight(height_px)
        if props.get("style", None):
            widget.setStyleSheet(qss_for_widget_style(props.get("style"), comp_id))
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        return widget

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)

    def update_widget_property(self, widget, prop: str, value: Any) -> None:
        if prop == "spacing":
            layout = widget.layout()
            if layout is not None:
                layout.setSpacing(int(value or 0))
            return
        super().update_widget_property(widget, prop, value)
