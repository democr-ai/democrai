from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)


class RadioGroupRenderer(BaseRenderer):
    component_type = "RadioGroup"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "value": self.PROPERTY,
            "label": self.PROPERTY,
            "options": self.PROPERTY,
            "error": self.PROPERTY,
        }

    @staticmethod
    def _normalize_options(options: Any) -> list[tuple[str, Any]]:
        if not isinstance(options, list):
            return []
        normalized: list[tuple[str, Any]] = []
        for entry in options:
            if isinstance(entry, dict):
                label = str(entry.get("label", entry.get("value", "")))
                value = entry.get("value")
            else:
                label = str(entry)
                value = entry
            normalized.append((label, value))
        return normalized

    @staticmethod
    def _selected_value(container: QWidget) -> Any:
        for rb in container.findChildren(QRadioButton):
            if rb.isChecked():
                return rb.property("rb_value")
        return ""

    def _render_options(
        self,
        group_widget: QWidget,
        button_group: QButtonGroup,
        options: list[tuple[str, Any]],
        current_value: Any,
    ) -> None:
        layout = group_widget.layout()
        if not isinstance(layout, QHBoxLayout):
            return

        while layout.count():
            item = layout.takeAt(0)
            child = item.widget()
            if child is not None:
                child.deleteLater()

        for button in button_group.buttons():
            button_group.removeButton(button)

        for index, (label, value) in enumerate(options):
            rb = QRadioButton(label)
            rb.setProperty("rb_value", value)
            rb.setProperty("ui_role", "form_radio")
            rb.setCursor(Qt.CursorShape.PointingHandCursor)
            if value == current_value:
                rb.setChecked(True)
            button_group.addButton(rb, index)
            layout.addWidget(rb)

        layout.addStretch()

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        options = self._normalize_options(props.get("options", []))
        current_val = props.get("value", "")

        container = QWidget()
        container.setObjectName(comp_id)
        container.setProperty("is_input", True)
        container.setProperty("value", current_val if current_val is not None else "")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(self._literal_text(props.get("label")))
        label.setProperty("ui_role", "form_label")
        layout.addWidget(label)

        group_widget = QWidget()
        group_widget.setObjectName(f"{comp_id}__group")
        group_layout = QHBoxLayout(group_widget)
        group_layout.setContentsMargins(0, 4, 0, 0)
        group_layout.setSpacing(20)
        layout.addWidget(group_widget)

        button_group = QButtonGroup(container)
        container.setProperty("_button_group", button_group)
        self._render_options(group_widget, button_group, options, current_val)

        err_label = QLabel()
        err_label.setProperty("ui_role", "form_error_label")
        err_label.setWordWrap(True)
        err_label.hide()
        layout.addWidget(err_label)

        initial_value = self._selected_value(container)
        container.setProperty("value", initial_value)
        container.setProperty("_confirmed_value", initial_value)
        publish_bound_value(app_instance, container, comp_id, initial_value)

        def on_clicked(button: QRadioButton) -> None:
            selected = button.property("rb_value")
            action = props.get("action")
            confirm = action.get("confirm") if isinstance(action, dict) else None
            if action and not confirm_action(app_instance, confirm):
                previous = container.property("_confirmed_value")
                for rb in container.findChildren(QRadioButton):
                    rb.blockSignals(True)
                    rb.setChecked(rb.property("rb_value") == previous)
                    rb.blockSignals(False)
                container.setProperty("value", previous if previous is not None else "")
                return
            container.setProperty("value", selected if selected is not None else "")
            container.setProperty("_confirmed_value", selected if selected is not None else "")
            publish_bound_value(app_instance, container, comp_id, selected)
            if not isinstance(action, dict):
                return
            action_spec = dict(action)
            action_spec.pop("confirm", None)
            emit_action_spec(
                app_instance,
                action_spec,
                {comp_id: selected, "value": selected},
                surface_id,
                comp_id,
            )

        button_group.buttonClicked.connect(on_clicked)

        if props.get("error"):
            self.update_widget_property(container, "error", props["error"])

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        if prop == "label":
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "form_label":
                    child.setText(self._literal_text(value))
                    return
            return

        if prop == "options":
            group_widget = widget.findChild(QWidget, f"{widget.objectName()}__group")
            button_group = widget.property("_button_group")
            if isinstance(group_widget, QWidget) and isinstance(button_group, QButtonGroup):
                current = widget.property("value")
                if current in (None, ""):
                    current = self._selected_value(widget)
                self._render_options(group_widget, button_group, self._normalize_options(value), current)
                widget.setProperty("value", self._selected_value(widget))
            return

        if prop == "value":
            matched = False
            for rb in widget.findChildren(QRadioButton):
                is_match = rb.property("rb_value") == value
                rb.setChecked(is_match)
                matched = matched or is_match
            if not matched:
                for rb in widget.findChildren(QRadioButton):
                    rb.setChecked(False)
                widget.setProperty("value", "")
            else:
                widget.setProperty("value", value)
            widget.setProperty("_confirmed_value", widget.property("value"))
            return

        if prop == "error":
            has_error = bool(value)
            field_label = None
            err_label = None

            for child in widget.findChildren(QLabel):
                role = child.property("ui_role")
                if role == "form_label" and field_label is None:
                    field_label = child
                if role == "form_error_label" and err_label is None:
                    err_label = child

            if field_label is not None:
                field_label.setProperty("invalid", "true" if has_error else "false")
                field_label.style().unpolish(field_label)
                field_label.style().polish(field_label)

            for rb in widget.findChildren(QRadioButton):
                rb.setProperty("invalid", "true" if has_error else "false")
                rb.style().unpolish(rb)
                rb.style().polish(rb)

            if err_label is not None:
                if has_error:
                    err_label.setText(self._literal_text(value))
                    err_label.show()
                else:
                    err_label.hide()
            return

        super().update_widget_property(widget, prop, value)
