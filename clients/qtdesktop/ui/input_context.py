from __future__ import annotations

from typing import Any

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QRadioButton,
    QTextEdit,
    QWidget,
)


def read_input_widget_value(widget: QWidget) -> Any:
    """Return a normalized value for supported input widget types."""
    if isinstance(widget, QLineEdit):
        return widget.text()
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        return widget.toPlainText()
    if isinstance(widget, QCheckBox):
        return widget.isChecked()
    if isinstance(widget, QComboBox):
        data = widget.currentData()
        return data if data is not None else widget.currentText()
    if isinstance(widget, QListWidget):
        selected = []
        for item in widget.selectedItems():
            user_role = item.data(Qt.ItemDataRole.UserRole)
            selected.append(user_role if user_role is not None else item.text())
        return selected
    if isinstance(widget, QGroupBox):
        for radio in widget.findChildren(QRadioButton):
            if radio.isChecked():
                rb_val = radio.property("rb_value")
                return rb_val if rb_val is not None else radio.text()
        return ""
    return widget.property("value")


def collect_action_context(input_widgets: list[QWidget]) -> dict[str, Any]:
    """Build `{componentId: value}` context from active input widgets."""
    values: dict[str, Any] = {}
    for widget in input_widgets:
        if not shiboken6.isValid(widget):
            continue
        key = widget.objectName()
        if not key or key == "unknown":
            continue
        values[key] = read_input_widget_value(widget)
    return values
