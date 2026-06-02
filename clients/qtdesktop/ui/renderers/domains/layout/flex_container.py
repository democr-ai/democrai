from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout, QSizePolicy
from ...base import BaseRenderer
from .common import apply_children_collection_patch


class FlexContainerRenderer(BaseRenderer):
    """
    Renders a FlexContainer — a direction-agnostic container that always
    expands to fill available space. Equivalent to Column with stretch=True
    but without alignment/direction semantics.
    """

    component_type = "FlexContainer"

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
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        return widget

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)
