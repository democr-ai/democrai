from __future__ import annotations

from typing import Any, Dict

from PySide6.QtWidgets import QVBoxLayout, QWidget

from ....qss_sanitizer import sanitize_qss_style
from ...base import BaseRenderer
from .common import make_code_widget, make_md_widget, split_markdown


class MarkdownRenderer(BaseRenderer):
    component_type = "Markdown"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "text": self.PROPERTY,
            "content_style": self.PROPERTY,
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
                bindings = getattr(app_instance, "bindings", None)
                resolved = (
                    bindings.resolve_value_for_surface(text_prop, surface_id)
                    if bindings is not None
                    else None
                )
                text = resolved if resolved is not None else text_prop.get("default", "")
        else:
            text = text_prop
        text = "" if text is None else str(text)

        widget = QWidget()
        widget.setObjectName(comp_id)
        widget.setProperty("_comp_type", "Markdown")
        widget.setProperty("ui_role", "markdown_container")
        widget._current_text = text  # type: ignore
        widget._content_style = str(
            props.get("content_style")
            or props.get("style")
            or ""
        )  # type: ignore[attr-defined]

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        def populate(txt):
            while layout.count() > 1:
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            for seg in split_markdown(txt):
                if seg.kind == "md":
                    child = make_md_widget(seg.text)
                else:
                    child = make_code_widget(seg.text, seg.lang)
                content_style = str(getattr(widget, "_content_style", "") or "")
                if content_style:
                    child.setStyleSheet(sanitize_qss_style(content_style))
                layout.insertWidget(layout.count() - 1, child)

        def set_text(new_text):
            widget._current_text = new_text
            populate(new_text)

        widget.setText = set_text  # type: ignore
        widget.rebuildMarkdown = populate  # type: ignore[attr-defined]
        layout.addStretch(1)
        populate(text)
        return widget

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "text":
            text = "" if value is None else str(value)
            set_text = getattr(widget, "setText", None)
            if callable(set_text):
                set_text(text)
            return
        if prop == "content_style":
            widget._content_style = "" if value is None else str(value)  # type: ignore[attr-defined]
            rebuild = getattr(widget, "rebuildMarkdown", None)
            current_text = getattr(widget, "_current_text", "")
            if callable(rebuild):
                rebuild(current_text)
            return
        super().update_widget_property(widget, prop, value)
