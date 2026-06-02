from __future__ import annotations
import os
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer
from .....utils.paths import resolve_resource
from .common import apply_children_collection_patch


class ScrollAreaRenderer(BaseRenderer):
    component_type = "ScrollArea"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "style": self.PROPERTY,
            "content_style": self.PROPERTY,
            "transparent": self.PROPERTY,
            "scroll_x": self.PROPERTY,
            "scroll_y": self.PROPERTY,
            "content_vertical_policy": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        scroll = QScrollArea()
        scroll.setObjectName(comp_id)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        allow_scroll_x = bool(props.get("scroll_x", True))
        allow_scroll_y = bool(props.get("scroll_y", True))
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if allow_scroll_x
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
            if allow_scroll_y
            else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        if bool(props.get("transparent", False)):
            scroll.setStyleSheet(
                "QScrollArea { background: transparent; border: none; }"
                "QScrollArea > QWidget > QWidget { background: transparent; }"
            )
        elif props.get("style"):
            scroll.setStyleSheet(qss_for_widget_style(props.get("style"), comp_id))

        # Content widget
        content = QFrame()
        content.setObjectName(f"{comp_id}_content")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        if props.get("class"):
            content.setProperty("class", props.get("class"))
        if props.get("content_style"):
            content.setStyleSheet(
                qss_for_widget_style(props.get("content_style"), content.objectName())
            )
        vertical_policy_raw = str(
            props.get("content_vertical_policy") or "expanding"
        ).strip().lower()
        vertical_policy = (
            QSizePolicy.Policy.Maximum
            if vertical_policy_raw == "maximum"
            else QSizePolicy.Policy.Expanding
        )
        content.setSizePolicy(
            QSizePolicy.Policy.Expanding, vertical_policy
        )

        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        scroll.setWidget(content)
        scroll._surface_id = surface_id  # type: ignore[attr-defined]
        scroll._app_instance = app_instance  # type: ignore[attr-defined]
        scroll._comp_id = comp_id  # type: ignore[attr-defined]
        return scroll

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        content = widget.widget()
        if content and content.layout():
            layout = content.layout()
            # Only add spacer if no child is already stretching
            has_stretching_child = False
            for i in range(layout.count()):
                if layout.stretch(i) > 0:
                    has_stretching_child = True
                    break

            if not has_stretching_child:
                layout.addStretch()

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)
