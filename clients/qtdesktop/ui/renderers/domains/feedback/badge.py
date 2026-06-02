from __future__ import annotations
from typing import Any, Dict
from PySide6.QtWidgets import (
    QLabel,
    QSizePolicy,
    QWidget,
)
from ...base import BaseRenderer
from .common import _literal


class BadgeRenderer(BaseRenderer):
    component_type = "Badge"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "text": self.PROPERTY,
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
        text = str(
            self._resolve_initial(
                props.get("text"),
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
                default="default",
            )
            or "default"
        )
        label = QLabel(text)
        label.setObjectName(comp_id)
        label.setProperty("ui_role", "advanced_badge")
        label.setProperty("variant", variant)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "text":
            widget.setText(_literal(value))
            return
        if prop == "variant":
            widget.setProperty("variant", str(value or "default"))
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            return
        super().update_widget_property(widget, prop, value)
