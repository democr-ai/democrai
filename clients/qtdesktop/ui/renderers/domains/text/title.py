from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import QWidget, QLabel, QSizePolicy

from PySide6.QtCore import Qt
from ...base import BaseRenderer
from .common import escape_qt_mnemonic


class TitleRenderer(BaseRenderer):
    component_type = "Title"

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

    @staticmethod
    def _coerce_initial_level(value: Any, default: Any = 3) -> int:
        if value is None:
            value = default
        try:
            level = int(value)
        except (TypeError, ValueError):
            try:
                level = int(default)
            except (TypeError, ValueError):
                level = 3
        if level > 5 or level < 1:
            return 3
        return level

    @staticmethod
    def _coerce_initial_align(value: Any, default: Any = "left") -> str:
        if value is None:
            value = default
        align = str(value or default or "left").strip().lower()
        if align not in {"left", "center", "right"}:
            return "left"
        return align

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "text": self.PROPERTY,
            "align": self.PROPERTY,
            "level": self.PROPERTY,
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
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        if props.get("selectable", False):
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        align_prop = props.get("align", "left")
        if isinstance(align_prop, dict):
            bindings = getattr(app_instance, "bindings", None)
            resolved = (
                bindings.resolve_value_for_surface(align_prop, surface_id)
                if bindings is not None
                else None
            )
            align = self._coerce_initial_align(
                resolved,
                align_prop.get("default", "left"),
            )
        else:
            align = self._coerce_initial_align(align_prop, "left")
        if align == "center":
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        elif align == "right":
            widget.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            widget.setAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )

        if props.get("selectable", False):
            widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        level_prop = props.get("level", 3)
        if isinstance(level_prop, dict):
            bindings = getattr(app_instance, "bindings", None)
            resolved = (
                bindings.resolve_value_for_surface(level_prop, surface_id)
                if bindings is not None
                else None
            )
            level = self._coerce_initial_level(
                resolved,
                level_prop.get("default", 3),
            )
        else:
            level = self._coerce_initial_level(level_prop, 3)
        widget.setProperty("title", str(level))
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
        if prop == "level":
            try:
                level = int(value)
            except (TypeError, ValueError):
                level = 3
            if level > 5 or level < 1:
                level = 3
            widget.setProperty("title", str(level))
            widget.style().unpolish(widget)
            widget.style().polish(widget)
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
