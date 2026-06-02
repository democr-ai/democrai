from PySide6.QtWidgets import QLabel, QMessageBox, QWidget
from PySide6.QtCore import QObject, QTimer
from typing import Dict, Any, Optional

from ..animation import fade_in, pulse_opacity, slide, stop_animations
from .base_animation import (
    direct_child_widgets,
    normalize_animation_spec,
    normalize_stagger_spec,
    run_declared_animation,
)
from .base_visibility import (
    evaluate_condition,
    evaluate_visibility_rule,
    get_component_props,
    permissions_allow,
    resolve_condition_value,
)
from ..qss_sanitizer import qss_for_widget_style


def emit_action(
    app_instance: Any,
    action_name: str,
    context: Optional[dict],
    surface_id: str,
    comp_id: str,
) -> None:
    """Single point for emitting UI actions from renderers."""
    if not action_name:
        return
    resolved_context = _resolve_action_context(app_instance, context or {}, surface_id)
    app_instance.action_triggered.emit(
        action_name, resolved_context, surface_id, comp_id
    )


def emit_action_spec(
    app_instance: Any,
    action: Any,
    extra_context: Optional[dict],
    surface_id: str,
    comp_id: str,
) -> None:
    """Emit an ActionSpec, applying client-side confirmation when declared."""
    if isinstance(action, str):
        action_name = action.strip()
        action_context: dict[str, Any] = {}
        confirm = None
    elif isinstance(action, dict):
        action_name = str(action.get("name", "")).strip()
        raw_context = action.get("context", {})
        action_context = raw_context if isinstance(raw_context, dict) else {}
        confirm = action.get("confirm")
    else:
        return

    if not action_name:
        return
    if isinstance(confirm, dict) and not _confirm_action(app_instance, confirm):
        return

    merged_context = dict(action_context)
    if isinstance(extra_context, dict):
        merged_context.update(extra_context)
    emit_action(app_instance, action_name, merged_context, surface_id, comp_id)


def _confirm_action(app_instance: Any, confirm: dict[str, Any]) -> bool:
    text = _action_text(confirm.get("text"), "Are you sure?")
    confirm_text = _action_text(confirm.get("confirm_text"), "Confirm")
    cancel_text = _action_text(confirm.get("cancel_text"), "Cancel")
    parent = app_instance if isinstance(app_instance, QWidget) else None
    dialog = QMessageBox(parent)
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setWindowTitle(confirm_text)
    dialog.setText(text)
    yes_button = dialog.addButton(confirm_text, QMessageBox.ButtonRole.AcceptRole)
    dialog.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)
    dialog.exec()
    return dialog.clickedButton() is yes_button


def confirm_action(app_instance: Any, confirm: Any) -> bool:
    """Return whether an ActionSpec confirmation is accepted."""
    if not isinstance(confirm, dict):
        return True
    return _confirm_action(app_instance, confirm)


def _action_text(value: Any, fallback: str) -> str:
    if isinstance(value, dict) and isinstance(value.get("literalString"), str):
        return value.get("literalString") or fallback
    text = str(value or "").strip()
    return text or fallback


def _resolve_action_context(
    app_instance: Any,
    context: Any,
    surface_id: str | None = None,
) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}

    bindings = getattr(app_instance, "bindings", None)
    if bindings is None:
        return context

    def _resolve(value: Any, *, allow_implicit_path: bool = True) -> Any:
        if isinstance(value, dict):
            value_type = value.get("type")
            if value_type in {"store", "action", "literal"} or (
                allow_implicit_path and "path" in value and "type" not in value
            ):
                try:
                    if hasattr(bindings, "resolve_value_for_surface"):
                        return bindings.resolve_value_for_surface(
                            value,
                            surface_id,
                            allow_implicit_path=allow_implicit_path,
                        )
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

    resolved = _resolve(context, allow_implicit_path=False)
    return resolved if isinstance(resolved, dict) else context


