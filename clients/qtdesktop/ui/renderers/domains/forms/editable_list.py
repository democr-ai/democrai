from typing import Any, Dict

from PySide6.QtCore import QSize, QSignalBlocker
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QLabel

from ...base import BaseRenderer, emit_action_spec, publish_bound_value
from ...icon import get_icon


class EditableListRenderer(BaseRenderer):
    component_type = "EditableList"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "value": self.PROPERTY,
            "item_label": self.PROPERTY,
            "add_label": self.PROPERTY,
            "remove_label": self.PROPERTY,
            "submit_label": self.PROPERTY,
            "placeholder": self.PROPERTY,
            "item_schema": self.PROPERTY,
        }

    def _validate_values(self, value: Any) -> list[str]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise ValueError("EditableList value must be a list of strings")
        return list(value)

    def _item_schema(self, widget: QFrame) -> dict[str, Any]:
        props = getattr(widget, "props", {})
        schema = props.get("item_schema")
        if not isinstance(schema, dict):
            raise ValueError("EditableList item_schema must be an object")
        schema_type = str(schema.get("type") or "").strip().lower()
        if schema_type not in {"text", "select"}:
            raise ValueError("EditableList item_schema type must be text or select")
        if schema_type == "text":
            return {"type": "text", "options": []}
        options = schema.get("options")
        if not isinstance(options, list):
            raise ValueError("EditableList select item_schema options must be a list")
        for option in options:
            if (
                not isinstance(option, dict)
                or not isinstance(option.get("label"), str)
                or not isinstance(option.get("value"), str)
            ):
                raise ValueError("EditableList select options must have string label and value")
        return {"type": "select", "options": options}

    def _row_control(self, row: QFrame) -> QComboBox | QLineEdit | None:
        combo = row.findChild(QComboBox)
        if combo is not None:
            return combo
        return row.findChild(QLineEdit)

    def _current_values(self, widget: QFrame) -> list[str]:
        rows = getattr(widget, "rows_layout", None)
        if rows is None:
            return []
        values: list[str] = []
        for index in range(rows.count()):
            item = rows.itemAt(index)
            row = item.widget() if item is not None else None
            if row is None:
                continue
            control = self._row_control(row)
            if isinstance(control, QComboBox):
                values.append(str(control.currentData()))
            elif isinstance(control, QLineEdit):
                values.append(control.text())
        return values

    def _set_control_value(self, control: QComboBox | QLineEdit, value: str) -> None:
        with QSignalBlocker(control):
            if isinstance(control, QComboBox):
                selected_index = control.findData(value)
                if selected_index >= 0:
                    control.setCurrentIndex(selected_index)
                return
            control.setText(value)

    def _publish_current(self, widget: QFrame) -> None:
        values = self._current_values(widget)
        widget.setProperty("is_input", True)
        widget.setProperty("value", values)
        widget._editable_list_values = list(values)  # type: ignore[attr-defined]
        publish_bound_value(
            getattr(widget, "app_instance", None),
            widget,
            getattr(widget, "comp_id", widget.objectName()),
            values,
        )

    def _add_row(self, widget: QFrame, text: str = "") -> None:
        rows = getattr(widget, "rows_layout", None)
        if rows is None:
            return
        props = getattr(widget, "props", {})
        schema = self._item_schema(widget)
        row = QFrame()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)
        if schema["type"] == "select":
            edit = QComboBox()
            for option in schema["options"]:
                edit.addItem(option["label"], option["value"])
            self._set_control_value(edit, text)
        else:
            edit = QLineEdit()
            edit.setPlaceholderText(str(props.get("placeholder") or ""))
            self._set_control_value(edit, str(text))
        edit.setProperty("is_input", True)
        edit.setProperty("ui_role", "form_input")
        remove_text = self._literal_text(props.get("remove_label"), "Remove")
        remove_button = QPushButton()
        remove_button.setToolTip(remove_text)
        remove_button.setAccessibleName(remove_text)
        remove_button.setProperty("variant", "danger")
        remove_button.setIcon(get_icon("ric.delete-bin-2-line", "#ffffff", 16))
        remove_button.setIconSize(QSize(16, 16))
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(remove_button)
        rows.addWidget(row)
        if isinstance(edit, QComboBox):
            edit.currentIndexChanged.connect(lambda _index: self._publish_current(widget))
        else:
            edit.textChanged.connect(lambda _text: self._publish_current(widget))
        remove_button.clicked.connect(lambda _checked=False, r=row: self._remove_row(widget, r))

    def _remove_row(self, widget: QFrame, row: QFrame) -> None:
        rows = getattr(widget, "rows_layout", None)
        if rows is None:
            return
        rows.removeWidget(row)
        row.setParent(None)
        row.deleteLater()
        self._publish_current(widget)

    def _sync_rows(self, widget: QFrame, value: Any) -> None:
        values = self._validate_values(value)
        rows = getattr(widget, "rows_layout", None)
        if rows is None:
            return

        while rows.count() > len(values):
            item = rows.takeAt(rows.count() - 1)
            row = item.widget()
            if row is not None:
                row.setParent(None)
                row.deleteLater()

        while rows.count() < len(values):
            self._add_row(widget, values[rows.count()])

        for index, value_item in enumerate(values):
            item = rows.itemAt(index)
            row = item.widget() if item is not None else None
            if row is None:
                continue
            control = self._row_control(row)
            if control is not None:
                self._set_control_value(control, value_item)

        widget.setProperty("is_input", True)
        widget.setProperty("value", list(values))
        widget._editable_list_values = list(values)  # type: ignore[attr-defined]

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QFrame()
        container.setObjectName(comp_id)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label_text = self._literal_text(props.get("item_label"))
        if label_text:
            label = QLabel(label_text)
            label.setProperty("ui_role", "form_label")
            layout.addWidget(label)

        rows = QVBoxLayout()
        rows.setContentsMargins(0, 0, 0, 0)
        rows.setSpacing(6)
        layout.addLayout(rows)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        add_button = QPushButton(self._literal_text(props.get("add_label"), "Add"))
        save_button = QPushButton(self._literal_text(props.get("submit_label"), "Save"))
        actions.addWidget(add_button)
        actions.addWidget(save_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        container.props = props  # type: ignore[attr-defined]
        container.surface_id = surface_id  # type: ignore[attr-defined]
        container.app_instance = app_instance  # type: ignore[attr-defined]
        container.comp_id = comp_id  # type: ignore[attr-defined]
        container.rows_layout = rows  # type: ignore[attr-defined]

        self._sync_rows(container, props.get("value"))
        self._publish_current(container)

        def add_empty_row() -> None:
            self._add_row(container, "")
            self._publish_current(container)

        add_button.clicked.connect(add_empty_row)
        save_button.clicked.connect(
            lambda: emit_action_spec(
                app_instance,
                props.get("action"),
                {
                    **(props.get("params") if isinstance(props.get("params"), dict) else {}),
                    comp_id: self._current_values(container),
                    "value": self._current_values(container),
                },
                surface_id,
                comp_id,
            )
        )

        container.setProperty("type", "editable_list")
        return container

    def update_widget_property(self, widget: QFrame, prop: str, value: Any):
        if prop == "value":
            self._sync_rows(widget, value)
            return
        super().update_widget_property(widget, prop, value)
