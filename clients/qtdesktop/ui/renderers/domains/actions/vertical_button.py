from PySide6.QtWidgets import QLabel, QPushButton, QToolButton, QHBoxLayout, QSizePolicy
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, Qt, QObject, QEvent
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from ...base import BaseRenderer, emit_action
from ...icon import get_icon, get_icon_gliph
from ....theme.tokens import button_icon_colors as resolve_button_icon_colors
from .....utils.paths import resolve_resource
import os
import time

_BUTTON_VARIANT_ALIASES = {
    "primary": "default",
    "danger": "destructive",
    "info": "secondary",
    "warning": "warning",
    "success": "success",
}

_BUTTON_SIZE_ALIASES = {
    "small": "sm",
    "normal": "default",
    "large": "lg",
}

def normalize_button_variant(variant: str) -> str:
    return _BUTTON_VARIANT_ALIASES.get(variant, variant)

def normalize_button_size(size: str) -> str:
    return _BUTTON_SIZE_ALIASES.get(size, size)

def normalize_button_appearance(mode: str) -> str:
    return "default" if mode == "solid" else mode

def button_icon_colors(
    variant: str,
    appearance: str,
    shape: str,
    active: bool,
    *,
    app_instance: Any | None = None,
) -> tuple[str, str]:
    return resolve_button_icon_colors(
        variant=normalize_button_variant(variant),
        appearance=appearance,
        shape=shape,
        active=active,
        profile="contrast",
        app_instance=app_instance,
    )

def _escape_qt_mnemonic(text: Any) -> str:
    raw = "" if text is None else str(text)
    return raw.replace("&", "&&")

def _normalize_image_source(url: str, app_instance: Any) -> str:
    del app_instance
    return str(url or "")

def _normalize_track_loading(value: Any, fallback_action_name: str = "") -> list[str]:
    names: list[str] = []
    if isinstance(value, (list, tuple, set)):
        names.extend(str(item or "").strip() for item in value)
    elif value is not None:
        raw = str(value).strip()
        if raw:
            names.append(raw)

    normalized = [name for name in names if name]
    if normalized:
        return normalized

    fallback = str(fallback_action_name or "").strip()
    return [fallback] if fallback else []

class IconSwapOnHover(QObject):
    def __init__(self, btn: QPushButton, icon_normal, icon_hover):
        super().__init__(btn)
        self.btn = btn
        self.icon_normal = icon_normal
        self.icon_hover = icon_hover

        btn.setAttribute(Qt.WA_Hover, True)
        btn.setMouseTracking(True)
        btn.installEventFilter(self)
        self.apply_current()

    def set_icons(self, icon_normal, icon_hover):
        self.icon_normal = icon_normal
        self.icon_hover = icon_hover
        self.apply_current()

    def apply_current(self):
        # se il mouse è sopra, mostra subito hover
        self.btn.setIcon(self.icon_hover if self.btn.underMouse() else self.icon_normal)

    def eventFilter(self, obj, ev):
        if obj is self.btn:
            if ev.type() in (QEvent.Enter, QEvent.HoverEnter):
                obj.setIcon(self.icon_hover)
            elif ev.type() in (QEvent.Leave, QEvent.HoverLeave):
                obj.setIcon(self.icon_normal)
        return False

class VerticalButtonRenderer(BaseRenderer):
    component_type = "VerticalButton"

    @staticmethod
    def _resolve_action_context(
        app_instance: Any,
        context: Any,
        surface_id: str | None = None,
    ) -> dict:
        if not isinstance(context, dict):
            return {}

        bindings = getattr(app_instance, "bindings", None)
        if bindings is None:
            return context

        def _resolve(value: Any) -> Any:
            if isinstance(value, dict):
                value_type = value.get("type")
                if value_type in {"store", "action", "literal"} or (
                    "path" in value and "type" not in value
                ):
                    try:
                        if hasattr(bindings, "resolve_value_for_surface"):
                            return bindings.resolve_value_for_surface(value, surface_id)
                        if hasattr(bindings, "resolve_value"):
                            return bindings.resolve_value(value)
                        return value
                    except Exception:
                        return None
                return {k: _resolve(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_resolve(v) for v in value]
            if isinstance(value, str):
                try:
                    if hasattr(bindings, "resolve_value_for_surface"):
                        return bindings.resolve_value_for_surface(value, surface_id)
                    if hasattr(bindings, "resolve_value"):
                        return bindings.resolve_value(value)
                    return value
                except Exception:
                    return value
            return value

        resolved = _resolve(context)
        return resolved if isinstance(resolved, dict) else context

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        label = props.get("label", {}).get("literalString", "Button")
        icon_name = props.get("icon", {}).get("iconName")

        widget = QToolButton()
        widget.setObjectName(comp_id)
        widget.setToolTip(label)
        widget.setCursor(Qt.CursorShape.PointingHandCursor)

        # Handle active state
        active_prop = props.get("active", "false")
        if not isinstance(active_prop, dict):
            # Static value
            active = str(active_prop).lower()
            if active in ("1", "yes", "true"):
                active = "true"
            else:
                active = "false"
            widget.setProperty("active", active)
        # If it's a dict (binding), setup_bindings will handle it via update_widget_property normalization

        if icon_name:
            widget.setIcon(get_icon(icon_name))
            widget.setIconSize(QSize(24, 24))
            widget.setFixedWidth(45)
            widget.setFixedHeight(45)

        widget.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        widget.setProperty("ui_role", "vertical_button")
        widget.style().unpolish(widget)
        widget.style().polish(widget)

        if "action" in props:
            action = props["action"]
            action_name = str(action.get("name", "")).strip()
            widget.setProperty("_action_name", action_name)
            widget.setProperty("track_loading", props.get("track_loading"))
            track_loading_names = _normalize_track_loading(
                props.get("track_loading"),
                action_name,
            )
            widget.setProperty("_track_loading_names", track_loading_names)
            if track_loading_names:
                action_locks = getattr(app_instance, "_action_locks", None)
                if action_locks is not None:
                    action_locks.sync_widget(widget)
            collect_input_ids = props.get("collect_input_ids")
            widget.clicked.connect(
                lambda: emit_action(
                    app_instance,
                    action_name,
                    {
                        **self._resolve_action_context(
                            app_instance,
                            action.get("context", {}),
                            surface_id,
                        ),
                        **(
                            {"__client__": {"collect_input_ids": collect_input_ids}}
                            if isinstance(collect_input_ids, list) and collect_input_ids
                            else {}
                        ),
                    },
                    surface_id,
                    comp_id,
                )
            )
        return widget
