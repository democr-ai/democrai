from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QWidget

from ...base import BaseRenderer
from ...collection_patch import patch_collection


def _clear_layout(layout: QHBoxLayout) -> None:
    while layout.count():
        child = layout.takeAt(0)
        widget = child.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()


class HeaderRenderer(BaseRenderer):
    component_type = "Header"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "left": self.COMPONENT,
            "center": self.COMPONENT,
            "right": self.COMPONENT,
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
        widget.setProperty("ui_role", "header")
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QHBoxLayout(widget)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        left_host = QFrame()
        center_host = QFrame()
        right_host = QFrame()
        left_layout = QHBoxLayout(left_host)
        center_layout = QHBoxLayout(center_host)
        right_layout = QHBoxLayout(right_host)
        for slot_layout in (left_layout, center_layout, right_layout):
            slot_layout.setContentsMargins(0, 0, 0, 0)
            slot_layout.setSpacing(8)
        left_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        center_layout.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        right_layout.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )

        left_host.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        center_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        right_host.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )

        root.addWidget(left_host, 0)
        root.addWidget(center_host, 1)
        root.addWidget(right_host, 0)

        widget._header_props = dict(props)  # type: ignore[attr-defined]
        widget._header_surface_id = surface_id  # type: ignore[attr-defined]
        widget._header_app = app_instance  # type: ignore[attr-defined]
        widget._header_comp_id = comp_id  # type: ignore[attr-defined]
        widget._header_left_layout = left_layout  # type: ignore[attr-defined]
        widget._header_center_layout = center_layout  # type: ignore[attr-defined]
        widget._header_right_layout = right_layout  # type: ignore[attr-defined]
        self._build(widget)
        return widget

    def _build(self, widget: QWidget) -> None:
        props = dict(getattr(widget, "_header_props", {}))
        surface_id = str(getattr(widget, "_header_surface_id", "main"))
        app_instance = getattr(widget, "_header_app", None)
        if app_instance is None:
            return

        left_layout: QHBoxLayout = getattr(widget, "_header_left_layout")
        center_layout: QHBoxLayout = getattr(widget, "_header_center_layout")
        right_layout: QHBoxLayout = getattr(widget, "_header_right_layout")
        for slot_layout in (left_layout, center_layout, right_layout):
            _clear_layout(slot_layout)

        left = props.get("left", [])
        center = props.get("center", [])
        right = props.get("right", [])

        # Compatibility: legacy Header children are mapped to center slot.
        if not left and not center and not right:
            children = props.get("children", {})
            if isinstance(children, dict):
                center = children.get("explicitList", []) or []

        self._populate_slot(left_layout, left, surface_id, app_instance)
        self._populate_slot(center_layout, center, surface_id, app_instance)
        self._populate_slot(right_layout, right, surface_id, app_instance)

    def _populate_slot(
        self,
        layout: QHBoxLayout,
        items: Any,
        surface_id: str,
        app_instance: Any,
    ) -> None:
        if not isinstance(items, list):
            return
        for child in items:
            child_widget = None
            if isinstance(child, dict):
                child_widget = app_instance.renderer.build_widget(
                    surface_id,
                    app_instance.surfaces,
                    comp_def=child,
                    app_instance=app_instance,
                    seen_dialogs=set(),
                )
            elif isinstance(child, str):
                child_widget = app_instance.renderer.build_widget(
                    surface_id,
                    app_instance.surfaces,
                    comp_id=child,
                    app_instance=app_instance,
                    seen_dialogs=set(),
                )
            if child_widget is not None:
                layout.addWidget(child_widget)

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop in {"left", "center", "right", "children"}:
            props = dict(getattr(widget, "_header_props", {}))
            props[prop] = value
            widget._header_props = props  # type: ignore[attr-defined]
            self._build(widget)
            return
        super().update_widget_property(widget, prop, value)

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        if prop not in {"left", "center", "right"}:
            return False
        props = dict(getattr(widget, "_header_props", {}))
        current = list(props.get(prop, []))
        patch = patch_collection(current, action, value)
        if not patch.handled:
            return False
        props[prop] = patch.items
        widget._header_props = props  # type: ignore[attr-defined]
        self._build(widget)
        return True