def _normalize_store_path(path: str) -> str:
    text = str(path or "").strip()
    if not text:
        return "/"
    return text if text.startswith("/") else f"/{text.lstrip('/')}"


def extract_store_path(spec: Any) -> str | None:
    if not isinstance(spec, dict):
        return None
    if spec.get("type") == "store" and spec.get("path"):
        return _normalize_store_path(str(spec.get("path")))
    if "path" in spec and len(spec.keys()) <= 3 and spec.get("path"):
        return _normalize_store_path(str(spec.get("path")))
    return None


def publish_bound_value(
    app_instance: Any,
    widget: QWidget | None,
    fallback_key: str,
    value: Any,
    *,
    prop_name: str = "value",
    scope: str = "page",
) -> None:
    target = None
    current = widget
    marker = f"_binding_target_{prop_name}"
    while current is not None:
        candidate = current.property(marker)
        if isinstance(candidate, str) and candidate.strip():
            target = candidate
            break
        current = current.parentWidget()

    app_instance.store.set(target or fallback_key, value, scope)


class BaseRenderer:
    """
    Base class for all Desktop Renderers.

    Standardize widget creation (`render` method).
    """

    # The component type this renderer handles (e.g. "Button")
    component_type: str = ""
    PROPERTY = "property"
    COMPONENT = "component"
    SURFACE = "surface"

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ) -> Optional[QWidget]:
        """
        Renders the widget.
        app_instance: Reference to the main app/renderer to emit signals.
        """
        raise NotImplementedError

    def is_component_visible(
        self,
        component_data: Dict[str, Any],
        app_instance: Any,
        item: Optional[dict] = None,
        *,
        surface_id: str | None = None,
    ) -> bool:
        props = self._get_component_props(component_data)
        if not self._permissions_allow(component_data, app_instance):
            return False
        if not self._evaluate_visibility_rule(
            props.get("show_if", component_data.get("show_if")),
            app_instance,
            item,
            surface_id=surface_id,
            default=True,
        ):
            return False
        if self._evaluate_visibility_rule(
            props.get("hide_if", component_data.get("hide_if")),
            app_instance,
            item,
            surface_id=surface_id,
            default=False,
        ):
            return False
        return True

    def _permissions_allow(self, component_data: Dict[str, Any], app_instance: Any) -> bool:
        return permissions_allow(component_data, app_instance)

    def _get_component_props(self, component_data: Dict[str, Any]) -> Dict[str, Any]:
        return get_component_props(component_data)

    def _evaluate_visibility_rule(
        self,
        rule: Any,
        app_instance: Any,
        item: Optional[dict],
        *,
        surface_id: str | None = None,
        default: bool,
    ) -> bool:
        return evaluate_visibility_rule(
            rule,
            app_instance,
            item,
            surface_id,
            default=default,
        )

    def _evaluate_condition(
        self,
        condition: Dict[str, Any],
        app_instance: Any,
        item: Optional[dict],
        *,
        surface_id: str | None = None,
    ) -> bool:
        return evaluate_condition(condition, app_instance, item, surface_id)

    def _resolve_condition_value(
        self,
        value: Any,
        app_instance: Any,
        item: Optional[dict],
        *,
        surface_id: str | None = None,
    ) -> Any:
        return resolve_condition_value(value, app_instance, item, surface_id)

    def before_children_render(
        self,
        widget: QWidget,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str,
    ):
        """Hook called before rendering children."""
        pass

    def after_children_render(
        self,
        widget: QWidget,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str,
    ):
        """Hook called after rendering children."""
        pass

    def binding_strategies(self) -> Dict[str, str]:
        """Declare which props support incremental binding updates."""
        return {
            "style": self.PROPERTY,
            "visible": self.PROPERTY,
            "enabled": self.PROPERTY,
            "disabled": self.PROPERTY,
            "tooltip": self.PROPERTY,
            "animation": self.PROPERTY,
            "animation_stagger": self.PROPERTY,
        }

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        """Apply a property change without rebuilding the whole surface."""
        if prop == "style":
            self._apply_inline_style(widget, value)
            return
        if prop == "visible":
            widget.setVisible(bool(value))
            return
        if prop == "enabled":
            widget.setEnabled(bool(value))
            return
        if prop == "disabled":
            widget.setDisabled(bool(value))
            return
        if prop == "tooltip":
            widget.setToolTip("" if value is None else str(value))
            return
        if prop == "animation":
            self.apply_declared_animation(widget, value)
            return
        if prop == "animation_stagger":
            self.apply_post_children_effects(widget, {"animation_stagger": value})
            return

        widget.setProperty(prop, value)
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def apply_collection_patch(
        self,
        widget: QWidget,
        prop: str,
        action: str,
        value: Any,
    ) -> bool:
        """Apply collection-oriented patches like append/remove/replace."""
        return False

    def _literal_text(self, value: Any, fallback: str = "") -> str:
        if isinstance(value, dict) and "literalString" in value:
            return str(value.get("literalString") or "")
        if value is None:
            return fallback
        return str(value)

    def _find_first_label(self, widget: QWidget) -> QLabel | None:
        labels = widget.findChildren(QLabel)
        return labels[0] if labels else None

    def configure_widget(
        self,
        widget: QWidget,
        raw_props: Dict[str, Any],
        resolved_props: Dict[str, Any],
        app_instance: Any,
        comp_id: str,
    ) -> None:
        widget.setProperty("_comp_type", self.component_type or "")
        for prop_name, prop_value in raw_props.items():
            path = extract_store_path(prop_value)
            if not path:
                continue
            widget.setProperty(f"_binding_target_{prop_name}", path)
        widget.setProperty("_dmc_declared_animation", resolved_props.get("animation"))
        self.apply_declared_animation(widget, resolved_props.get("animation"))
        if "style" in resolved_props:
            self._apply_inline_style(widget, resolved_props.get("style"))

    def _apply_inline_style(self, widget: QWidget, value: Any) -> None:
        if value is None:
            widget.setStyleSheet("")
            return
        widget.setStyleSheet(qss_for_widget_style(value, str(widget.objectName() or "")))

    def apply_declared_animation(
        self,
        widget: QWidget,
        spec: Any,
        *,
        extra_delay: int = 0,
        force: bool = False,
    ) -> None:
        run_declared_animation(
            widget,
            spec,
            extra_delay=extra_delay,
            force=force,
            qtimer_cls=QTimer,
            stop_animations_fn=stop_animations,
            fade_in_fn=fade_in,
            pulse_opacity_fn=pulse_opacity,
            slide_fn=slide,
        )

    def _normalize_animation_spec(self, spec: Any) -> Dict[str, Any] | None:
        return normalize_animation_spec(spec)

    def apply_post_children_effects(
        self,
        widget: QWidget,
        props: Dict[str, Any],
        surface_id: str | None = None,
        comp_id: str | None = None,
    ) -> None:
        stagger_spec = normalize_stagger_spec(props.get("animation_stagger"))
        if not stagger_spec:
            return

        fallback_animation = stagger_spec["animation"]
        base_delay = int(stagger_spec.get("delay", 0) or 0)
        step = int(stagger_spec.get("step", 70) or 70)
        for index, child in enumerate(self._direct_child_widgets(widget)):
            child_animation = child.property("_dmc_declared_animation")
            self.apply_declared_animation(
                child,
                child_animation or fallback_animation,
                extra_delay=base_delay + (index * step),
                force=child_animation is None,
            )

    def _normalize_stagger_spec(self, spec: Any) -> Dict[str, Any] | None:
        return normalize_stagger_spec(spec)

    def _direct_child_widgets(self, widget: QWidget) -> list[QWidget]:
        return direct_child_widgets(widget)

    def _widgets_from_layout(self, layout) -> list[QWidget]:
        # Compatibility shim retained for legacy call sites.
        from .base_animation import widgets_from_layout

        return widgets_from_layout(layout)
