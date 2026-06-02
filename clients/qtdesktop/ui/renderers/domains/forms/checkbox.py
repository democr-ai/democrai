from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from .common import _literal

class CheckboxRenderer(BaseRenderer):
    component_type = "Checkbox"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "checked": self.PROPERTY,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        container = QWidget()
        container.setObjectName(comp_id)
        container.setProperty("is_input", True)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        widget = QCheckBox(_literal(props.get("label")))
        widget.setObjectName(f"{comp_id}__input")
        widget.setProperty("is_input", True)
        widget.setChecked(bool(props.get("checked", False)))
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        widget.setProperty("ui_role", "advanced_checkbox")
        widget.setProperty("error", False)
        widget.setProperty("invalid", "false")
        layout.addWidget(widget)

        # Error label
        err_label = QLabel()
        err_label.setProperty("ui_role", "form_error_label")
        err_label.setWordWrap(True)
        err_label.hide()
        layout.addWidget(err_label)

        action = props.get("action")
        container.setProperty("checked", widget.isChecked())
        container.setProperty("value", widget.isChecked())
        container.setProperty("_confirmed_checked", widget.isChecked())
        publish_bound_value(app_instance, widget, comp_id, widget.isChecked(), prop_name="checked")

        def _apply_checked(checked: bool) -> None:
            container.setProperty("checked", checked)
            container.setProperty("value", checked)
            container.setProperty("_confirmed_checked", checked)
            publish_bound_value(
                app_instance,
                widget,
                comp_id,
                checked,
                prop_name="checked",
            )

        def _on_clicked(next_checked: bool) -> None:
            previous = bool(container.property("_confirmed_checked"))
            confirm = action.get("confirm") if isinstance(action, dict) else None
            if action and not confirm_action(app_instance, confirm):
                widget.blockSignals(True)
                widget.setChecked(previous)
                widget.blockSignals(False)
                container.setProperty("checked", previous)
                container.setProperty("value", previous)
                return

            _apply_checked(next_checked)
            if action:
                action_spec = action
                if isinstance(action, dict):
                    action_spec = dict(action)
                    action_spec.pop("confirm", None)
                emit_action_spec(
                    app_instance,
                    action_spec,
                    {
                        "checked": next_checked,
                        comp_id: next_checked,
                        "value": next_checked,
                    },
                    surface_id,
                    comp_id,
                )

        widget.clicked.connect(_on_clicked)

        # Initial error state
        if props.get("error"):
            self.update_widget_property(container, "error", props["error"])

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        checkbox = widget.findChild(QCheckBox, f"{widget.objectName()}__input")
        host = widget
        if not checkbox:
            if isinstance(widget, QCheckBox):
                checkbox = widget
                host = widget.parentWidget() or widget
            else:
                return super().update_widget_property(widget, prop, value)

        if prop == "label":
            checkbox.setText(_literal(value))
            return
        if prop == "checked":
            checked = bool(value)
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
            host.setProperty("checked", checked)
            host.setProperty("value", checked)
            host.setProperty("_confirmed_checked", checked)
            return
        if prop == "error":
            has_error = bool(value)
            checkbox.setProperty("error", has_error)
            checkbox.setProperty("invalid", "true" if has_error else "false")
            for child in host.findChildren(QLabel):
                if child.property("ui_role") == "form_error_label":
                    if has_error:
                        child.setText(self._literal_text(value))
                        child.show()
                    else:
                        child.hide()
                    checkbox.style().unpolish(checkbox)
                    checkbox.style().polish(checkbox)
                    return
            checkbox.style().unpolish(checkbox)
            checkbox.style().polish(checkbox)
            return
        super().update_widget_property(widget, prop, value)
