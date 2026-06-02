from __future__ import annotations
from typing import Any, Dict, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QWidget, QLabel
from ...base import BaseRenderer, emit_action_spec, publish_bound_value

class TextAreaRenderer(BaseRenderer):
    component_type = "TextArea"

    _DEFAULT_ROWS = 3

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "value": self.PROPERTY,
            "placeholder": self.PROPERTY,
            "disabled": self.PROPERTY,
            "rows": self.PROPERTY,
            "auto_resize": self.PROPERTY,
            "error": self.PROPERTY,
        }

    @staticmethod
    def _rows_to_min_height(text_edit: QTextEdit, rows: int) -> int:
        safe_rows = max(1, int(rows or 1))
        line_height = text_edit.fontMetrics().lineSpacing()
        doc_margin = int(text_edit.document().documentMargin() * 2)
        frame = int(text_edit.frameWidth() * 2)
        inner_padding = 8
        return max(44, (line_height * safe_rows) + doc_margin + frame + inner_padding)

    @classmethod
    def _content_height(cls, text_edit: QTextEdit, rows: int) -> int:
        min_height = cls._rows_to_min_height(text_edit, rows)
        doc_height = int(text_edit.document().size().height())
        frame = int(text_edit.frameWidth() * 2)
        inner_padding = 8
        return max(min_height, doc_height + frame + inner_padding)

    @classmethod
    def _apply_sizing(cls, text_edit: QTextEdit) -> None:
        rows = int(text_edit.property("_rows") or cls._DEFAULT_ROWS)
        auto_resize = bool(text_edit.property("_auto_resize"))
        min_height = cls._rows_to_min_height(text_edit, rows)
        text_edit.setMinimumHeight(min_height)
        if auto_resize:
            text_edit.setMaximumHeight(16777215)
            text_edit.setFixedHeight(cls._content_height(text_edit, rows))
        else:
            text_edit.setFixedHeight(min_height)

    def render(
        self,
        props: dict,
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label_text = self._literal_text(props.get("label"))
        if label_text:
            label = QLabel(label_text)
            label.setProperty("ui_role", "form_label")
            layout.addWidget(label)

        te = QTextEdit()
        te.setPlainText(props.get("value", ""))
        te.setPlaceholderText(props.get("placeholder", ""))
        te.setObjectName(comp_id)
        te.setProperty("is_input", True)
        te.setProperty("ui_role", "form_textarea")
        te.setProperty("error", False)
        te.setProperty("invalid", "false")
        te.setProperty("_rows", int(props.get("rows", self._DEFAULT_ROWS) or self._DEFAULT_ROWS))
        te.setProperty("_auto_resize", bool(props.get("auto_resize", True)))
        te.setDisabled(bool(props.get("disabled", False)))
        self._apply_sizing(te)

        layout.addWidget(te)

        # Error label
        err_label = QLabel()
        err_label.setProperty("ui_role", "form_error_label")
        err_label.setWordWrap(True)
        err_label.hide()
        layout.addWidget(err_label)
        
        # Bind value
        publish_bound_value(app_instance, te, comp_id, te.toPlainText(), prop_name="value")
        def _on_text_changed(send_action: bool = True) -> None:
            self._apply_sizing(te)
            current = te.toPlainText()
            publish_bound_value(app_instance, te, comp_id, current, prop_name="value")
            action = props.get("onChangeAction")
            if send_action and action:
                emit_action_spec(
                    app_instance,
                    action,
                    {comp_id: current, "value": current},
                    surface_id,
                    comp_id,
                )

        te.textChanged.connect(_on_text_changed)
        _on_text_changed(False)

        # Initial error state (same behavior as other form renderers)
        if props.get("error"):
            self.update_widget_property(container, "error", props["error"])

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        te = widget if isinstance(widget, QTextEdit) else widget.findChild(QTextEdit)
        host = widget if not isinstance(widget, QTextEdit) else (widget.parentWidget() or widget)
        if prop == "value":
            if te:
                next_text = "" if value is None else str(value)
                if te.toPlainText() != next_text:
                    te.setPlainText(next_text)
                self._apply_sizing(te)
            return
        if prop == "placeholder":
            if te:
                te.setPlaceholderText("" if value is None else str(value))
            return
        if prop == "disabled":
            if te:
                te.setDisabled(bool(value))
            return
        if prop == "rows":
            if te:
                te.setProperty("_rows", int(value or self._DEFAULT_ROWS))
                self._apply_sizing(te)
            return
        if prop == "auto_resize":
            if te:
                te.setProperty("_auto_resize", bool(value))
                self._apply_sizing(te)
            return
        if prop == "error":
            field_label = None
            for candidate in host.findChildren(QLabel):
                if candidate.property("ui_role") == "form_label":
                    field_label = candidate
                    break
            has_error = bool(value)
            if te:
                te.setProperty("error", has_error)
                te.setProperty("invalid", "true" if has_error else "false")
            if field_label is not None:
                field_label.setProperty("invalid", "true" if has_error else "false")
                field_label.style().unpolish(field_label)
                field_label.style().polish(field_label)
            for child in host.findChildren(QLabel):
                if child.property("ui_role") == "form_error_label":
                    if has_error:
                        child.setText(self._literal_text(value))
                        child.show()
                    else:
                        child.hide()
                    if te:
                        te.style().unpolish(te)
                        te.style().polish(te)
                    return
            if te:
                te.style().unpolish(te)
                te.style().polish(te)
            return
        super().update_widget_property(widget, prop, value)
