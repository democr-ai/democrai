from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedLayout,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QImage
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtCore import QSize, Qt, QObject, QEvent, QRect, QTimer
from typing import Dict, Any, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import base64
from concurrent.futures import ThreadPoolExecutor
import re
from shiboken6 import isValid as qt_is_valid
from ...base import BaseRenderer, emit_action
from ...icon import get_icon, get_icon_gliph
from .common import (
    localize_runtime_media_source,
    resolve_runtime_media_source,
)
from .http import fetch_media_bytes
from ....i18n import get_i18n
from ....theme.tokens import button_icon_colors as resolve_button_icon_colors
from ....theme.tokens import current_theme
from ....theme.tokens import theme_token
from .....utils.paths import resolve_resource
import os
import time

_IMAGE_LOAD_EXECUTOR = ThreadPoolExecutor(
    max_workers=4,
    thread_name_prefix="democrai-qt-image",
)

_BUTTON_VARIANT_ALIASES = {
    "primary": "default",
    "danger": "destructive",
    "info": "secondary",
    "warning": "warning",
    "success": "success",
}

_BUTTON_SIZE_ALIASES = {
    "small": "sm",
    "normal": "default",
    "large": "lg",
}


_WHITE_SVG_COLOR_RE = re.compile(
    r"""(?i)(fill|stroke)\s*=\s*(['"])\s*(#fff(?:fff)?|white)\s*\2"""
)


def normalize_button_variant(variant: str) -> str:
    return _BUTTON_VARIANT_ALIASES.get(variant, variant)


def normalize_button_size(size: str) -> str:
    return _BUTTON_SIZE_ALIASES.get(size, size)


def normalize_button_appearance(mode: str) -> str:
    return "default" if mode == "solid" else mode


def button_icon_colors(
    variant: str,
    appearance: str,
    shape: str,
    active: bool,
    *,
    app_instance: Any | None = None,
) -> tuple[str, str]:
    return resolve_button_icon_colors(
        variant=normalize_button_variant(variant),
        appearance=appearance,
        shape=shape,
        active=active,
        profile="contrast",
        app_instance=app_instance,
    )


def _escape_qt_mnemonic(text: Any) -> str:
    raw = "" if text is None else str(text)
    return raw.replace("&", "&&")


def _tint_logo_svg_if_needed(
    svg_bytes: bytes, comp_id: str, source_hint: str = ""
) -> bytes:
    source_name = os.path.basename(urlparse(str(source_hint or "")).path).lower()
    is_brand_logo = str(comp_id or "") == "logo_img" or source_name in {
        "logo.svg",
        "logo_full.svg",
    }
    if not is_brand_logo:
        return svg_bytes
    if str(comp_id or "") == "logo_img":
        return svg_bytes
    if current_theme() != "light":
        return svg_bytes
    try:
        svg_text = svg_bytes.decode("utf-8")
    except UnicodeDecodeError:
        return svg_bytes
    primary = theme_token("color.info", theme="light") or "#2563EB"
    tinted = _WHITE_SVG_COLOR_RE.sub(
        lambda m: f'{m.group(1)}={m.group(2)}{primary}{m.group(2)}', svg_text
    )
    return tinted.encode("utf-8")


def _normalize_image_source(url: str, app_instance: Any) -> str:
    return resolve_runtime_media_source(str(url or ""), app_instance)


def _with_proxy_resize_params(source: str, width: int, height: int) -> str:
    parsed = urlparse(str(source or ""))
    is_proxy = source.startswith("/media/proxy") or (
        parsed.scheme in {"http", "https"} and parsed.path == "/media/proxy"
    )
    if not is_proxy:
        return source

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if int(width or 0) > 0:
        params["width"] = str(int(width))
    if int(height or 0) > 0:
        params["height"] = str(int(height))
    query = urlencode(params)
    if source.startswith("/media/proxy"):
        return urlunparse(("", "", parsed.path, "", query, ""))
    return urlunparse(
        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, query, parsed.fragment)
    )


