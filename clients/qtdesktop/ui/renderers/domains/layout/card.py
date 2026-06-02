from __future__ import annotations
import os
from typing import Any, Dict
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from ...base import BaseRenderer, emit_action_spec
from ...base_visibility import spec_is_visible
from ...icon import get_icon
from ..actions.button import (
    button_icon_colors,
    normalize_button_appearance,
    normalize_button_variant,
)
from .....utils.paths import resolve_resource
from .common import apply_children_collection_patch


class _CardFrame(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self._background_pixmap = QPixmap()

    def set_background_image(self, path: str) -> None:
        pixmap = QPixmap(path)
        self._background_pixmap = pixmap if not pixmap.isNull() else QPixmap()
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self._background_pixmap.isNull():
            super().paintEvent(event)
            return

        card_rect = self.rect()
        target = card_rect
        footer = getattr(self, "_card_footer", None)
        if footer is not None:
            footer_top = footer.geometry().top()
            if footer_top > 0:
                target = card_rect.adjusted(0, 0, 0, -(card_rect.height() - footer_top))

        scaled = self._background_pixmap.scaled(
            target.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (scaled.width() - target.width()) // 2
        y = (scaled.height() - target.height()) // 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect.adjusted(0, 0, -1, -1), 16, 16)
        painter.fillPath(card_path, QColor("#111113"))
        painter.setClipPath(card_path)
        painter.drawPixmap(target, scaled.copy(x, y, target.width(), target.height()))
        image_path = QPainterPath()
        image_path.addRect(target)
        painter.fillPath(image_path, QColor(17, 17, 19, 96))
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#27272a"), 1))
        painter.drawPath(card_path)


class CardRenderer(BaseRenderer):
    component_type = "Card"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "children": self.COMPONENT,
            "variant": self.PROPERTY,
            "background_image": self.COMPONENT,
            "padding": self.PROPERTY,
            "max_width": self.PROPERTY,
            "maxWidth": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        variant = props.get("variant", "elevated")
        bg_image = props.get("background_image")
        item_actions = props.get("itemActions") or []
        item_data = props.get("data") or {}

        # Outer wrapper — this is what the engine returns and attaches to the parent.
        widget = _CardFrame()
        widget.setObjectName(comp_id)
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        widget.setProperty("type", "card")
        widget.setProperty("variant", variant)
        widget.setProperty("ui_role", "card")
        max_width = _positive_int(props.get("max_width") or props.get("maxWidth"))
        if max_width:
            widget.setMaximumWidth(max_width)
            widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)

        # Outer layout has zero margins so the footer can span full card width.
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        widget.setLayout(outer_layout)

        if bg_image:
            widget.setProperty("has_image", True)
            img_path = resolve_resource(bg_image)
            if os.path.exists(img_path):
                widget.set_background_image(img_path)

        widget.style().unpolish(widget)
        widget.style().polish(widget)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]

        # Inner content frame — children go here via add_child_to_widget().
        # Carries the card padding so the footer can be flush with the edges.
        raw_padding = props.get("padding")
        content_padding = [16, 16, 16, 16]
        if (
            isinstance(raw_padding, (list, tuple))
            and len(raw_padding) == 4
            and all(isinstance(v, (int, float)) for v in raw_padding)
        ):
            content_padding = [int(v) for v in raw_padding]

        content = QFrame()
        content.setObjectName(f"{comp_id}_content")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(*content_padding)
        content_layout.setSpacing(12)
        content.setLayout(content_layout)
        outer_layout.addWidget(content, stretch=1)
        widget._card_content = content  # type: ignore[attr-defined]

        if item_actions:
            footer = QFrame()
            footer.setObjectName(f"{comp_id}_footer")
            footer.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
            footer.setProperty("ui_role", "card_footer")
            widget._card_footer = footer  # type: ignore[attr-defined]
            footer_layout = QHBoxLayout()
            footer_layout.setContentsMargins(16, 8, 16, 8)
            footer_layout.setSpacing(6)
            footer.setLayout(footer_layout)

            visible_actions = [
                action_def
                for action_def in item_actions
                if isinstance(action_def, dict)
                and spec_is_visible(action_def, app_instance, item_data)
            ]

            for action_def in visible_actions:
                label = str(action_def.get("label", "") or "")
                icon_name = action_def.get("icon")
                btn_variant = str(action_def.get("variant", "default") or "default")
                btn_mode = str(action_def.get("mode", "solid") or "solid")
                variant = normalize_button_variant(btn_variant)
                appearance = normalize_button_appearance(btn_mode)
                action_spec = action_def.get("action", {})
                merged_ctx = {**action_spec.get("context", {}), **item_data}

                btn = QPushButton()
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.setProperty("ui_role", "card_footer_btn")
                btn.setProperty("variant", variant)
                btn.setProperty("mode", btn_mode)
                btn.setProperty("appearance", appearance)

                if label:
                    btn.setText(label)
                if icon_name:
                    icon_color, _ = button_icon_colors(
                        variant=variant,
                        appearance=appearance,
                        shape="default",
                        active=False,
                        app_instance=app_instance,
                    )
                    btn.setIcon(get_icon(icon_name, color=icon_color))
                    btn.setIconSize(QSize(16, 16))

                btn.clicked.connect(
                    lambda _=False, spec=action_spec, ctx=merged_ctx: emit_action_spec(
                        app_instance, spec, ctx, surface_id, comp_id
                    )
                )
                footer_layout.addWidget(btn, stretch=1)

            if visible_actions:
                outer_layout.addWidget(footer)

        return widget

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop in {"max_width", "maxWidth"}:
            max_width = _positive_int(value)
            if max_width:
                widget.setMaximumWidth(max_width)
                widget.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
            else:
                widget.setMaximumWidth(16777215)
                widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            widget.updateGeometry()
            return
        super().update_widget_property(widget, prop, value)

    def add_child_to_widget(self, widget: QWidget, child_widget: QWidget) -> None:
        """Route children into the inner content frame, keeping footer at the bottom."""
        content = getattr(widget, "_card_content", None)
        target_layout = content.layout() if content is not None else widget.layout()
        if target_layout:
            target_layout.addWidget(child_widget)

    def apply_collection_patch(self, widget, prop, action, value) -> bool:
        return apply_children_collection_patch(widget, prop, action, value)


def _positive_int(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return number if number > 0 else 0
