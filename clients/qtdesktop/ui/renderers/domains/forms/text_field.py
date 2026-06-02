from PySide6.QtWidgets import (
    QLabel,
    QCheckBox,
    QWidget,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QVBoxLayout,
    QFileDialog,
    QHBoxLayout,
    QPushButton,
)
from PySide6.QtCore import QLocale, Qt
from PySide6.QtGui import QDoubleValidator, QIntValidator
from typing import Dict, Any
from ...base import BaseRenderer, emit_action_spec, publish_bound_value
import os

class TextFieldRenderer(BaseRenderer):
    component_type = "TextField"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "value": self.PROPERTY,
            "placeholder": self.PROPERTY,
            "password": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        value = props.get("value", "")
        placeholder = props.get("placeholder", "")
        # Resolve initial display text
        if isinstance(value, dict) and value.get("type") == "store":
            path = value.get("path")
            display_text = str(app_instance.store.get(path, ""))
        else:
            display_text = self._literal_text(value, "") if isinstance(value, dict) else str(value or "")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        label_text = self._literal_text(props.get("label"))
        if label_text:
            label = QLabel(label_text)
            label.setProperty("ui_role", "form_label")
            layout.addWidget(label)

        edit = QLineEdit(display_text)
        edit.setObjectName(comp_id)
        edit.setPlaceholderText(placeholder)
        input_type = str(props.get("input_type") or props.get("type") or "").lower()
        if input_type in {"integer", "int"}:
            validator = QIntValidator(edit)
            if props.get("min") not in (None, ""):
                validator.setBottom(int(props["min"]))
            if props.get("max") not in (None, ""):
                validator.setTop(int(props["max"]))
            edit.setValidator(validator)
        elif input_type in {"number", "float", "decimal"}:
            validator = QDoubleValidator(edit)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            validator.setLocale(QLocale.c())
            if props.get("min") not in (None, ""):
                validator.setBottom(float(props["min"]))
            if props.get("max") not in (None, ""):
                validator.setTop(float(props["max"]))
            if props.get("decimals") not in (None, ""):
                validator.setDecimals(int(props["decimals"]))
            edit.setValidator(validator)
        if props.get("password"):
            edit.setEchoMode(QLineEdit.EchoMode.Password)
        edit.setProperty("is_input", True)
        edit.setProperty("ui_role", "form_input")
        layout.addWidget(edit)

        # Error label
        err_label = QLabel()
        err_label.setProperty("ui_role", "form_error_label")
        err_label.setWordWrap(True)
        err_label.hide()
        layout.addWidget(err_label)

        self.configure_widget(edit, props, props, app_instance, comp_id)

        edit.textChanged.connect(
            lambda text: publish_bound_value(app_instance, edit, comp_id, text)
        )

        if "action" in props:
            action = props["action"]
            edit.returnPressed.connect(
                lambda: emit_action_spec(
                    app_instance,
                    action,
                    {
                        comp_id: edit.text(),
                        "value": edit.text(),
                    },
                    surface_id,
                    comp_id,
                )
            )

        if "onChangeAction" in props:
            action = props["onChangeAction"]
            change_mode = str(props.get("onChangeMode", "local")).strip().lower()
            if change_mode in {
                "live",
                "autocomplete",
                "search",
                "search_suggest",
                "remote_validate",
                "remote_preview",
            }:
                edit.textChanged.connect(
                    lambda text: emit_action_spec(
                        app_instance,
                        action,
                        {comp_id: text, "value": text},
                        surface_id,
                        comp_id,
                    )
                )

        # Initial error state
        if props.get("error"):
            self.update_widget_property(container, "error", props["error"])

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        edit = widget.findChild(QLineEdit)
        if not edit:
             # Backward compatibility or direct widget usage
             if isinstance(widget, QLineEdit):
                 edit = widget
             else:
                 return super().update_widget_property(widget, prop, value)

        if prop == "value":
            text = "" if value is None else str(value)
            if edit.text() != text:
                edit.setText(text)
            return
        if prop == "placeholder":
            edit.setPlaceholderText("" if value is None else str(value))
            return
        if prop == "password":
            edit.setEchoMode(
                QLineEdit.EchoMode.Password if bool(value) else QLineEdit.EchoMode.Normal
            )
            return
        if prop == "error":
            err_label = widget.findChild(QLabel, options=Qt.FindChildOption.FindDirectChildrenOnly)
            # Actually, label and err_label are both QLabels. Let's find by role or index.
            # I'll search for the one with ui_role="form_error_label"
            field_label = None
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "form_label":
                    field_label = child
                    break
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "form_error_label":
                    if value:
                        child.setText(self._literal_text(value))
                        child.show()
                        edit.setProperty("error", True)
                        edit.setProperty("invalid", "true")
                        if field_label is not None:
                            field_label.setProperty("invalid", "true")
                            field_label.style().unpolish(field_label)
                            field_label.style().polish(field_label)
                    else:
                        child.hide()
                        edit.setProperty("error", False)
                        edit.setProperty("invalid", "false")
                        if field_label is not None:
                            field_label.setProperty("invalid", "false")
                            field_label.style().unpolish(field_label)
                            field_label.style().polish(field_label)
                    edit.style().unpolish(edit)
                    edit.style().polish(edit)
                    return
            return
        super().update_widget_property(widget, prop, value)
