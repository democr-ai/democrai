from PySide6.QtWidgets import QLabel, QPushButton, QToolButton, QHBoxLayout, QSizePolicy, QApplication
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, Qt, QObject, QEvent
from typing import Dict, Any, Optional
from urllib.parse import urlparse
from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer, emit_action_spec
from ...icon import get_icon, get_icon_gliph
from ....theme.tokens import button_icon_colors as resolve_button_icon_colors
from ....theme.tokens import theme_token
from .....utils.paths import resolve_resource
import os
import time

_BUTTON_VARIANT_ALIASES = {
    "primary": "primary",
    "danger": "destructive",
    "warning": "warning",
    "success": "success",
    "info": "info",
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
        profile="button",
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

class ButtonRenderer(BaseRenderer):
    component_type = "Button"

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

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "active": self.PROPERTY,
            "action": self.PROPERTY,
            "params": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        label = props.get("label", {}).get("literalString", "Button")
        icon_name = props.get("icon", {}).get("iconName")
        variant_raw = props.get("variant", "default")
        mode_raw = props.get("mode", "solid")
        size_raw = props.get("btnsize", "normal")
        variant = normalize_button_variant(variant_raw)
        appearance_raw = props.get("appearance")
        appearance = (
            str(appearance_raw)
            if appearance_raw is not None
            else normalize_button_appearance(mode_raw)
        )
        size = normalize_button_size(size_raw)
        shape = props.get("shape", "default")
        active_prop = props.get("active", "false")
        # Default to non-focusable to avoid stealing focus from form fields on click.
        # Components that need keyboard focus can opt in via `focusable=true`.
        focusable_prop = props.get("focusable", False)
        is_main_sidebar_nav = (comp_id or "").startswith("top_nav") or (comp_id or "").startswith("bottom_nav")

        widget = QPushButton(_escape_qt_mnemonic(label))

        widget.setObjectName(comp_id)
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        widget.setFlat(False)
        # Keep natural button width inside stretching parent layouts (e.g. Column align=top/fill).
        # Full-width can still be explicitly requested by style overrides.
        widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        focusable = str(focusable_prop).strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }
        widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus if focusable else Qt.FocusPolicy.NoFocus)

        # Set properties for CSS targeting
        widget.setProperty("variant", variant)
        widget.setProperty("mode", mode_raw)
        widget.setProperty("appearance", appearance)
        widget.setProperty("btnsize", size)
        widget.setProperty("shape", shape)
        widget.setProperty("_icon_name", icon_name)
        widget.setProperty("_variant", variant)
        widget.setProperty("_appearance", appearance)
        widget.setProperty("_size", size)
        widget.setProperty("_shape", shape)
        widget.setProperty("_main_sidebar_nav", bool(is_main_sidebar_nav))

        # widget.installEventFilter(HoverPropertyFilter(widget))
        # Refresh style to apply property-based rules
        widget.style().unpolish(widget)
        widget.style().polish(widget)

        def build_icon(icon_name, appearance, shape, variant, size, active):
            try:
                icon_label = get_icon_gliph(
                    icon_name
                )  # deve restituire una QLabel (glifo TTF) o simile
            except Exception:
                raise

            i_n, i_h = button_icon_colors(
                variant=variant,
                appearance=appearance,
                shape=shape,
                active=str(active).lower() in ("1", "true", "yes"),
                app_instance=app_instance,
            )
            if is_main_sidebar_nav and shape == "round" and appearance == "ghost":
                current_active = str(active).lower() in ("1", "true", "yes")
                i_n = (
                    theme_token("icon.sidebar.active", app_instance=app_instance)
                    if current_active
                    else theme_token("icon.sidebar.idle", app_instance=app_instance)
                )
                i_h = i_n

            def getIconSize(v):
                if v == "sm":
                    return 12, 12
                elif v == "lg":
                    return 22, 22
                else:
                    return 18, 18

            w, h = getIconSize(size)

            size = QSize(w, h)
            icon_normal = get_icon(icon_name, color=i_n)
            icon_hover = get_icon(icon_name, color=i_h)
            widget.setIconSize(size)

            return icon_normal, icon_hover

        if isinstance(active_prop, dict):
            active = "false"

            _mode = active_prop.get("operator", "AND")

            def path_to_key(p: str) -> str:
                return p if p.startswith("/") else f"/{p.lstrip('/')}"

            observe_keys = []
            for condition in active_prop.get("conditions", []):
                left = condition.get("left", {})
                right = condition.get("right", {})

                if isinstance(left, dict) and left.get("path", None):
                    observe_keys.append(path_to_key(left.get("path")))

                if isinstance(right, dict) and right.get("path", None):
                    observe_keys.append(path_to_key(right.get("path")))

            def evalConditions():
                _active = (
                    "false" if _mode == "OR" else "true"
                )  # if mode == "AND": "true" else: "false"
                for condition in active_prop.get("conditions", []):
                    left = condition.get("left", "")
                    right = condition.get("right", "")

                    if isinstance(left, dict) and left.get("path", None):
                        left = app_instance.store.get(path_to_key(left.get("path")), None, "auto")

                    if isinstance(right, dict) and right.get("path", None):
                        right = app_instance.store.get(path_to_key(right.get("path")), None, "auto")

                    comparator = condition.get("op")

                    try:
                        if comparator == "==":
                            res = left == right
                        if comparator == "!=":
                            res = left != right
                        if comparator == ">":
                            res = float(left) > float(right)
                        if comparator == "<":
                            res = float(left) < float(right)
                        if comparator == ">=":
                            res = float(left) >= float(right)
                        if comparator == "<=":
                            res = float(left) <= float(right)
                        if comparator == "in":
                            res = left in right
                        if comparator == "contains":
                            res = right in left
                    except Exception:
                        res = False

                    if _mode == "AND" and not res:
                        _active = False

                    if _mode == "OR" and res:
                        _active = True

                widget.setProperty("active", str(_active).lower())
                if icon_name:
                    icon_normal, icon_hover = build_icon(
                        icon_name, appearance, shape, variant, size, _active
                    )

                    def ensure_icon_swapper():
                        swap = getattr(widget, "_icon_swap", None)
                        if swap is None:
                            swap = IconSwapOnHover(widget, QIcon(), QIcon())
                            setattr(widget, "_icon_swap", swap)
                        return swap

                    ensure_icon_swapper().set_icons(icon_normal, icon_hover)
                widget.style().unpolish(widget)
                widget.style().polish(widget)
                return _active

            app_instance.binder.bind_many(observe_keys, evalConditions, owner=widget)
            active = evalConditions()
        else:
            active = str(active_prop).lower()
            if active in ("1", "yes", "true"):
                active = "true"
                widget.setProperty("active", active)
            elif active in ("0", "no", "false"):
                active = "false"

            widget.setProperty("active", active)

        if icon_name:
            icon_normal, icon_hover = build_icon(
                icon_name, appearance, shape, variant, size, active
            )
            IconSwapOnHover(widget, icon_normal, icon_hover)

        style = props.get("style", None)
        if style:
            widget.setStyleSheet(qss_for_widget_style(style, comp_id))

        if "action" in props:
            action = props["action"]
            params = props.get("params", {})
            if isinstance(action, str):
                action_name = action.strip()
                action_spec = action
            else:
                action_name = str(action.get("name", "")).strip()
                action_spec = action
            widget.setProperty("_action_name", action_name)
            widget.setProperty("_action_spec_raw", action_spec)
            widget.setProperty("_action_params_raw", params if isinstance(params, dict) else {})
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

            def current_extra_context():
                raw_params = widget.property("_action_params_raw")
                resolved = {}
                if isinstance(raw_params, dict):
                    resolved.update(
                        self._resolve_action_context(
                            app_instance,
                            raw_params,
                            surface_id,
                        )
                    )
                return resolved

            widget.clicked.connect(
                lambda: emit_action_spec(
                    app_instance,
                    widget.property("_action_spec_raw"),
                    {
                        **current_extra_context(),
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

    def update_widget_property(self, widget, prop, value):
        if prop == "label":
            if isinstance(value, dict) and "literalString" in value:
                widget.setText(_escape_qt_mnemonic(value.get("literalString") or ""))
            else:
                widget.setText(_escape_qt_mnemonic(value))
            return
        if prop == "params":
            widget.setProperty("_action_params_raw", value if isinstance(value, dict) else {})
            return
        if prop == "action":
            if isinstance(value, str):
                action_name = value.strip()
                action_ctx = {}
                action_spec = action_name
            else:
                action = value if isinstance(value, dict) else {}
                action_name = str(action.get("name", "")).strip()
                action_ctx = action.get("context", {})
            if not isinstance(action_ctx, dict):
                action_ctx = {}
            if not isinstance(value, str):
                action_spec = dict(action)
                action_spec["context"] = action_ctx
            widget.setProperty("_action_name", action_name)
            widget.setProperty("_action_spec_raw", action_spec)
            widget.setProperty("_action_context_raw", action_ctx)
            widget.setProperty(
                "_track_loading_names",
                _normalize_track_loading(widget.property("track_loading"), action_name),
            )
            action_locks = getattr(QApplication.instance(), "_action_locks", None)
            track_loading_names = widget.property("_track_loading_names") or []
            if action_locks is not None and isinstance(track_loading_names, list):
                action_locks.sync_widget(widget)
            return
        if prop == "track_loading":
            action_name = str(widget.property("_action_name") or "").strip()
            track_loading_names = _normalize_track_loading(value, action_name)
            widget.setProperty("track_loading", value)
            widget.setProperty("_track_loading_names", track_loading_names)
            action_locks = getattr(QApplication.instance(), "_action_locks", None)
            if action_locks is not None:
                action_locks.sync_widget(widget)
            return
        super().update_widget_property(widget, prop, value)

        if prop == "active":
            # Regenerate icons based on new active state
            icon_name = widget.property("_icon_name")
            if not icon_name:
                return

            variant = widget.property("_variant")
            appearance = widget.property("_appearance")
            size_val = widget.property("_size")
            shape = widget.property("_shape")

            i_n, i_h = button_icon_colors(
                variant=str(variant),
                appearance=str(appearance),
                shape=str(shape),
                active=str(value).lower() in ("1", "true", "yes"),
                app_instance=widget.window(),
            )
            if (
                bool(widget.property("_main_sidebar_nav"))
                and str(shape) == "round"
                and str(appearance) == "ghost"
            ):
                current_active = str(value).lower() in ("1", "true", "yes")
                i_n = (
                    theme_token("icon.sidebar.active")
                    if current_active
                    else theme_token("icon.sidebar.idle")
                )
                i_h = i_n

            def getIconSize(v):
                if v == "sm":
                    return 12, 12
                elif v == "lg":
                    return 22, 22
                else:
                    return 18, 18

            w, h = getIconSize(size_val)
            size = QSize(w, h)
            icon_normal = get_icon(icon_name, color=i_n)
            icon_hover = get_icon(icon_name, color=i_h)

            widget.setIconSize(size)
            widget.setIcon(icon_normal)

            # Update hover filter if present (it's hard to access the filter instance directly without keeping ref)
            # But IconSwapOnHover stores itself on the button? No.
            # However, we can just re-install it or rely on setIcon updating current state.
            # A cleaner approach would be finding the child IconSwapOnHover.
            # But for now, updating the widget icon covers the static state.
            # Hover state update is tricky without ref.
            # Let's try to update the hover filter if we can find it.

            # Assuming we can't easily find it, let's just re-create it? No that adds multiple event filters.
            # Best effort: update widget icon.
            # For hover, we might need to store the filter on the widget.

            filter_obj = widget.findChild(
                IconSwapOnHover
            )  # It's a QObject with button as parent
            if not filter_obj:
                # Check children manually?
                children = widget.children()
                for child in children:
                    if isinstance(child, IconSwapOnHover):
                        filter_obj = child
                        break

            if filter_obj:
                filter_obj.icon_normal = icon_normal
                filter_obj.icon_hover = icon_hover
            else:
                # Create if missing (unlikely if render called it)
                IconSwapOnHover(widget, icon_normal, icon_hover)
