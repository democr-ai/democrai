from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ...base import BaseRenderer, emit_action_spec, publish_bound_value
from ..layout.flow import FlowLayout
from .common import _field_shell, _literal


def _values_equal(left: Any, right: Any) -> bool:
    return left == right


class TagsInputRenderer(BaseRenderer):
    component_type = "TagsInput"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "value": self.PROPERTY,
            "placeholder": self.PROPERTY,
            "add_label": self.PROPERTY,
            "item_schema": self.PROPERTY,
        }

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        frame, layout = _field_shell(comp_id, _literal(props.get("label")))
        chips = FlowLayout(spacing=6)
        chips.setContentsMargins(0, 0, 0, 0)
        chip_frame = QFrame()
        chip_frame.setLayout(chips)
        layout.addWidget(chip_frame)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(6)
        layout.addLayout(controls)

        error_label = QLabel()
        error_label.setProperty("ui_role", "form_error_label")
        error_label.setWordWrap(True)
        error_label.hide()
        layout.addWidget(error_label)

        schema = self._item_schema(props.get("item_schema"))
        values = self._values(props.get("value"))
        frame.setProperty("is_input", True)
        frame.setProperty("value", list(values))
        frame.setProperty("_tags_values", list(values))
        frame.setProperty("_tags_schema", schema)
        frame.setProperty("_chips_layout", chips)
        frame.setProperty("_surface_id", surface_id)
        frame.setProperty("_app_instance", app_instance)
        frame.setProperty("_component_id", comp_id)
        frame.setProperty("_action", props.get("action"))
        frame.setProperty("_params", props.get("params") if isinstance(props.get("params"), dict) else {})
        publish_bound_value(app_instance, frame, comp_id, list(values))

        input_widget = self._build_input(schema, props, comp_id)
        controls.addWidget(input_widget, 1)
        add_button = QPushButton(_literal(props.get("add_label"), "Add"))
        controls.addWidget(add_button)
        frame.setProperty("_tags_input", input_widget)
        frame.setProperty("_tags_add_button", add_button)

        def add_current() -> None:
            current = self._candidate_value(schema, input_widget)
            if current is None:
                return
            existing = list(frame.property("_tags_values") or [])
            if any(_values_equal(item, current) for item in existing):
                return
            self._publish(frame, existing + [current])
            if isinstance(input_widget, QLineEdit):
                input_widget.clear()

        add_button.clicked.connect(add_current)
        if isinstance(input_widget, QLineEdit):
            input_widget.returnPressed.connect(add_current)

        self._render_chips(frame)
        if props.get("error"):
            self.update_widget_property(frame, "error", props["error"])
        return frame

    @staticmethod
    def _values(value: Any) -> list[Any]:
        if not isinstance(value, list):
            raise ValueError("TagsInput value must be a list")
        return list(value)

    @staticmethod
    def _item_schema(schema: Any) -> dict[str, Any]:
        if not isinstance(schema, dict):
            raise ValueError("TagsInput item_schema must be an object")
        schema_type = str(schema.get("type") or "").strip().lower()
        if schema_type not in {"text", "string", "number", "boolean", "select"}:
            raise ValueError("TagsInput item_schema type must be text, string, number, boolean or select")
        if schema_type != "select":
            return {"type": schema_type, "options": []}
        options = schema.get("options")
        if not isinstance(options, list):
            raise ValueError("TagsInput select item_schema options must be a list")
        for option in options:
            if not isinstance(option, dict) or not isinstance(option.get("label"), str) or "value" not in option:
                raise ValueError("TagsInput select options must have label and value")
        return {"type": "select", "options": list(options)}

    def _build_input(self, schema: dict[str, Any], props: Dict[str, Any], comp_id: str) -> QWidget:
        schema_type = schema["type"]
        if schema_type in {"boolean", "select"}:
            combo = QComboBox()
            combo.setObjectName(f"{comp_id}__input")
            combo.setProperty("ui_role", "form_input")
            if schema_type == "boolean":
                combo.addItem("true", True)
                combo.addItem("false", False)
            else:
                if not schema["options"]:
                    raise ValueError("TagsInput select item_schema requires at least one option")
                for option in schema["options"]:
                    combo.addItem(str(option["label"]), option["value"])
            return combo
        edit = QLineEdit()
        edit.setObjectName(f"{comp_id}__input")
        edit.setPlaceholderText(str(props.get("placeholder") or ""))
        edit.setProperty("ui_role", "form_input")
        return edit

    @staticmethod
    def _candidate_value(schema: dict[str, Any], input_widget: QWidget) -> Any:
        schema_type = schema["type"]
        if isinstance(input_widget, QComboBox):
            return input_widget.currentData()
        if not isinstance(input_widget, QLineEdit):
            return None
        text = input_widget.text().strip()
        if schema_type == "number":
            if not text:
                return None
            try:
                return float(text) if "." in text else int(text)
            except ValueError:
                return None
        if not text:
            return None
        return text

    def _item_text(self, schema: dict[str, Any], value: Any) -> str:
        if schema["type"] == "select":
            for option in schema["options"]:
                if _values_equal(option.get("value"), value):
                    return str(option.get("label") or "")
        return str(value)

    def _render_chips(self, frame: QFrame) -> None:
        layout = frame.property("_chips_layout")
        if layout is None:
            return
        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.setParent(None)
                child.deleteLater()
        schema = frame.property("_tags_schema")
        values = list(frame.property("_tags_values") or [])
        for index, value in enumerate(values):
            chip = QFrame()
            chip.setProperty("ui_role", "tags_input_chip")
            row = QHBoxLayout(chip)
            row.setContentsMargins(8, 2, 4, 2)
            row.setSpacing(3)
            label = QLabel(self._item_text(schema, value))
            label.setProperty("ui_role", "tags_input_chip_label")
            remove = QPushButton("x")
            remove.setProperty("ui_role", "tags_input_chip_remove")
            remove.setCursor(Qt.CursorShape.PointingHandCursor)
            remove.clicked.connect(lambda _checked=False, i=index: self._remove_index(frame, i))
            row.addWidget(label)
            row.addWidget(remove)
            layout.addWidget(chip)

    def _remove_index(self, frame: QFrame, index: int) -> None:
        values = list(frame.property("_tags_values") or [])
        self._publish(frame, [item for item_index, item in enumerate(values) if item_index != index])

    def _publish(self, frame: QFrame, values: list[Any]) -> None:
        frame.setProperty("_tags_values", list(values))
        frame.setProperty("value", list(values))
        app_instance = frame.property("_app_instance")
        comp_id = str(frame.property("_component_id") or frame.objectName())
        surface_id = str(frame.property("_surface_id") or "main")
        publish_bound_value(app_instance, frame, comp_id, list(values))
        action = frame.property("_action")
        if action:
            params = frame.property("_params")
            emit_action_spec(
                app_instance,
                action,
                {
                    **(params if isinstance(params, dict) else {}),
                    comp_id: list(values),
                    "value": list(values),
                },
                surface_id,
                comp_id,
            )
        self._render_chips(frame)
        callback = getattr(frame, "_form_on_value_changed", None)
        if callable(callback):
            callback()

    def update_widget_property(self, widget: QFrame, prop: str, value: Any):
        if prop == "value":
            values = self._values(value)
            widget.setProperty("_tags_values", list(values))
            widget.setProperty("value", list(values))
            self._render_chips(widget)
            return
        if prop == "error":
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "form_error_label":
                    if value:
                        child.setText(_literal(value))
                        child.show()
                    else:
                        child.hide()
                    return
        return super().update_widget_property(widget, prop, value)
