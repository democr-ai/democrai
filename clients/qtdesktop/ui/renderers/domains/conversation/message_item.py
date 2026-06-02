from __future__ import annotations
from typing import Any, Dict
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QFrame, QPlainTextEdit, QTextEdit, QToolButton, QVBoxLayout, QWidget
from ...base import BaseRenderer
from .common import _literal
from .message_list import _AutoResizeMarkdownBrowser
from .message_list import _message_card


class MessageItemRenderer(BaseRenderer):
    component_type = "MessageItem"

    def render(self, props: Dict[str, Any], surface_id: str, app_instance: Any, comp_id: str = "unknown"):
        return _message_card(
            {
                "role":    props.get("role", "assistant"),
                "text":    props.get("text"),
                "meta":    props.get("meta"),
                "reasoning": props.get("reasoning"),
                "actions": props.get("actions", []),
            },
            surface_id,
            app_instance,
            comp_id,
        )

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "text":
            body = getattr(widget, "_message_body_widget", None)
            text = _literal(value)
            if hasattr(body, "set_markdown"):
                body.set_markdown(text)
                return
            if isinstance(body, QLabel):
                body.setText(text)
                return
            if isinstance(body, (QTextEdit, QPlainTextEdit)):
                body.setPlainText(text)
                return

        if prop == "reasoning":
            reasoning_body = getattr(widget, "_message_reasoning_body_widget", None)
            reasoning = _literal(value)
            if hasattr(reasoning_body, "set_markdown"):
                reasoning_body.set_markdown(reasoning)
                return
            if reasoning:
                self._add_reasoning_block(widget, reasoning)
                return

        super().update_widget_property(widget, prop, value)

    @staticmethod
    def _add_reasoning_block(widget: QWidget, reasoning: str) -> None:
        bubble_layout = getattr(widget, "_message_bubble_layout", None)
        if not isinstance(bubble_layout, QVBoxLayout):
            return
        reasoning_wrap = QFrame()
        reasoning_layout = QVBoxLayout(reasoning_wrap)
        reasoning_layout.setContentsMargins(0, 2, 0, 0)
        reasoning_layout.setSpacing(4)

        reasoning_toggle = QToolButton()
        reasoning_toggle.setText("Reasoning")
        reasoning_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        reasoning_toggle.setCheckable(True)
        reasoning_toggle.setChecked(False)
        reasoning_toggle.setArrowType(Qt.ArrowType.RightArrow)
        reasoning_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        reasoning_toggle.setProperty("ui_role", "advanced_message_action")
        reasoning_wrap.setProperty("ui_role", "advanced_reasoning_wrap")

        reasoning_body = _AutoResizeMarkdownBrowser()
        reasoning_body.set_markdown(reasoning)
        reasoning_body.setStyleSheet(
            "color: #a1a1aa; background: transparent; border: none;"
        )
        reasoning_body.setVisible(False)

        reasoning_toggle.toggled.connect(
            lambda visible, body=reasoning_body: body.setVisible(bool(visible))
        )
        reasoning_toggle.toggled.connect(
            lambda visible, toggle=reasoning_toggle: toggle.setArrowType(
                Qt.ArrowType.DownArrow if bool(visible) else Qt.ArrowType.RightArrow
            )
        )
        reasoning_layout.addWidget(reasoning_toggle, 0, Qt.AlignmentFlag.AlignLeft)
        reasoning_layout.addWidget(reasoning_body)
        bubble_layout.addWidget(reasoning_wrap)
        widget._message_reasoning_body_widget = reasoning_body  # type: ignore[attr-defined]
