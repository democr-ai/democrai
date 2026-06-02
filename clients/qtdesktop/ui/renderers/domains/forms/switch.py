from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
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
from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from .common import _field_shell, _literal, _parse_qdate

class SwitchRenderer(BaseRenderer):
    component_type = "Switch"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "checked": self.PROPERTY,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        shell = QFrame()
        shell.setObjectName(comp_id)
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        copy = QLabel(_literal(props.get("label")))
        copy.setObjectName(f"{comp_id}__label")
        copy.setProperty("ui_role", "advanced_switch_label")

        widget = QCheckBox()
        widget.setObjectName(f"{comp_id}__input")
        widget.setChecked(bool(props.get("checked", False)))
        widget.setCursor(Qt.CursorShape.PointingHandCursor)
        widget.setProperty("ui_role", "advanced_switch_input")

        layout.addWidget(copy)
        layout.addStretch()
        layout.addWidget(widget)

        action = props.get("action")
        shell.setProperty("checked", widget.isChecked())
        shell.setProperty("value", widget.isChecked())
        shell.setProperty("_confirmed_checked", widget.isChecked())
        publish_bound_value(app_instance, shell, comp_id, widget.isChecked(), prop_name="checked")

        def _apply_checked(checked: bool) -> None:
            shell.setProperty("checked", checked)
            shell.setProperty("value", checked)
            shell.setProperty("_confirmed_checked", checked)
            publish_bound_value(
                app_instance,
                widget,
                comp_id,
                checked,
                prop_name="checked",
            )

        def _on_clicked(next_checked: bool) -> None:
            previous = bool(shell.property("_confirmed_checked"))
            confirm = action.get("confirm") if isinstance(action, dict) else None
            if action and not confirm_action(app_instance, confirm):
                widget.blockSignals(True)
                widget.setChecked(previous)
                widget.blockSignals(False)
                shell.setProperty("checked", previous)
                shell.setProperty("value", previous)
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
            self.update_widget_property(shell, "error", props["error"])

        return shell

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "error":
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "form_error_label":
                    if value:
                        child.setText(self._literal_text(value))
                        child.show()
                    else:
                        child.hide()
                    return
            # If not found, add it
            err_label = QLabel(self._literal_text(value))
            err_label.setProperty("ui_role", "form_error_label")
            err_label.setWordWrap(True)
            widget.layout().addWidget(err_label)
            if not value: err_label.hide()
            return
        if prop == "label":
            label = widget.findChild(QLabel, f"{widget.objectName()}__label")
            if label is not None:
                label.setText(_literal(value))
            return
        if prop == "checked":
            checkbox = widget.findChild(QCheckBox, f"{widget.objectName()}__input")
            if checkbox is not None:
                checked = bool(value)
                checkbox.blockSignals(True)
                checkbox.setChecked(checked)
                checkbox.blockSignals(False)
                widget.setProperty("checked", checked)
                widget.setProperty("value", checked)
                widget.setProperty("_confirmed_checked", checked)
            return
        super().update_widget_property(widget, prop, value)
