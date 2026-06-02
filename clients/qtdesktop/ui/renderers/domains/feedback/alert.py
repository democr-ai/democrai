from __future__ import annotations
from typing import Any, Dict
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ...base import BaseRenderer
from .common import _literal


class AlertRenderer(BaseRenderer):
    component_type = "Alert"

    @staticmethod
    def _repolish(widget: QWidget | None) -> None:
        if widget is None:
            return
        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget.update()

    def _apply_variant(self, widget: QWidget, variant: str) -> None:
        widget.setProperty("variant", variant)
        title = widget.findChild(QLabel, f"{widget.objectName()}__title")
        body = widget.findChild(QLabel, f"{widget.objectName()}__body")
        for child in (title, body):
            if child is not None:
                child.setProperty("variant", variant)
        self._repolish(widget)
        self._repolish(title)
        self._repolish(body)

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "title": self.PROPERTY,
            "description": self.PROPERTY,
            "variant": self.PROPERTY,
        }

    def _resolve_initial(
        self,
        value: Any,
        *,
        surface_id: str,
        app_instance: Any,
        default: Any = "",
    ) -> Any:
        if not isinstance(value, dict):
            return value if value is not None else default
        if "literalString" in value:
            return value.get("literalString", default)
        bindings = getattr(app_instance, "bindings", None)
        if bindings is None:
            return value.get("default", default)
        resolved = bindings.resolve_value_for_surface(value, surface_id)
        if resolved is None:
            return value.get("default", default)
        return resolved

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        title_text = str(
            self._resolve_initial(
                props.get("title"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        )
        description_text = str(
            self._resolve_initial(
                props.get("description"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="",
            )
            or ""
        )
        variant = str(
            self._resolve_initial(
                props.get("variant"),
                surface_id=surface_id,
                app_instance=app_instance,
                default="info",
            )
            or "info"
        )

        frame = QFrame()
        frame.setObjectName(comp_id)
        frame.setProperty("ui_role", "advanced_alert")
        frame.setProperty("variant", variant)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        layout = QVBoxLayout(frame)
        layout.setSizeConstraint(QVBoxLayout.SetMinimumSize)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        title = QLabel(title_text)
        title.setObjectName(f"{comp_id}__title")
        title.setWordWrap(True)
        title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        title.setProperty("ui_role", "advanced_alert_title")
        title.setProperty("variant", variant)
        body = QLabel(description_text)
        body.setObjectName(f"{comp_id}__body")
        body.setWordWrap(True)
        body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        body.setProperty("ui_role", "advanced_alert_body")
        body.setProperty("variant", variant)

        layout.addWidget(title)
        if body.text():
            layout.addWidget(body)
        title.updateGeometry()
        body.updateGeometry()
        frame.updateGeometry()
        return frame

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        title = widget.findChild(QLabel, f"{widget.objectName()}__title")
        body = widget.findChild(QLabel, f"{widget.objectName()}__body")
        if prop == "title":
            if title is not None:
                title.setText(_literal(value))
                title.updateGeometry()
                widget.updateGeometry()
            return
        if prop == "description":
            if body is not None:
                body.setText(_literal(value))
                body.setVisible(bool(body.text()))
                body.updateGeometry()
                widget.updateGeometry()
            return
        if prop == "variant":
            self._apply_variant(widget, str(value or "info"))
            return
        super().update_widget_property(widget, prop, value)
