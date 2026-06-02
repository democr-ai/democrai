from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QFrame,
    QLabel,
    QMenu,
    QProgressBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QHBoxLayout,
)
from ...base import BaseRenderer, emit_action, publish_bound_value
from .common import _field_shell, _literal, _parse_qdate

class ProgressRenderer(BaseRenderer):
    component_type = "Progress"

    @staticmethod
    def _resolve_bound_value(
        app_instance: Any,
        value: Any,
        surface_id: str,
        fallback: Any,
    ) -> Any:
        if not isinstance(value, dict):
            return fallback if value is None else value
        bindings = getattr(app_instance, "bindings", None)
        if bindings is None:
            return value.get("default", fallback)
        try:
            if hasattr(bindings, "resolve_value_for_surface"):
                resolved = bindings.resolve_value_for_surface(value, surface_id)
            elif hasattr(bindings, "resolve_value"):
                resolved = bindings.resolve_value(value)
            else:
                resolved = value.get("default", fallback)
        except Exception:
            resolved = value.get("default", fallback)
        return fallback if resolved is None else resolved

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "value": self.PROPERTY,
            "maximum": self.PROPERTY,
            "show_label": self.SURFACE,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        frame = QFrame()
        frame.setObjectName(comp_id)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label_text = _literal(props.get("label"))
        show_label = self._resolve_bound_value(
            app_instance,
            props.get("show_label", True),
            surface_id,
            True,
        )
        if show_label:
            label = QLabel(label_text or "Progress")
            label.setObjectName(f"{comp_id}__label")
            label.setProperty("ui_role", "advanced_progress_label")
            layout.addWidget(label)
        bar = QProgressBar()
        bar.setObjectName(f"{comp_id}__bar")
        maximum = self._resolve_bound_value(
            app_instance,
            props.get("maximum", 100),
            surface_id,
            100,
        )
        value = self._resolve_bound_value(
            app_instance,
            props.get("value", 0),
            surface_id,
            0,
        )
        try:
            safe_maximum = max(1, int(maximum))
        except (TypeError, ValueError):
            safe_maximum = 100
        try:
            safe_value = int(value)
        except (TypeError, ValueError):
            safe_value = 0
        bar.setRange(0, safe_maximum)
        bar.setValue(max(0, min(safe_value, safe_maximum)))
        bar.setTextVisible(True)
        bar.setProperty("ui_role", "advanced_progress_bar")
        layout.addWidget(bar)
        return frame

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "label":
            label = widget.findChild(QLabel, f"{widget.objectName()}__label")
            if label is not None:
                label.setText(_literal(value) or "Progress")
            return
        bar = widget.findChild(QProgressBar, f"{widget.objectName()}__bar")
        if bar is None:
            super().update_widget_property(widget, prop, value)
            return
        if prop == "value":
            try:
                target = int(value)
            except (TypeError, ValueError):
                target = 0
            anim = QPropertyAnimation(bar, b"value")
            anim.setDuration(500)
            anim.setStartValue(bar.value())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            bar._progress_anim = anim
            anim.start()
            return
        if prop == "maximum":
            try:
                bar.setRange(0, int(value))
            except (TypeError, ValueError):
                bar.setRange(0, 100)
            return
        super().update_widget_property(widget, prop, value)
