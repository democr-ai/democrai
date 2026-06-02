from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid as qt_is_valid

from ...base import BaseRenderer
from .....utils.paths import resolve_resource
from .common import (
    _apply_explicit_size,
    _as_media_url,
    _build_local_proxy_base_url,
    _construct_qt_object,
    _int_value,
    _is_allowed_media_source,
    _is_internal_proxy_source,
    _literal,
    _normalize_media_source,
    load_runtime_image_pixmap,
)

class VideoFrameWidget(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._frame_pixmap = QPixmap()
        self._poster_pixmap = QPixmap()
        self._last_rendered_size = None
        self._last_rendered_source = None
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("VIDEO")
        self.setProperty("ui_role", "media_video_frame")

    def set_frame_pixmap(self, pixmap: QPixmap) -> None:
        self._frame_pixmap = pixmap
        self._last_rendered_source = None
        self._render_current_pixmap()

    def clear_frame(self) -> None:
        self._frame_pixmap = QPixmap()
        self._last_rendered_source = None
        self._render_current_pixmap()

    def set_poster(self, poster: str, app_instance: Any | None = None) -> None:
        if not poster:
            self._poster_pixmap = QPixmap()
            self._last_rendered_source = None
            self._render_current_pixmap()
            return
        pixmap = load_runtime_image_pixmap(poster, app_instance)
        self._poster_pixmap = pixmap if not pixmap.isNull() else QPixmap()
        self._last_rendered_source = None
        self._render_current_pixmap()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().resizeEvent(event)
        self._render_current_pixmap()

    def _render_current_pixmap(self) -> None:
        pixmap = self._frame_pixmap if not self._frame_pixmap.isNull() else self._poster_pixmap
        if pixmap.isNull():
            self.setPixmap(QPixmap())
            self.setText("VIDEO")
            self._last_rendered_size = None
            self._last_rendered_source = None
            return
        target_size = self.size()
        cache_key = pixmap.cacheKey()
        if (
            self._last_rendered_size == target_size
            and self._last_rendered_source == cache_key
        ):
            return
        self.setText("")
        self.setPixmap(
            pixmap.scaled(
                target_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
        )
        self._last_rendered_size = target_size
        self._last_rendered_source = cache_key
