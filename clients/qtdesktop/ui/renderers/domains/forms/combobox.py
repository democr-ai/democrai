from __future__ import annotations
from typing import Any, Dict
from PySide6.QtWidgets import QComboBox, QLabel, QWidget
from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from .common import _field_shell, _literal, _options

class ComboboxRenderer(BaseRenderer):
    component_type = "Combobox"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "value": self.PROPERTY,
            "options": self.PROPERTY,
            "placeholder": self.PROPERTY,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        label = _literal(props.get("label"))
        max_w = props.get("max_width")
        frame, layout = _field_shell(comp_id, label, max_width=max_w)
        widget = QComboBox()
        widget.setObjectName(f"{comp_id}__input")
        widget.setProperty("ui_role", "advanced_combobox")

        opts = _options(props.get("options", []))
        placeholder = str(props.get("placeholder", "") or "")
        if placeholder:
            widget.addItem(placeholder, None)
        for text, value in opts:
            widget.addItem(text, value)

        current_value = props.get("value", "")
        action = props.get("action")
        index = next((i for i in range(widget.count()) if widget.itemData(i) == current_value), 0)
        if widget.count():
            widget.setCurrentIndex(index)
        publish_bound_value(app_instance, widget, comp_id, widget.currentData())
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
        return frame

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "label":
            label = self._find_first_label(widget)
            if label is not None:
                label.setText(_literal(value))
            return
        combo = widget.findChild(QComboBox, f"{widget.objectName()}__input")
        if combo is None:
            super().update_widget_property(widget, prop, value)
            return
        if prop == "placeholder":
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
            current = combo.currentData()
            placeholder = combo.itemText(0) if combo.count() > 0 and combo.itemData(0) is None else ""
            combo.clear()
            if placeholder:
                combo.addItem(placeholder, None)
            for text, option_value in _options(value or []):
                combo.addItem(text, option_value)
            index = next((i for i in range(combo.count()) if combo.itemData(i) == current), 0)
            if combo.count():
                combo.setCurrentIndex(index)
            return
        if prop == "value":
            index = next((i for i in range(combo.count()) if combo.itemData(i) == value), combo.currentIndex())
            if combo.count():
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
                widget.setProperty("value", combo.currentData())
                widget.setProperty("_confirmed_index", combo.currentIndex())
                widget.setProperty("_confirmed_value", combo.currentData())
            return
        super().update_widget_property(widget, prop, value)
