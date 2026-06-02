from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout
from ...base import BaseRenderer, emit_action
from .common import _literal

class BreadcrumbRenderer(BaseRenderer):
    component_type = "Breadcrumb"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "segments": self.PROPERTY,
            "separator": self.PROPERTY,
        }

    def _resolve_segment_field(
        self,
        value: Any,
        app_instance: Any,
        surface_id: str,
    ) -> Any:
        bindings = getattr(app_instance, "bindings", None)
        if bindings is None:
            return value
        return bindings.resolve_value_for_surface(value, surface_id)

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        frame = QFrame()
        frame.setObjectName(comp_id)
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        frame._breadcrumb_props = dict(props)  # type: ignore[attr-defined]
        frame._breadcrumb_surface_id = surface_id  # type: ignore[attr-defined]
        frame._breadcrumb_app = app_instance  # type: ignore[attr-defined]
        frame._breadcrumb_comp_id = comp_id  # type: ignore[attr-defined]
        self._build(frame)
        return frame

    def _clear_layout(self, layout: QHBoxLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

    def _build(self, frame: QFrame) -> None:
        layout = frame.layout()
        if not isinstance(layout, QHBoxLayout):
            return
        self._clear_layout(layout)
        props = dict(getattr(frame, "_breadcrumb_props", {}))
        surface_id = str(getattr(frame, "_breadcrumb_surface_id", "main"))
        app_instance = getattr(frame, "_breadcrumb_app", None)
        comp_id = str(getattr(frame, "_breadcrumb_comp_id", "unknown"))
        if app_instance is None:
            return
        separator = str(props.get("separator", "/"))

        segments = props.get("segments", [])
        if not isinstance(segments, list):
            segments = []

        for index, segment in enumerate(segments):
            if not isinstance(segment, dict):
                continue

            label = _literal(
                self._resolve_segment_field(segment.get("label", ""), app_instance, surface_id)
            )
            is_current = bool(
                self._resolve_segment_field(segment.get("current", False), app_instance, surface_id)
                or index == len(segments) - 1
            )
            path = self._resolve_segment_field(segment.get("path"), app_instance, surface_id)
            if path and not is_current:
                button = QPushButton(label)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setProperty("ui_role", "breadcrumb_btn")
                button.clicked.connect(
                    lambda _=False, target=path: emit_action(
                        app_instance,
                        "navigate",
                        {"path": target},
                        surface_id,
                        comp_id,
                    )
                )
                layout.addWidget(button)
            else:
                crumb = QLabel(label)
                crumb.setProperty("ui_role", "breadcrumb_crumb")
                crumb.setProperty("current", bool(is_current))
                layout.addWidget(crumb)

            if index < len(segments) - 1:
                sep = QLabel(separator)
                sep.setProperty("ui_role", "breadcrumb_sep")
                layout.addWidget(sep)

        layout.addStretch()

    def update_widget_property(self, widget, prop: str, value: Any) -> None:
        if prop in {"segments", "separator"}:
            props = dict(getattr(widget, "_breadcrumb_props", {}))
            props[prop] = value
            widget._breadcrumb_props = props  # type: ignore[attr-defined]
            self._build(widget)
            return
        super().update_widget_property(widget, prop, value)
