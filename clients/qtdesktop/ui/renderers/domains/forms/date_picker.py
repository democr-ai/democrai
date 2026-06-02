from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QWidget

from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from .common import _field_shell, _literal


def _token_to_strptime(fmt: str) -> str:
    return (
        str(fmt or "yyyy-MM-dd")
        .replace("yyyy", "%Y")
        .replace("MM", "%m")
        .replace("dd", "%d")
        .replace("HH", "%H")
        .replace("mm", "%M")
    )


def _format_to_input_mask(fmt: str) -> str:
    mask = str(fmt or "yyyy-MM-dd")
    return (
        mask.replace("yyyy", "0000")
        .replace("MM", "00")
        .replace("dd", "00")
        .replace("HH", "00")
        .replace("mm", "00")
    )


def _parse_value(raw: str, fmt: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, _token_to_strptime(fmt))
    except ValueError:
        return None


def _is_complete(raw: str, fmt: str) -> bool:
    expected = _format_to_input_mask(fmt).replace("0", "_")
    current = str(raw or "")
    return current and "_" not in current and len(current) == len(expected)


class DatePickerRenderer(BaseRenderer):
    component_type = "DatePicker"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "value": self.PROPERTY,
            "min_date": self.PROPERTY,
            "max_date": self.PROPERTY,
            "format": self.PROPERTY,
            "error": self.PROPERTY,
        }

    def _validate_and_paint(self, frame: QWidget, line_edit: QLineEdit, error_label: QLabel) -> None:
        fmt = str(line_edit.property("_format") or "yyyy-MM-dd")
        min_raw = str(line_edit.property("_min_date") or "").strip()
        max_raw = str(line_edit.property("_max_date") or "").strip()
        typed = line_edit.text().strip()

        if not typed:
            line_edit.setProperty("invalid", "false")
            if error_label.property("_server_error"):
                error_label.setText(str(error_label.property("_server_error")))
                error_label.show()
            else:
                error_label.hide()
            line_edit.style().unpolish(line_edit)
            line_edit.style().polish(line_edit)
            return

        if not _is_complete(typed, fmt):
            line_edit.setProperty("invalid", "false")
            if error_label.property("_server_error"):
                error_label.setText(str(error_label.property("_server_error")))
                error_label.show()
            else:
                error_label.hide()
            line_edit.style().unpolish(line_edit)
            line_edit.style().polish(line_edit)
            return

        parsed = _parse_value(typed, fmt)
        if parsed is None:
            line_edit.setProperty("invalid", "true")
            error_label.setText("Invalid date/time for selected format.")
            error_label.show()
            line_edit.style().unpolish(line_edit)
            line_edit.style().polish(line_edit)
            return

        min_dt = _parse_value(min_raw, fmt) if min_raw else None
        max_dt = _parse_value(max_raw, fmt) if max_raw else None
        if min_dt and parsed < min_dt:
            line_edit.setProperty("invalid", "true")
            error_label.setText(f"Date/time must be >= {min_raw}.")
            error_label.show()
            line_edit.style().unpolish(line_edit)
            line_edit.style().polish(line_edit)
            return
        if max_dt and parsed > max_dt:
            line_edit.setProperty("invalid", "true")
            error_label.setText(f"Date/time must be <= {max_raw}.")
            error_label.show()
            line_edit.style().unpolish(line_edit)
            line_edit.style().polish(line_edit)
            return

        line_edit.setProperty("invalid", "false")
        if error_label.property("_server_error"):
            error_label.setText(str(error_label.property("_server_error")))
            error_label.show()
        else:
            error_label.hide()
        line_edit.style().unpolish(line_edit)
        line_edit.style().polish(line_edit)

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        max_w = props.get("max_width")
        frame, layout = _field_shell(comp_id, _literal(props.get("label")), max_width=max_w)
        frame.setProperty("is_input", True)

        value = str(props.get("value") or "")
        fmt = str(props.get("format") or "yyyy-MM-dd")
        input_mask = _format_to_input_mask(fmt)

        line_edit = QLineEdit()
        line_edit.setObjectName(f"{comp_id}__input")
        line_edit.setProperty("ui_role", "advanced_datepicker")
        line_edit.setProperty("_format", fmt)
        line_edit.setProperty("_min_date", str(props.get("min_date") or ""))
        line_edit.setProperty("_max_date", str(props.get("max_date") or ""))
        line_edit.setInputMask(input_mask)
        line_edit.setPlaceholderText(fmt)
        line_edit.setText(value)

        err_label = QLabel()
        err_label.setProperty("ui_role", "form_error_label")
        err_label.setWordWrap(True)
        err_label.hide()
        if props.get("error"):
            err_label.setProperty("_server_error", self._literal_text(props.get("error")))
            err_label.setText(self._literal_text(props.get("error")))
            err_label.show()

        action = props.get("action")
        initial_value = line_edit.text().strip()
        frame.setProperty("value", initial_value)
        frame.setProperty("_confirmed_value", initial_value)
        publish_bound_value(app_instance, frame, comp_id, initial_value)

        def _on_change() -> None:
            current = line_edit.text().strip()
            previous = str(frame.property("_confirmed_value") or "")
            if current == previous:
                return
            confirm = action.get("confirm") if isinstance(action, dict) else None
            if action and not confirm_action(app_instance, confirm):
                line_edit.blockSignals(True)
                line_edit.setText(previous)
                line_edit.blockSignals(False)
                frame.setProperty("value", previous)
                self._validate_and_paint(frame, line_edit, err_label)
                return
            frame.setProperty("value", current)
            frame.setProperty("_confirmed_value", current)
            publish_bound_value(app_instance, line_edit, comp_id, current)
            self._validate_and_paint(frame, line_edit, err_label)
            if action:
                action_spec = action
                if isinstance(action, dict):
                    action_spec = dict(action)
                    action_spec.pop("confirm", None)
                emit_action_spec(
                    app_instance,
                    action_spec,
                    {comp_id: current, "value": current},
                    surface_id,
                    comp_id,
                )

        line_edit.editingFinished.connect(_on_change)
        self._validate_and_paint(frame, line_edit, err_label)

        layout.addWidget(line_edit)
        layout.addWidget(err_label)
        return frame

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "label":
            label = self._find_first_label(widget)
            if label is not None:
                label.setText(_literal(value))
            return

        line_edit = widget.findChild(QLineEdit, f"{widget.objectName()}__input")
        err_label = None
        for child in widget.findChildren(QLabel):
            if child.property("ui_role") == "form_error_label":
                err_label = child
                break
        if line_edit is None:
            super().update_widget_property(widget, prop, value)
            return

        if prop == "value":
            next_value = "" if value is None else str(value)
            if line_edit.text() != next_value:
                line_edit.blockSignals(True)
                line_edit.setText(next_value)
                line_edit.blockSignals(False)
            widget.setProperty("value", line_edit.text().strip())
            widget.setProperty("_confirmed_value", line_edit.text().strip())
            if err_label is not None:
                self._validate_and_paint(widget, line_edit, err_label)
            return
        if prop == "min_date":
            line_edit.setProperty("_min_date", "" if value is None else str(value))
            if err_label is not None:
                self._validate_and_paint(widget, line_edit, err_label)
            return
        if prop == "max_date":
            line_edit.setProperty("_max_date", "" if value is None else str(value))
            if err_label is not None:
                self._validate_and_paint(widget, line_edit, err_label)
            return
        if prop == "format":
            fmt = str(value or "yyyy-MM-dd")
            line_edit.setProperty("_format", fmt)
            line_edit.setInputMask(_format_to_input_mask(fmt))
            line_edit.setPlaceholderText(fmt)
            if err_label is not None:
                self._validate_and_paint(widget, line_edit, err_label)
            return
        if prop == "error" and err_label is not None:
            if value:
                err_label.setProperty("_server_error", self._literal_text(value))
                err_label.setText(self._literal_text(value))
                err_label.show()
            else:
                err_label.setProperty("_server_error", "")
                err_label.hide()
            self._validate_and_paint(widget, line_edit, err_label)
            return
        super().update_widget_property(widget, prop, value)
