from __future__ import annotations
import os
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QScrollArea, QSplitter, QTabWidget, QSizePolicy, QVBoxLayout, QWidget
from ...base import BaseRenderer
from .common import apply_children_collection_patch
from .....utils.paths import resolve_resource

class SplitterRenderer(BaseRenderer):
    component_type = "Splitter"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "sizes": self.PROPERTY,
            "max_sizes": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        widget = QSplitter(Qt.Orientation.Horizontal)
        widget.setObjectName(comp_id)
        widget.setHandleWidth(1)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        # widget.setSizes(props.get("sizes"))  # 0 for hidden sub initially
        # widget.setCollapsible(0, False)
        return widget

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        sizes = props.get("sizes")
        if sizes:
            widget.setSizes(sizes)
        max_sizes = props.get("max_sizes")
        if isinstance(max_sizes, list):
            for index, raw in enumerate(max_sizes):
                try:
                    px = int(raw)
                except Exception:
                    continue
                if px <= 0:
                    continue
                child = widget.widget(index)
                if child is not None:
                    child.setMaximumWidth(px)
        widget.setCollapsible(0, True)

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)

    def update_widget_property(self, widget, prop, value) -> None:
        if prop == "sizes":
            sizes = self._int_list(value)
            if sizes:
                widget.setSizes(sizes)
            return
        if prop == "max_sizes":
            self._apply_max_sizes(widget, value)
            return
        super().update_widget_property(widget, prop, value)

    def _apply_max_sizes(self, widget, value) -> None:
        if not isinstance(value, list):
            return
        for index, raw in enumerate(value):
            try:
                px = int(raw)
            except Exception:
                continue
            if px <= 0:
                continue
            child = widget.widget(index)
            if child is not None:
                child.setMaximumWidth(px)

    def _int_list(self, value) -> list[int]:
        if not isinstance(value, list):
            return []
        sizes = []
        for raw in value:
            try:
                size = int(raw)
            except Exception:
                continue
            if size > 0:
                sizes.append(size)
        return sizes
