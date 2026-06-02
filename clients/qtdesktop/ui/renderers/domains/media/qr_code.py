from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

from ...base import BaseRenderer

try:
    import qrcode
    from PIL.ImageQt import ImageQt

    QR_AVAILABLE = True
except Exception:
    QR_AVAILABLE = False


class QRCodeRenderer(BaseRenderer):
    component_type = "QRCode"

    @staticmethod
    def _coerce_initial_content(value: Any, default: Any = "") -> str:
        if value is None:
            value = default
        if value is None:
            return ""
        if isinstance(value, (str, int, float, bool)):
            return str(value)
        if isinstance(default, (str, int, float, bool)):
            return str(default)
        return ""

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "content": self.PROPERTY,
            "size": self.PROPERTY,
            "border": self.PROPERTY,
            "fill_color": self.PROPERTY,
            "back_color": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        widget = QLabel()
        widget.setObjectName(comp_id)
        widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        widget._surface_id = surface_id  # type: ignore[attr-defined]
        widget._app_instance = app_instance  # type: ignore[attr-defined]
        widget._comp_id = comp_id  # type: ignore[attr-defined]
        widget._qr_props = dict(props)  # type: ignore[attr-defined]
        self._build(widget)
        return widget

    def update_widget_property(self, widget, prop: str, value: Any) -> None:
        if prop in {"content", "size", "border", "fill_color", "back_color"}:
            props = dict(getattr(widget, "_qr_props", {}))
            props[prop] = value
            widget._qr_props = props  # type: ignore[attr-defined]
            self._build(widget)
            return
        super().update_widget_property(widget, prop, value)

    def _build(self, widget: QLabel) -> None:
        props = dict(getattr(widget, "_qr_props", {}))
        value = props.get("content", {})
        if isinstance(value, dict):
            if "literalString" in value:
                text = str(value.get("literalString", ""))
            else:
                bindings = getattr(getattr(widget, "_app_instance", None), "bindings", None)
                surface_id = getattr(widget, "_surface_id", None)
                resolved = (
                    bindings.resolve_value_for_surface(value, surface_id)
                    if bindings is not None
                    else None
                )
                text = self._coerce_initial_content(
                    resolved,
                    value.get("default", ""),
                )
        else:
            text = str(value or "")
        size = int(props.get("size", 220) or 220)
        border = int(props.get("border", 4) or 4)
        fill_color = str(props.get("fill_color", "#111111") or "#111111")
        back_color = str(props.get("back_color", "#ffffff") or "#ffffff")

        if not text:
            widget.setText("[QR: empty value]")
            widget.setPixmap(QPixmap())
            return
        if not QR_AVAILABLE:
            widget.setText("[QR unavailable: install qrcode]")
            widget.setPixmap(QPixmap())
            return

        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=max(0, border),
        )
        qr.add_data(text)
        qr.make(fit=True)
        image = qr.make_image(fill_color=fill_color, back_color=back_color).convert(
            "RGBA"
        )

        image = image.resize((max(40, size), max(40, size)))
        qimage = ImageQt(image)
        pixmap = QPixmap.fromImage(qimage)
        widget.setText("")
        widget.setPixmap(pixmap)
        widget.setFixedSize(pixmap.size())
