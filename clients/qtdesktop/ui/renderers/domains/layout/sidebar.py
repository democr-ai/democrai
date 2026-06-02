from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QSizePolicy, QVBoxLayout
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer
from ....theme.tokens import current_theme, theme_token
from .common import _to_px, apply_children_collection_patch

class SidebarRenderer(BaseRenderer):
    component_type = "Sidebar"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "width": self.PROPERTY,
            "max_width": self.PROPERTY,
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
        elif comp_id != "main_sidebar":
            widget.setProperty("ui_role", "sidebar_panel")
        layout = QVBoxLayout()
        # layout.setContentsMargins(16, 8, 0, 0)
        # layout.setSpacing(8)
        widget.setLayout(layout)

        if comp_id == "main_sidebar":
            widget.setFixedWidth(64)
            layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        else:
            width_px = _to_px(props.get("width"))
            if width_px is not None:
                widget.setMinimumWidth(width_px)
            max_width_px = _to_px(props.get("max_width"))
            if max_width_px is not None:
                widget.setMaximumWidth(max_width_px)

        default_theme = current_theme(app_instance=app_instance)
        if default_theme == "light":
            default_bg = theme_token("surface.main", app_instance=app_instance)
        else:
            default_bg = theme_token("surface.sidebar", app_instance=app_instance)
        default_border = theme_token("border.sidebar", app_instance=app_instance)

        # This allows inline styles to override if needed, but we keep it minimal
        if props.get("style", None):
            style = props.get("style", None)
            if comp_id != "main_sidebar":
                style_text = str(style or "")
                if "background-color" not in style_text:
                    style_text = f"background-color: {default_bg}; " + style_text
                if "border-right" not in style_text:
                    style_text = f"border-right: 1px solid {default_border}; " + style_text
                style = style_text
            widget.setStyleSheet(qss_for_widget_style(style, comp_id))
        elif comp_id != "main_sidebar":
            widget.setStyleSheet(
                f"#{comp_id} {{ background-color: {default_bg}; border-right: 1px solid {default_border}; }}"
            )

        widget.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        return widget

    def before_children_render(self, widget, props, surface_id, app_instance, comp_id):
        pass

    def after_children_render(self, widget, props, surface_id, app_instance, comp_id):
        # Ensure items stay at the top for sidebars, but allow the sidebar
        # widget itself to stretch in its parent layout.
        layout = widget.layout()
        if layout:
            # Main sidebar: give flexible height to top_nav so overflow logic
            # can use real available space. nav_spacer would otherwise consume
            # all extra space and collapse top_nav to its minimum height.
            if comp_id == "main_sidebar":
                top_idx = -1
                spacer_idx = -1
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    child = item.widget() if item is not None else None
                    if child is None:
                        continue
                    name = child.objectName()
                    if name == "top_nav":
                        top_idx = i
                    elif name == "nav_spacer":
                        spacer_idx = i
                if top_idx >= 0:
                    layout.setStretch(top_idx, 1)
                if spacer_idx >= 0:
                    layout.setStretch(spacer_idx, 0)

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

    def update_widget_property(self, widget, prop: str, value: Any) -> None:
        if prop == "width":
            width_px = _to_px(value)
            if width_px is not None:
                widget.setMinimumWidth(width_px)
                if widget.maximumWidth() < width_px:
                    widget.setMaximumWidth(width_px)
            return
        if prop == "max_width":
            max_width_px = _to_px(value)
            if max_width_px is not None:
                widget.setMaximumWidth(max_width_px)
                if widget.minimumWidth() > max_width_px:
                    widget.setMinimumWidth(max_width_px)
            return
        super().update_widget_property(widget, prop, value)
