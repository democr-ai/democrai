from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from ....qss_sanitizer import qss_for_widget_style
from ...base import BaseRenderer
from .common import escape_qt_mnemonic


class TextRenderer(BaseRenderer):
    component_type = "Text"

    @staticmethod
    def _coerce_initial_text(value: Any, default: Any = "") -> str:
        if value is None:
            value = default
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        # Non-scalar values (dict/list/...) are not valid text payloads.
        if isinstance(default, (str, int, float, bool)):
            return str(default)
        return ""

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "text": self.PROPERTY,
            "align": self.PROPERTY,
            "selectable": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        text_prop = props.get("text", {})
        if isinstance(text_prop, dict):
            if "literalString" in text_prop:
                text = text_prop.get("literalString", "")
            else:
                # Support bound specs (store/action/literal) on first render.
                bindings = getattr(app_instance, "bindings", None)
                resolved = (
                    bindings.resolve_value_for_surface(text_prop, surface_id)
                    if bindings is not None
                    else None
                )
                text = self._coerce_initial_text(
                    resolved,
                    text_prop.get("default", ""),
                )
        else:
            text = str(text_prop)

        widget = QLabel(escape_qt_mnemonic(text))
        widget.setObjectName(comp_id)
        widget.setWordWrap(True)

        if props.get("selectable", False):
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        align = props.get("align", "left")
        if align == "center":
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif align == "right":
            widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            widget.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

        if props.get("style"):
            widget.setStyleSheet(qss_for_widget_style(props.get("style"), comp_id))

        return widget

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "text":
            widget.setText(escape_qt_mnemonic(self._literal_text(value)))
            return
        if prop == "selectable":
            flags = (
                Qt.TextInteractionFlag.TextSelectableByMouse
                if bool(value)
                else Qt.TextInteractionFlag.NoTextInteraction
            )
            widget.setTextInteractionFlags(flags)
            return
        if prop == "align":
            align = str(value or "left")
            if align == "center":
                widget.setAlignment(
                    Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
                )
            elif align == "right":
                widget.setAlignment(
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop
                )
            else:
                widget.setAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                )
            return
        super().update_widget_property(widget, prop, value)