def _load_internal_media_bytes(url_path: str, app_instance: Any) -> bytes:
    return fetch_media_bytes(app_instance, url_path, timeout=15.0)


def _decode_data_image_url(raw: str) -> bytes:
    source = str(raw or "").strip()
    if not source.startswith("data:image/"):
        return b""
    marker = ";base64,"
    idx = source.find(marker)
    if idx < 0:
        return b""
    encoded = source[idx + len(marker) :].strip()
    if not encoded:
        return b""
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception:
        return b""


def _load_image_payload(
    *,
    normalized_url: str,
    resolved_url: str,
    app_instance: Any,
    w: int,
    h: int,
    fit_mode: str,
) -> dict[str, Any]:
    def _prepare_image(image: QImage) -> dict[str, Any]:
        if str(fit_mode or "").strip().lower() != "container":
            image = image.scaled(
                int(w or 45),
                int(h or 45),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        return {"kind": "image", "image": image}

    internal_payload = _load_internal_media_bytes(normalized_url, app_instance)
    if not internal_payload:
        internal_payload = _decode_data_image_url(normalized_url)
    if internal_payload:
        image = QImage()
        if image.loadFromData(internal_payload):
            return _prepare_image(image)
        return {"kind": "error"}

    if resolved_url.lower().endswith(".svg"):
        try:
            with open(resolved_url, "rb") as f:
                return {"kind": "svg", "svg_bytes": f.read(), "source": resolved_url}
        except OSError:
            return {"kind": "error"}

    image = QImage(resolved_url)
    if image.isNull():
        return {"kind": "error"}
    return _prepare_image(image)


class IconSwapOnHover(QObject):
    def __init__(self, btn: QPushButton, icon_normal, icon_hover):
        super().__init__(btn)
        self.btn = btn
        self.icon_normal = icon_normal
        self.icon_hover = icon_hover

        btn.setAttribute(Qt.WA_Hover, True)
        btn.setMouseTracking(True)
        btn.installEventFilter(self)
        self.apply_current()

    def set_icons(self, icon_normal, icon_hover):
        self.icon_normal = icon_normal
        self.icon_hover = icon_hover
        self.apply_current()

    def apply_current(self):
        # se il mouse è sopra, mostra subito hover
        self.btn.setIcon(self.icon_hover if self.btn.underMouse() else self.icon_normal)

    def eventFilter(self, obj, ev):
        if obj is self.btn:
            if ev.type() in (QEvent.Enter, QEvent.HoverEnter):
                obj.setIcon(self.icon_hover)
            elif ev.type() in (QEvent.Leave, QEvent.HoverLeave):
                obj.setIcon(self.icon_normal)
        return False


class _LazyImageLoader(QObject):
    def __init__(self, widget: QWidget, load_callback):
        super().__init__(widget)
        self.widget = widget
        self.load_callback = load_callback
        self._loaded = False
        self._scroll_area = self._find_scroll_area(widget)

        widget.installEventFilter(self)
        if self._scroll_area is not None:
            viewport = self._scroll_area.viewport()
            if viewport is not None:
                viewport.installEventFilter(self)
            hbar = self._scroll_area.horizontalScrollBar()
            vbar = self._scroll_area.verticalScrollBar()
            if hbar is not None:
                hbar.valueChanged.connect(lambda *_: self.check_and_load())
            if vbar is not None:
                vbar.valueChanged.connect(lambda *_: self.check_and_load())
        QTimer.singleShot(0, self.check_and_load)

    @staticmethod
    def _find_scroll_area(widget: QWidget):
        current = widget.parentWidget()
        while current is not None:
            if hasattr(current, "viewport") and callable(getattr(current, "viewport")):
                return current
            current = current.parentWidget()
        return None

    def eventFilter(self, obj, event):
        if event.type() in {
            QEvent.Type.Show,
            QEvent.Type.Resize,
            QEvent.Type.Move,
        }:
            QTimer.singleShot(0, self.check_and_load)
        return False

    def check_and_load(self):
        if self._loaded or self.widget is None or not self.widget.isVisible():
            return
        if self._is_in_viewport():
            self._loaded = True
            self.load_callback()

    def _is_in_viewport(self) -> bool:
        if self._scroll_area is None:
            return True
        viewport = self._scroll_area.viewport()
        if viewport is None or not viewport.isVisible():
            return False
        top_left = self.widget.mapTo(viewport, self.widget.rect().topLeft())
        rect = QRect(top_left, self.widget.rect().size())
        return viewport.rect().intersects(rect)




class _ImageWidget(QFrame):
    """QFrame container that shows either the image or a blocked-URL placeholder."""

    def __init__(self, w: int, h: int, fit_mode: str = ""):
        super().__init__()
        self._fit_mode = str(fit_mode or "").strip().lower()
        self._base_w = int(w or 45)
        self._base_h = int(h or 45)
        self._source_pixmap: QPixmap | None = None
        self._blocked_message = "URL blocked"
        self.setFrameShape(QFrame.Shape.NoFrame)
        if self._fit_mode == "container":
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
            self.setMinimumHeight(80)
        else:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setFixedSize(self._base_w, self._base_h)

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.setSpacing(0)

        # Page 0 — image
        self.img_label = QLabel()
        self.img_label.setProperty("ui_role", "media_image")
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if self._fit_mode == "container":
            self.img_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
        self._stack.addWidget(self.img_label)

        # Page 1 — placeholder shown when URL is blocked
        ph = QWidget()
        ph.setProperty("ui_role", "media_placeholder")
        ph_layout = QVBoxLayout(ph)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.setSpacing(8)
        ph_layout.setContentsMargins(8, 8, 8, 8)

        self._status_label = QLabel(self._blocked_message)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setProperty("ui_role", "media_status")
        self._status_label.setWordWrap(True)

        self._reload_btn = QPushButton("Reload")
        icon = get_icon(
            "ric.refresh-line",
            theme_token("text.primary"),
            16,
        )
        if icon:
            self._reload_btn.setIcon(icon)
        self._reload_btn.setIconSize(QSize(16, 16))
        self._reload_btn.setProperty("ui_role", "media_control_btn")
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.setToolTip("Reload URL")

        ph_layout.addWidget(self._status_label)
        ph_layout.addWidget(self._reload_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._stack.addWidget(ph)

        self._stack.setCurrentIndex(0)

    def set_i18n(self, app_instance: Any) -> None:
        messages = get_i18n(app_instance)
        self._blocked_message = messages["blocked_url"]
        self._status_label.setText(self._blocked_message)
        self._reload_btn.setText(messages["reload"])
        self._reload_btn.setToolTip(messages["reload_url"])

    def show_placeholder(self, message: str = "") -> None:
        self._status_label.setText(str(message or self._blocked_message))
        self._stack.setCurrentIndex(1)

    def show_image(self) -> None:
        self._stack.setCurrentIndex(0)

    def set_source_pixmap(self, pixmap: QPixmap, w: int, h: int) -> None:
        self._source_pixmap = pixmap
        self._base_w = int(w or self._base_w or 45)
        self._base_h = int(h or self._base_h or 45)
        self._apply_pixmap()

    def _apply_pixmap(self) -> None:
        if self._source_pixmap is None:
            self.img_label.setPixmap(QPixmap())
            return
        target_w = self._base_w
        target_h = self._base_h
        if self._fit_mode == "container":
            current_w = int(self.width() or 0)
            current_h = int(self.height() or 0)
            parent = self.parentWidget()
            if current_w <= 0 and parent is not None:
                current_w = int(parent.width() or 0)
            if current_h <= 0 and parent is not None:
                current_h = int(parent.height() or 0)
            target_w = max(120, current_w) if current_w > 0 else 120
            target_h = max(80, current_h) if current_h > 0 else 80
        scaled = self._source_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.img_label.setText("")
        self.img_label.setPixmap(scaled)

    def resizeEvent(self, event):  # type: ignore[override]
        super().resizeEvent(event)
        if self._fit_mode == "container" and self._source_pixmap is not None:
            self._apply_pixmap()


class ImageRenderer(BaseRenderer):
    component_type = "Image"

    @staticmethod
    def _resolve_initial_bound_value(
        value: Any,
        app_instance: Any,
        surface_id: str,
        default: Any,
    ) -> Any:
        if isinstance(value, dict):
            if "literalString" in value:
                return value.get("literalString", default)
            bindings = getattr(app_instance, "bindings", None)
            if bindings is not None:
                resolved = bindings.resolve_value_for_surface(value, surface_id)
                if resolved is not None:
                    return resolved
            return value.get("default", default)
        return value if value is not None else default

    def binding_strategies(self) -> Dict[str, str]:
        return {
            **super().binding_strategies(),
            "url": self.PROPERTY,
            "alt": self.PROPERTY,
            "width": self.PROPERTY,
            "height": self.PROPERTY,
            "fit": self.PROPERTY,
            "lazy": self.PROPERTY,
        }

    def render(
        self,
        props: Dict[str, Any],
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        alt = str(
            self._resolve_initial_bound_value(
                props.get("alt"),
                app_instance,
                surface_id,
                "Image",
            )
            or "Image"
        )
        url = str(
            self._resolve_initial_bound_value(
                props.get("url"),
                app_instance,
                surface_id,
                "",
            )
            or ""
        )
        w = self._resolve_initial_bound_value(
            props.get("width"),
            app_instance,
            surface_id,
            45,
        )
        h = self._resolve_initial_bound_value(
            props.get("height"),
            app_instance,
            surface_id,
            45,
        )
        fit = str(
            self._resolve_initial_bound_value(
                props.get("fit"),
                app_instance,
                surface_id,
                "",
            )
            or ""
        ).strip().lower()
        lazy = bool(
            self._resolve_initial_bound_value(
                props.get("lazy"),
                app_instance,
                surface_id,
                True,
            )
        )

        media_resolver = getattr(app_instance, "_media", None)
        widget = _ImageWidget(w, h, fit_mode=fit)
        widget.set_i18n(app_instance)
        widget.setObjectName(comp_id)
        setattr(widget, "_dmc_image_width", w)
        setattr(widget, "_dmc_image_height", h)
        setattr(widget, "_dmc_image_fit", fit)
        setattr(widget, "_dmc_image_comp_id", comp_id)
        setattr(widget, "_dmc_image_resolver", media_resolver)
        setattr(widget, "_dmc_image_url", url)
        setattr(widget, "_dmc_image_app_instance", app_instance)
        setattr(widget, "_dmc_image_lazy", lazy)
        setattr(widget, "_dmc_image_lazy_loader", None)
        setattr(widget, "_dmc_image_load_request_id", 0)
        self._set_widget_alt(widget, alt)
        widget._reload_btn.clicked.connect(
            lambda: self._on_reload(widget)
        )
        self._schedule_widget_image_load(
            widget=widget,
            url=url,
            w=w,
            h=h,
            comp_id=comp_id,
            media_resolver=media_resolver,
            app_instance=app_instance,
        )
        return widget

    def _on_reload(self, widget: _ImageWidget) -> None:
        url = str(getattr(widget, "_dmc_image_url", "") or "")
        if not url:
            return
        widget.show_image()
        widget.img_label.setText("[Loading]")
        widget.img_label.setPixmap(QPixmap())
        setattr(widget, "_dmc_image_lazy_loader", None)
        self._set_widget_image(
            widget=widget,
            url=url,
            w=int(getattr(widget, "_dmc_image_width", 45) or 45),
            h=int(getattr(widget, "_dmc_image_height", 45) or 45),
            comp_id=str(getattr(widget, "_dmc_image_comp_id", "unknown") or "unknown"),
            media_resolver=getattr(widget, "_dmc_image_resolver", None),
            app_instance=getattr(widget, "_dmc_image_app_instance", None),
            force_refresh=True,
        )

    def _schedule_widget_image_load(
        self,
        *,
        widget,
        url: str,
        w: int,
        h: int,
        comp_id: str,
        media_resolver: Any,
        app_instance: Any,
        force_refresh: bool = False,
    ) -> None:
        if not bool(getattr(widget, "_dmc_image_lazy", False)):
            self._set_widget_image(
                widget=widget,
                url=url,
                w=w,
                h=h,
                comp_id=comp_id,
                media_resolver=media_resolver,
                app_instance=app_instance,
                force_refresh=force_refresh,
            )
            return

        label: QLabel = widget.img_label if isinstance(widget, _ImageWidget) else widget
        label.setPixmap(QPixmap())
        label.setText("[Visible to load]")

        def _load_when_visible():
            self._set_widget_image(
                widget=widget,
                url=url,
                w=w,
                h=h,
                comp_id=comp_id,
                media_resolver=media_resolver,
                app_instance=app_instance,
                force_refresh=force_refresh,
            )

        loader = _LazyImageLoader(widget, _load_when_visible)
        setattr(widget, "_dmc_image_lazy_loader", loader)

    @staticmethod
    def _apply_resolved_image(
        widget, payload: Dict[str, Any], w: int, h: int, comp_id: str
    ) -> None:
        # Unwrap container to get the actual QLabel
        label: QLabel
        container: _ImageWidget | None = None
        if isinstance(widget, _ImageWidget):
            container = widget
            label = widget.img_label
        else:
            label = widget

        if payload.get("error"):
            error_code = str(payload.get("error_code") or "")
            if error_code == "not_enabled" and container is not None:
                container.show_placeholder(payload.get("error", container._blocked_message))
                return
            label.setPixmap(QPixmap())
            label.setText(f"[ERR Load: {payload.get('error')}]")
            return
        resolved_url = str(payload.get("path") or "")
        if not resolved_url:
            label.setPixmap(QPixmap())
            label.setText("[ERR Load]")
            return
        if container is not None:
            container.show_image()
        if resolved_url.lower().endswith(".svg"):
            with open(resolved_url, "rb") as f:
                svg_bytes = f.read()
            svg_bytes = _tint_logo_svg_if_needed(svg_bytes, comp_id, resolved_url)
            renderer = QSvgRenderer(svg_bytes)
            pixmap = QPixmap(w, h)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            try:
                renderer.render(painter)
            finally:
                if painter.isActive():
                    painter.end()
            label.setText("")
            if container is not None:
                container.set_source_pixmap(pixmap, w, h)
            else:
                label.setPixmap(pixmap)
            if comp_id == "logo_img":
                label.setFixedSize(w, h)
            return
        pixmap = QPixmap(resolved_url)
        if pixmap.isNull():
            label.setPixmap(QPixmap())
            label.setText(f"[ERR Load: {resolved_url}]")
            return
        if container is not None:
            container.set_source_pixmap(pixmap, w, h)
            return
        pixmap = pixmap.scaled(
            w,
            h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if comp_id == "logo_img":
            label.setFixedSize(pixmap.size())
        label.setText("")
        label.setPixmap(pixmap)

    def _set_widget_alt(self, widget, alt: str) -> None:
        value = str(alt or "")
        if hasattr(widget, "setToolTip"):
            widget.setToolTip(value)
        target = widget.img_label if isinstance(widget, _ImageWidget) else widget
        if hasattr(target, "setAccessibleName"):
            target.setAccessibleName(value or "Image")

    @staticmethod
    def _apply_loaded_image_result(
        *,
        widget,
        result: dict[str, Any],
        w: int,
        h: int,
        comp_id: str,
    ) -> None:
        label: QLabel = widget.img_label if isinstance(widget, _ImageWidget) else widget
        kind = str(result.get("kind") or "")

        if kind == "svg":
            svg_bytes = bytes(result.get("svg_bytes") or b"")
            if not svg_bytes:
                kind = "error"
            else:
                svg_bytes = _tint_logo_svg_if_needed(
                    svg_bytes,
                    comp_id,
                    str(result.get("source") or ""),
                )
                renderer = QSvgRenderer(svg_bytes)
                pixmap = QPixmap(w, h)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                try:
                    renderer.render(painter)
                finally:
                    if painter.isActive():
                        painter.end()
                label.setText("")
                if isinstance(widget, _ImageWidget):
                    widget.show_image()
                    widget.set_source_pixmap(pixmap, w, h)
                else:
                    label.setPixmap(pixmap)
                if comp_id == "logo_img":
                    label.setFixedSize(w, h)
                return

        if kind == "image":
            image = result.get("image")
            if not isinstance(image, QImage) or image.isNull():
                kind = "error"
            else:
                pixmap = QPixmap.fromImage(image)
                if pixmap.isNull():
                    kind = "error"
                else:
                    if isinstance(widget, _ImageWidget):
                        widget.show_image()
                        if getattr(widget, "_fit_mode", "") == "container":
                            widget.set_source_pixmap(pixmap, w, h)
                        else:
                            widget._source_pixmap = pixmap
                            widget.img_label.setText("")
                            widget.img_label.setPixmap(pixmap)
                        return
                    pixmap = pixmap.scaled(
                        w,
                        h,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    if comp_id == "logo_img":
                        label.setFixedSize(pixmap.size())
                    label.setText("")
                    label.setPixmap(pixmap)
                    return

        if isinstance(widget, _ImageWidget):
            widget.show_placeholder()
        else:
            label.setPixmap(QPixmap())
            label.setText("[ERR Load]")

    def _start_async_image_load(
        self,
        *,
        widget,
        normalized_url: str,
        resolved_url: str,
        w: int,
        h: int,
        comp_id: str,
        app_instance: Any,
    ) -> None:
        current_id = int(getattr(widget, "_dmc_image_load_request_id", 0) or 0) + 1
        setattr(widget, "_dmc_image_load_request_id", current_id)

        future = _IMAGE_LOAD_EXECUTOR.submit(
            _load_image_payload,
            normalized_url=normalized_url,
            resolved_url=resolved_url,
            app_instance=app_instance,
            w=w,
            h=h,
            fit_mode=str(getattr(widget, "_dmc_image_fit", "") or ""),
        )

        def _finish(done_future, request_id=current_id, expected_source=normalized_url):
            try:
                result = done_future.result()
            except Exception:
                result = {"kind": "error"}

            def _apply() -> None:
                if not qt_is_valid(widget):
                    return
                if int(getattr(widget, "_dmc_image_load_request_id", 0) or 0) != request_id:
                    return
                current_source = str(
                    getattr(widget, "_dmc_image_requested_source", "") or ""
                )
                if current_source != str(expected_source or ""):
                    return
                self._apply_loaded_image_result(
                    widget=widget,
                    result=result,
                    w=w,
                    h=h,
                    comp_id=comp_id,
                )

            try:
                QTimer.singleShot(0, widget, _apply)
            except RuntimeError:
                return

        future.add_done_callback(_finish)

    def _set_widget_image(
        self,
        *,
        widget,
        url: str,
        w: int,
        h: int,
        comp_id: str,
        media_resolver: Any,
        app_instance: Any,
        force_refresh: bool = False,
    ) -> None:
        label: QLabel = widget.img_label if isinstance(widget, _ImageWidget) else widget
        if not url:
            label.setPixmap(QPixmap())
            label.setText("[No URL]")
            return

        if url.startswith("ric.") or url.startswith("fa."):
            icon = get_icon(url)
            if icon:
                label.setText("")
                label.setPixmap(icon.pixmap(32, 32))
                return

        normalized_url = _with_proxy_resize_params(
            _normalize_image_source(url, app_instance),
            w,
            h,
        )
        setattr(widget, "_dmc_image_requested_source", normalized_url)
        if media_resolver is not None:
            label.setPixmap(QPixmap())
            label.setText("[Loading]")
        # KEEP COMMENTED: mediaResolver is intentionally bypassed for desktop media.
        # Media components now consume the final proxy/runtime URL directly.
        #
        # if media_resolver is not None and media_resolver.request_resolution(
        #     normalized_url,
        #     lambda payload, widget=widget, w=w, h=h, comp_id=comp_id, expected_source=normalized_url: self._apply_resolved_image_if_current(
        #         widget,
        #         payload,
        #         w,
        #         h,
        #         comp_id,
        #         expected_source=expected_source,
        #     ),
        #     force_refresh=force_refresh,
        # ):
        #     return

        parsed = urlparse(normalized_url)
        is_remote = parsed.scheme in {"http", "https"}
        localized_runtime_source = localize_runtime_media_source(normalized_url)
        resolved_url = (
            normalized_url
            if is_remote
            else (localized_runtime_source or resolve_resource(normalized_url))
        )

        label.setPixmap(QPixmap())
        label.setText("[Loading]")
        self._start_async_image_load(
            widget=widget,
            normalized_url=normalized_url,
            resolved_url=resolved_url,
            w=w,
            h=h,
            comp_id=comp_id,
            app_instance=app_instance,
        )

    @staticmethod
    def _apply_resolved_image_if_current(
        widget: QLabel,
        payload: Dict[str, Any],
        w: int,
        h: int,
        comp_id: str,
        *,
        expected_source: str,
    ) -> None:
        current_source = str(getattr(widget, "_dmc_image_requested_source", "") or "")
        if current_source and current_source != str(expected_source or ""):
            return
        ImageRenderer._apply_resolved_image(widget, payload, w, h, comp_id)

    def _literal(self, value: Any, fallback: str = "") -> str:
        if isinstance(value, dict):
            if "literalString" in value:
                return str(value.get("literalString") or "")
            return fallback
        if value is None:
            return fallback
        return str(value)

    def update_widget_property(self, widget, prop: str, value: Any) -> None:
        if prop == "alt":
            self._set_widget_alt(widget, self._literal(value))
            return
        if prop in {"width", "height"}:
            try:
                numeric = max(1, int(value or 0))
            except (TypeError, ValueError):
                return
            attr = "_dmc_image_width" if prop == "width" else "_dmc_image_height"
            setattr(widget, attr, numeric)
            current_url = str(getattr(widget, "_dmc_image_url", "") or "")
            if current_url:
                self._schedule_widget_image_load(
                    widget=widget,
                    url=current_url,
                    w=int(getattr(widget, "_dmc_image_width", 45) or 45),
                    h=int(getattr(widget, "_dmc_image_height", 45) or 45),
                    comp_id=str(
                    getattr(widget, "_dmc_image_comp_id", "unknown") or "unknown"
                    ),
                    media_resolver=getattr(widget, "_dmc_image_resolver", None),
                    app_instance=getattr(widget, "_dmc_image_app_instance", None),
                    force_refresh=False,
                )
            return
        if prop == "url":
            url = self._literal(value)
            setattr(widget, "_dmc_image_url", url)
            setattr(widget, "_dmc_image_lazy_loader", None)
            self._schedule_widget_image_load(
                widget=widget,
                url=url,
                w=int(getattr(widget, "_dmc_image_width", 45) or 45),
                h=int(getattr(widget, "_dmc_image_height", 45) or 45),
                comp_id=str(
                    getattr(widget, "_dmc_image_comp_id", "unknown") or "unknown"
                ),
                media_resolver=getattr(widget, "_dmc_image_resolver", None),
                app_instance=getattr(widget, "_dmc_image_app_instance", None),
                force_refresh=True,
            )
            return
        if prop == "lazy":
            setattr(widget, "_dmc_image_lazy", bool(value))
            return
        super().update_widget_property(widget, prop, value)
