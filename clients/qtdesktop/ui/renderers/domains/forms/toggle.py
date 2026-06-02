from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt, QSize, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ...base import (
    BaseRenderer,
    confirm_action,
    emit_action_spec,
    publish_bound_value,
)
from ...icon import get_icon


class _SwitchWidget(QAbstractButton):
    """Custom desktop switch with explicit track/thumb rendering."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(40, 22)
        self._hovered = False
        self._invalid = False
        self._icon_on = ""
        self._icon_off = ""

    def sizeHint(self) -> QSize:  # pragma: no cover - trivial
        return QSize(40, 22)

    def minimumSizeHint(self) -> QSize:  # pragma: no cover - trivial
        return QSize(40, 22)

    def set_invalid(self, invalid: bool) -> None:
        if self._invalid == bool(invalid):
            return
        self._invalid = bool(invalid)
        self.update()

    def set_icons(self, icon_on: str, icon_off: str) -> None:
        self._icon_on = str(icon_on or "").strip()
        self._icon_off = str(icon_off or "").strip()
        self.update()

    def enterEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[override]
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[override]
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        rect = QRectF(0.5, 0.5, self.width() - 1.0, self.height() - 1.0)
        radius = rect.height() / 2.0
        checked = self.isChecked()

        track_off = QColor("#27272A")
        track_off_hover = QColor("#3F3F46")
        track_on = QColor("#3B82F6")
        track_on_hover = QColor("#2563EB")
        border_off = QColor("#3F3F46")
        border_off_hover = QColor("#60A5FA")
        border_on = QColor("#3B82F6")
        border_on_hover = QColor("#2563EB")

        if checked:
            track = track_on_hover if self._hovered else track_on
            border = border_on_hover if self._hovered else border_on
        else:
            track = track_off_hover if self._hovered else track_off
            border = border_off_hover if self._hovered else border_off
        if self._invalid and not checked:
            border = QColor("#DC2626")

        if not self.isEnabled():
            track.setAlpha(130)
            border.setAlpha(130)

        painter.setPen(QPen(border, 1.0))
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)

        thumb_d = rect.height() - 6.0
        thumb_y = rect.top() + (rect.height() - thumb_d) / 2.0
        thumb_x_off = rect.left() + 3.0
        thumb_x_on = rect.right() - thumb_d - 3.0
        thumb_x = thumb_x_on if checked else thumb_x_off
        thumb_rect = QRectF(thumb_x, thumb_y, thumb_d, thumb_d)

        thumb_color = QColor("#FFFFFF")
        if not self.isEnabled():
            thumb_color.setAlpha(180)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(thumb_color)
        painter.drawEllipse(thumb_rect)

        icon_name = self._icon_on if checked else self._icon_off
        if icon_name:
            icon_px = max(10, int(thumb_d - 4.0))
            icon_color = "#0F172A" if checked else "#334155"
            icon = get_icon(icon_name, color=icon_color, size=icon_px)
            pixmap = icon.pixmap(icon_px, icon_px)
            if not pixmap.isNull():
                icon_x = int(thumb_rect.center().x() - pixmap.width() / 2.0)
                icon_y = int(thumb_rect.center().y() - pixmap.height() / 2.0)
                painter.drawPixmap(icon_x, icon_y, pixmap)


class ToggleRenderer(BaseRenderer):
    component_type = "Toggle"

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "label": self.PROPERTY,
            "checked": self.PROPERTY,
            "error": self.PROPERTY,
            "margin_left": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        container = QWidget()
        container.setObjectName(comp_id)
        container.setProperty("is_input", True)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        row = QWidget()
        row.setObjectName(f"{comp_id}__row")
        row_layout = QHBoxLayout(row)
        margin_left = max(0, int(props.get("margin_left", 0) or 0))
        row_layout.setContentsMargins(margin_left, 0, 0, 0)
        row_layout.setSpacing(10)
        container.setProperty("margin_left", margin_left)

        switch = _SwitchWidget()
        switch.setObjectName(f"{comp_id}__input")
        switch.setProperty("is_input", True)
        switch.setProperty("ui_role", "advanced_switch_input")
        switch.setProperty("error", False)
        switch.setProperty("invalid", "false")
        switch.setChecked(bool(props.get("checked", False)))
        icon_on = str(props.get("icon_on") or "")
        icon_off = str(props.get("icon_off") or "")
        switch.set_icons(icon_on, icon_off)
        container.setProperty("icon_on", icon_on)
        container.setProperty("icon_off", icon_off)
        row_layout.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)

        label = QLabel(self._literal_text(props.get("label")))
        label.setProperty("ui_role", "advanced_switch_label")
        row_layout.addWidget(label, 1, Qt.AlignmentFlag.AlignVCenter)
        row_layout.addStretch()
        layout.addWidget(row)

        err_label = QLabel()
        err_label.setProperty("ui_role", "form_error_label")
        err_label.setWordWrap(True)
        err_label.hide()
        layout.addWidget(err_label)

        container.setProperty("checked", switch.isChecked())
        container.setProperty("value", switch.isChecked())
        container.setProperty("_confirmed_checked", switch.isChecked())
        publish_bound_value(app_instance, switch, comp_id, switch.isChecked(), prop_name="checked")

        def _on_state_changed(checked: bool) -> None:
            action_val = props.get("action")
            confirm = action_val.get("confirm") if isinstance(action_val, dict) else None
            previous = bool(container.property("_confirmed_checked"))
            if action_val and not confirm_action(app_instance, confirm):
                switch.blockSignals(True)
                switch.setChecked(previous)
                switch.blockSignals(False)
                container.setProperty("checked", previous)
                container.setProperty("value", previous)
                return

            container.setProperty("checked", checked)
            container.setProperty("value", checked)
            container.setProperty("_confirmed_checked", checked)
            publish_bound_value(app_instance, switch, comp_id, checked, prop_name="checked")

            params = props.get("params", {})
            if isinstance(action_val, str):
                action_spec: Any = action_val
            elif isinstance(action_val, dict):
                action_spec = dict(action_val)
                action_spec.pop("confirm", None)
                if isinstance(params, dict):
                    action_context = action_spec.get("context", {})
                    action_spec["context"] = {
                        **(action_context if isinstance(action_context, dict) else {}),
                        **params,
                    }
            else:
                return

            emit_action_spec(
                app_instance,
                action_spec,
                {comp_id: checked, "checked": checked, "value": checked},
                surface_id,
                comp_id,
            )

        switch.toggled.connect(_on_state_changed)

        if props.get("error"):
            self.update_widget_property(container, "error", props["error"])

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any):
        switch = widget.findChild(_SwitchWidget, f"{widget.objectName()}__input")
        if switch is None:
            if isinstance(widget, _SwitchWidget):
                switch = widget
            else:
                return super().update_widget_property(widget, prop, value)

        if prop == "label":
            for child in widget.findChildren(QLabel):
                if child.property("ui_role") == "advanced_switch_label":
                    child.setText(self._literal_text(value))
                    return
            return

        if prop == "checked":
            checked = bool(value)
            switch.blockSignals(True)
            switch.setChecked(checked)
            switch.blockSignals(False)
            widget.setProperty("checked", checked)
            widget.setProperty("value", checked)
            widget.setProperty("_confirmed_checked", checked)
            return

        if prop in {"icon_on", "icon_off"}:
            switch.set_icons(
                str(widget.property("icon_on") or "")
                if prop != "icon_on"
                else str(value or ""),
                str(widget.property("icon_off") or "")
                if prop != "icon_off"
                else str(value or ""),
            )
            widget.setProperty(prop, str(value or ""))
            return

        if prop == "margin_left":
            margin_left = max(0, int(value or 0))
            row_widget = widget.findChild(QWidget, f"{widget.objectName()}__row")
            if row_widget is not None:
                row_layout = row_widget.layout()
                if isinstance(row_layout, QHBoxLayout):
                    row_layout.setContentsMargins(margin_left, 0, 0, 0)
            widget.setProperty("margin_left", margin_left)
            return

        if prop == "error":
            has_error = bool(value)
            switch.setProperty("error", has_error)
            switch.setProperty("invalid", "true" if has_error else "false")
            switch.set_invalid(has_error)

            for child in widget.findChildren(QLabel):
                role = child.property("ui_role")
                if role == "advanced_switch_label":
                    child.setProperty("invalid", "true" if has_error else "false")
                    child.style().unpolish(child)
                    child.style().polish(child)
                if role == "form_error_label":
                    if has_error:
                        child.setText(self._literal_text(value))
                        child.show()
                    else:
                        child.hide()

            switch.style().unpolish(switch)
            switch.style().polish(switch)
            return

        if prop == "params":
            widget.setProperty("_action_context", value if isinstance(value, dict) else {})
            return

        if prop == "action":
            params = widget.property("_action_context") or {}
            if isinstance(value, str):
                action_name = value.strip()
                action_ctx = params if isinstance(params, dict) else {}
            else:
                action = value if isinstance(value, dict) else {}
                action_name = str(action.get("name", "")).strip()
                action_ctx = action.get("context", {})
                if isinstance(params, dict):
                    action_ctx.update(params)
            if not isinstance(action_ctx, dict):
                action_ctx = {}
            widget.setProperty("_action_name", action_name)
            widget.setProperty("_action_context", action_ctx)
            return

        super().update_widget_property(widget, prop, value)
