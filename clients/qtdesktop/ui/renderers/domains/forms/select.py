from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QWidget,
)
from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from ...icon import get_icon
from .common import _field_shell, _literal, _options

class SelectRenderer(BaseRenderer):
    component_type = "Select"

    @staticmethod
    def _sync_multi_icons(widget: QListWidget) -> None:
        check_icon = get_icon("ric.check-line", "#93C5FD", 14)
        for index in range(widget.count()):
            item = widget.item(index)
            item.setIcon(check_icon if item.isSelected() else QIcon())

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "value": self.PROPERTY,
            "options": self.PROPERTY,
            "placeholder": self.PROPERTY,
            "multiple": self.SURFACE,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        label = _literal(props.get("label"))
        max_w = props.get("max_width")
        frame, layout = _field_shell(comp_id, label, max_width=max_w)
        multiple = bool(props.get("multiple", False))
        opts = _options(props.get("options", []))
        current_value = props.get("value", [] if multiple else "")
        action = props.get("action")

        if multiple:
            widget = QListWidget()
            widget.setObjectName(f"{comp_id}__input")
            widget.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
            widget.setProperty("ui_role", "advanced_select_multi")
            widget.setProperty("ui_mode", "web_like")
            widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            widget.setSpacing(4)
            widget.setMinimumHeight(112)
            selected = {str(item) for item in (current_value or [])}
            for text, value in opts:
                item = QListWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, value)
                widget.addItem(item)
                if str(value) in selected:
                    item.setSelected(True)
            self._sync_multi_icons(widget)
            initial_values = [option_value for _, option_value in opts if str(option_value) in selected]
            publish_bound_value(app_instance, widget, comp_id, initial_values)
            frame.setProperty("is_input", True)
            frame.setProperty("value", initial_values)
            frame.setProperty("_confirmed_value", initial_values)

            def on_change():
                self._sync_multi_icons(widget)
                values = [
                    widget.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(widget.count())
                    if widget.item(i).isSelected()
                ]
                confirm = action.get("confirm") if isinstance(action, dict) else None
                if action and not confirm_action(app_instance, confirm):
                    previous = frame.property("_confirmed_value")
                    previous_values = previous if isinstance(previous, list) else []
                    widget.blockSignals(True)
                    selected_previous = {str(item) for item in previous_values}
                    for index in range(widget.count()):
                        item = widget.item(index)
                        item.setSelected(str(item.data(Qt.ItemDataRole.UserRole)) in selected_previous)
                    widget.blockSignals(False)
                    self._sync_multi_icons(widget)
                    frame.setProperty("value", previous_values)
                    return
                publish_bound_value(app_instance, widget, comp_id, values)
                frame.setProperty("value", values)
                frame.setProperty("_confirmed_value", values)
                if action:
                    action_spec = action
                    if isinstance(action, dict):
                        action_spec = dict(action)
                        action_spec.pop("confirm", None)
                    emit_action_spec(
                        app_instance,
                        action_spec,
                        {"value": values, comp_id: values},
                        surface_id,
                        comp_id,
                    )

            widget.itemSelectionChanged.connect(on_change)
        else:
            widget = QComboBox()
            widget.setObjectName(f"{comp_id}__input")
            widget.setProperty("ui_role", "advanced_select")
            placeholder = str(props.get("placeholder", "") or "")
            if placeholder:
                widget.addItem(placeholder, None)
            for text, value in opts:
                widget.addItem(text, value)
            index = next((i for i in range(widget.count()) if widget.itemData(i) == current_value), 0)
            widget.setCurrentIndex(index)
            publish_bound_value(app_instance, widget, comp_id, widget.currentData())
            frame.setProperty("is_input", True)
            frame.setProperty("value", widget.currentData())
            frame.setProperty("_confirmed_index", widget.currentIndex())
            frame.setProperty("_confirmed_value", widget.currentData())

            def on_change(_index: int):
                value = widget.currentData()
                confirm = action.get("confirm") if isinstance(action, dict) else None
                if action and not confirm_action(app_instance, confirm):
                    previous_index = int(frame.property("_confirmed_index") or 0)
                    widget.blockSignals(True)
                    widget.setCurrentIndex(previous_index)
                    widget.blockSignals(False)
                    frame.setProperty("value", frame.property("_confirmed_value"))
                    return
                publish_bound_value(app_instance, widget, comp_id, value)
                frame.setProperty("value", value)
                frame.setProperty("_confirmed_index", widget.currentIndex())
                frame.setProperty("_confirmed_value", value)
                if action:
                    action_spec = action
                    if isinstance(action, dict):
                        action_spec = dict(action)
                        action_spec.pop("confirm", None)
                    emit_action_spec(
                        app_instance,
                        action_spec,
                        {"value": value, comp_id: value},
                        surface_id,
                        comp_id,
                    )

            widget.currentIndexChanged.connect(on_change)

        layout.addWidget(widget)

        # Error label
        self.error_label = QLabel()
        self.error_label.setProperty("ui_role", "form_error_label")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)

        # Initial error state
        if props.get("error"):
            self.update_widget_property(frame, "error", props["error"])

        return frame

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "label":
            label = self._find_first_label(widget)
            if label is not None:
                label.setText(_literal(value))
            return
        if prop == "placeholder":
            combo = widget.findChild(QComboBox, f"{widget.objectName()}__input")
            if combo is not None:
                placeholder = str(value or "")
                has_placeholder = combo.count() > 0 and combo.itemData(0) is None
                if placeholder:
                    if has_placeholder:
                        combo.setItemText(0, placeholder)
                    else:
                        combo.insertItem(0, placeholder, None)
                elif has_placeholder:
                    combo.removeItem(0)
            return
        if prop == "options":
            list_widget = widget.findChild(QListWidget, f"{widget.objectName()}__input")
            if list_widget is not None:
                selected = {
                    list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(list_widget.count())
                    if list_widget.item(i).isSelected()
                }
                list_widget.clear()
                for text, option_value in _options(value or []):
                    item = QListWidgetItem(text)
                    item.setData(Qt.ItemDataRole.UserRole, option_value)
                    list_widget.addItem(item)
                    if option_value in selected:
                        item.setSelected(True)
                self._sync_multi_icons(list_widget)
                return

            combo = widget.findChild(QComboBox, f"{widget.objectName()}__input")
            if combo is not None:
                current = combo.currentData()
                placeholder = combo.itemText(0) if combo.count() > 0 and combo.itemData(0) is None else ""
                combo.clear()
                if placeholder:
                    combo.addItem(placeholder, None)
                for text, option_value in _options(value or []):
                    combo.addItem(text, option_value)
                index = next((i for i in range(combo.count()) if combo.itemData(i) == current), 0)
                combo.setCurrentIndex(index)
            return
        if prop == "value":
            list_widget = widget.findChild(QListWidget, f"{widget.objectName()}__input")
            if list_widget is not None:
                selected = {str(item) for item in (value or [])}
                list_widget.blockSignals(True)
                for index in range(list_widget.count()):
                    item = list_widget.item(index)
                    item.setSelected(str(item.data(Qt.ItemDataRole.UserRole)) in selected)
                list_widget.blockSignals(False)
                self._sync_multi_icons(list_widget)
                ordered_values = [
                    list_widget.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(list_widget.count())
                    if list_widget.item(i).isSelected()
                ]
                widget.setProperty("value", ordered_values)
                widget.setProperty("_confirmed_value", ordered_values)
                return

            combo = widget.findChild(QComboBox, f"{widget.objectName()}__input")
            if combo is not None:
                index = next(
                    (i for i in range(combo.count()) if combo.itemData(i) == value),
                    combo.currentIndex(),
                )
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
                widget.setProperty("value", combo.currentData())
                widget.setProperty("_confirmed_index", combo.currentIndex())
                widget.setProperty("_confirmed_value", combo.currentData())
            return
        if prop == "error":
            field_label = None
            for candidate in widget.findChildren(QLabel):
                if candidate.property("ui_role") == "advanced_field_label":
                    field_label = candidate
                    break
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "form_error_label":
                    if value:
                        child.setText(self._literal_text(value))
                        child.show()
                        # Apply error style to the input widget
                        input_widget = widget.findChild(QWidget, f"{widget.objectName()}__input")
                        if input_widget:
                            input_widget.setProperty("error", True)
                            input_widget.setProperty("invalid", "true")
                            input_widget.style().unpolish(input_widget)
                            input_widget.style().polish(input_widget)
                        if field_label is not None:
                            field_label.setProperty("invalid", "true")
                            field_label.style().unpolish(field_label)
                            field_label.style().polish(field_label)
                    else:
                        child.hide()
                        input_widget = widget.findChild(QWidget, f"{widget.objectName()}__input")
                        if input_widget:
                            input_widget.setProperty("error", False)
                            input_widget.setProperty("invalid", "false")
                            input_widget.style().unpolish(input_widget)
                            input_widget.style().polish(input_widget)
                        if field_label is not None:
                            field_label.setProperty("invalid", "false")
                            field_label.style().unpolish(field_label)
                            field_label.style().polish(field_label)
                    return
            return
        super().update_widget_property(widget, prop, value)
