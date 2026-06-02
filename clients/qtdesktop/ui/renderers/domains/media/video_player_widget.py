from __future__ import annotations

import os
import threading
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import QPropertyAnimation, QEasingCurve, QTimer, Qt, QSize, QUrl
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

from .common import (
    _apply_explicit_size,
    _as_media_url,
    _construct_qt_object,
    _is_allowed_media_source,
    _is_internal_proxy_source,
)
from .http import download_media_to_temp
from ....i18n import get_i18n
from ...icon import get_icon
from .video_frame_widget import VideoFrameWidget


class _VideoFullscreenOverlay(QWidget):
    """Fullscreen overlay that mirrors the VideoPlayerWidget video feed."""

    def __init__(self, parent_player: "VideoPlayerWidget"):
        super().__init__(None, Qt.WindowType.Window)
        self._player_ref = parent_player
        self.setStyleSheet("background: black;")
        self.setWindowTitle("Video – Fullscreen")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from .video_frame_widget import VideoFrameWidget

        self.video_host = VideoFrameWidget(self)
        self.video_host.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        layout.addWidget(self.video_host, 1)

        # Controls bar at the bottom
        controls_bar = QWidget(self)
        controls_bar.setStyleSheet("background: rgba(0,0,0,200);")
        controls_bar.setFixedHeight(44)
        ctrl_layout = QHBoxLayout(controls_bar)
        ctrl_layout.setContentsMargins(10, 0, 10, 0)
        ctrl_layout.setSpacing(10)

        self.play_button = QPushButton()
        self.play_button.setIcon(get_icon("ric.play-fill", "#fafafa", 20))
        self.play_button.setIconSize(QSize(20, 20))
        self.play_button.setProperty("ui_role", "media_control_btn")
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.mute_button = QPushButton()
        self.mute_button.setIcon(get_icon("ric.volume-up-fill", "#fafafa", 20))
        self.mute_button.setIconSize(QSize(20, 20))
        self.mute_button.setProperty("ui_role", "media_control_btn")
        self.mute_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setProperty("ui_role", "media_position_slider")
        self.position_slider.setRange(0, 0)
        self.position_slider.setCursor(Qt.CursorShape.PointingHandCursor)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setProperty("ui_role", "media_time")
        self.time_label.setStyleSheet("color: white;")

        self.exit_button = QPushButton()
        self.exit_button.setIcon(get_icon("ric.fullscreen-exit-line", "#fafafa", 20))
        self.exit_button.setIconSize(QSize(20, 20))
        self.exit_button.setProperty("ui_role", "media_control_btn")
        self.exit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.exit_button.setToolTip("Exit fullscreen (Esc)")

        ctrl_layout.addWidget(self.play_button)
        ctrl_layout.addWidget(self.mute_button)
        ctrl_layout.addWidget(self.position_slider, 1)
        ctrl_layout.addWidget(self.time_label)
        ctrl_layout.addWidget(self.exit_button)

        layout.addWidget(controls_bar)

        self.play_button.clicked.connect(parent_player.toggle_playback)
        self.mute_button.clicked.connect(parent_player._toggle_muted)
        self.position_slider.sliderPressed.connect(parent_player._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_overlay_slider_released)
        self.position_slider.valueChanged.connect(self._on_overlay_slider_value_changed)
        self.exit_button.clicked.connect(parent_player._exit_fullscreen)

    # ------------------------------------------------------------------
    # Overlay slider handling
    # ------------------------------------------------------------------

    def _on_overlay_slider_released(self) -> None:
        p = self._player_ref
        p._slider_dragging = False
        if p.player is not None:
            p.player.setPosition(self.position_slider.value())

    def _on_overlay_slider_value_changed(self, value: int) -> None:
        if self._player_ref._slider_dragging:
            self._player_ref._update_time_label(value, self._player_ref._duration)

    # ------------------------------------------------------------------
    # Sync helpers called by VideoPlayerWidget
    # ------------------------------------------------------------------

    def sync_play_button(self, icon_name: str) -> None:
        if qt_is_valid(self.play_button):
            self.play_button.setIcon(get_icon(icon_name, "#fafafa", 20))

    def sync_mute_button(self, icon_name: str) -> None:
        if qt_is_valid(self.mute_button):
            self.mute_button.setIcon(get_icon(icon_name, "#fafafa", 20))

    def sync_position(self, position: int) -> None:
        if qt_is_valid(self.position_slider) and not self._player_ref._slider_dragging:
            self.position_slider.setValue(position)

    def sync_duration(self, duration: int) -> None:
        if qt_is_valid(self.position_slider):
            self.position_slider.setRange(0, duration)

    def sync_time_label(self, text: str) -> None:
        if qt_is_valid(self.time_label):
            self.time_label.setText(text)

    def set_frame_pixmap(self, pixmap: "QPixmap") -> None:  # noqa: F821
        if qt_is_valid(self.video_host):
            self.video_host.set_frame_pixmap(pixmap)

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._player_ref._exit_fullscreen()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:  # noqa: N802
        if qt_is_valid(self._player_ref):
            self._player_ref._fullscreen_overlay = None
            self._player_ref._sync_fullscreen_button()
        super().closeEvent(event)


class VideoPlayerWidget(QFrame):
    def __init__(
        self,
        *,
        title: str = "",
        width: int = 640,
        height: int = 360,
        controls: bool = True,
    ):
        super().__init__()
        self._autoplay = False
        self._muted = False
        self._loop = False
        self._duration = 0
        self._slider_dragging = False
        self._play_on_load = False
        self._poster = ""
        self._pending_source = ""
        self._loaded_source = ""
        self._requested_source = ""
        self._resolving_proxy_source = False
        self._local_media_path = ""
        self._media_player_cls = None
        self._proxy_base_url = "http://127.0.0.1:8000"
        self.player = None
        self.audio_output = None
        self.video_sink = None
        self._media_resolver = None
        self._fullscreen_overlay: _VideoFullscreenOverlay | None = None
        self._download_request_id = 0
        self._i18n = get_i18n(self)

        self.setProperty("ui_role", "video_player_root")
        self.setMouseTracking(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        _apply_explicit_size(self, max(width, 240), max(height, 135))

        # Main layout: Title at top, then Video + Overlay
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        self.title_label = QLabel(title)
        self.title_label.setVisible(bool(title))
        self.title_label.setProperty("ui_role", "media_title")
        self.title_label.setContentsMargins(4, 0, 0, 4)
        self.main_layout.addWidget(self.title_label)

        # Video container for overlay positioning
        self.video_container = QWidget()
        self.video_container.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.main_layout.addWidget(self.video_container)

        self.video_host = VideoFrameWidget(self.video_container)
        self.video_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        _apply_explicit_size(self.video_host, max(width, 240), max(height, 135))

        self.status_label = QLabel("", self.video_host)
        self.status_label.setProperty("ui_role", "media_status")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(
            "background: rgba(0,0,0,120); color: white; border-radius: 4px; padding: 4px;"
        )
        self.status_label.hide()

        # Controls Overlay
        self.controls_frame = QWidget(self.video_container)
        self.controls_frame.setProperty("ui_role", "video_controls_overlay")
        self.controls_frame.setFixedHeight(44)

        controls_layout = QHBoxLayout(self.controls_frame)
        controls_layout.setContentsMargins(10, 0, 10, 0)
        controls_layout.setSpacing(10)

        # Symbols: Play: ric.play-fill, Pause: ric.pause-fill, Mute: ric.volume-mute-fill, Vol: ric.volume-up-fill
        self.play_button = QPushButton()
        self.play_button.setIcon(get_icon("ric.play-fill", "#fafafa", 20))
        self.play_button.setIconSize(QSize(20, 20))
        self.play_button.setProperty("ui_role", "media_control_btn")
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.mute_button = QPushButton()
        self.mute_button.setIcon(get_icon("ric.volume-up-fill", "#fafafa", 20))
        self.mute_button.setIconSize(QSize(20, 20))
        self.mute_button.setProperty("ui_role", "media_control_btn")
        self.mute_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.reload_button = QPushButton()
        self.reload_button.setIcon(get_icon("ric.refresh-line", "#fafafa", 20))
        self.reload_button.setIconSize(QSize(20, 20))
        self.reload_button.setProperty("ui_role", "media_control_btn")
        self.reload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_button.setToolTip(self._i18n["reload_url"])

        self.fullscreen_button = QPushButton()
        self.fullscreen_button.setIcon(get_icon("ric.fullscreen-line", "#fafafa", 20))
        self.fullscreen_button.setIconSize(QSize(20, 20))
        self.fullscreen_button.setProperty("ui_role", "media_control_btn")
        self.fullscreen_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.fullscreen_button.setToolTip("Fullscreen")

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setProperty("ui_role", "media_position_slider")
        self.position_slider.setRange(0, 0)
        self.position_slider.setCursor(Qt.CursorShape.PointingHandCursor)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setProperty("ui_role", "media_time")

        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.mute_button)
        controls_layout.addWidget(self.reload_button)
        controls_layout.addWidget(self.position_slider, 1)
        controls_layout.addWidget(self.time_label)
        controls_layout.addWidget(self.fullscreen_button)

        self.controls_frame.setVisible(bool(controls))

        # Placeholder overlay (shown when URL is blocked, covers the video area)
        self._ph_overlay = QWidget(self.video_container)
        self._ph_overlay.setProperty("ui_role", "media_placeholder")
        ph_layout = QVBoxLayout(self._ph_overlay)
        ph_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_layout.setSpacing(8)
        self._ph_label = QLabel(self._i18n["blocked_url"])
        self._ph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ph_label.setProperty("ui_role", "media_status")
        self._ph_reload_btn = QPushButton(self._i18n["reload"])
        self._ph_reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ph_reload_btn.clicked.connect(self._reload_source)
        ph_layout.addWidget(self._ph_label)
        ph_layout.addWidget(self._ph_reload_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self._ph_overlay.hide()

        # Hover animation setup
        from PySide6.QtWidgets import QGraphicsOpacityEffect

        self._fade_effect = QGraphicsOpacityEffect(self.controls_frame)
        self.controls_frame.setGraphicsEffect(self._fade_effect)
        self._fade_effect.setOpacity(0.0)

        self._fade_anim = QPropertyAnimation(self._fade_effect, b"opacity")
        self._fade_anim.setDuration(250)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

        self.play_button.clicked.connect(self.toggle_playback)
        self.mute_button.clicked.connect(self._toggle_muted)
        self.reload_button.clicked.connect(self._reload_source)
        self.fullscreen_button.clicked.connect(self._toggle_fullscreen)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.valueChanged.connect(self._on_slider_value_changed)

        # Backend is initialized lazily on first successful URL resolution.

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))

    # ------------------------------------------------------------------
    # Fullscreen
    # ------------------------------------------------------------------

    def _toggle_fullscreen(self) -> None:
        if self._fullscreen_overlay is None:
            overlay = _VideoFullscreenOverlay(self)
            # Mirror current poster/frame state
            if not self.video_host._frame_pixmap.isNull():
                overlay.video_host.set_frame_pixmap(self.video_host._frame_pixmap)
            elif not self.video_host._poster_pixmap.isNull():
                overlay.video_host.set_poster(
                    self._poster,
                    getattr(self, "_dmc_video_app_instance", None),
                )
            # Sync current player state
            if self._duration:
                overlay.sync_duration(self._duration)
            if self.player is not None:
                overlay.sync_position(self.player.position())
            overlay.sync_time_label(self.time_label.text())
            self._fullscreen_overlay = overlay
            overlay.showFullScreen()
        else:
            self._exit_fullscreen()

    def _exit_fullscreen(self) -> None:
        overlay = self._fullscreen_overlay
        self._fullscreen_overlay = None
        if overlay is not None and qt_is_valid(overlay):
            overlay.close()
        self._sync_fullscreen_button()

    def _sync_fullscreen_button(self) -> None:
        if not qt_is_valid(self.fullscreen_button):
            return
        if self._fullscreen_overlay is not None:
            self.fullscreen_button.setIcon(get_icon("ric.fullscreen-exit-line", "#fafafa", 20))
            self.fullscreen_button.setToolTip("Exit fullscreen")
        else:
            self.fullscreen_button.setIcon(get_icon("ric.fullscreen-line", "#fafafa", 20))
            self.fullscreen_button.setToolTip("Fullscreen")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        r = self.video_container.rect()
        self.video_host.setGeometry(r)
        self._ph_overlay.setGeometry(r)
        ch = self.controls_frame.height()
        self.controls_frame.setGeometry(0, r.height() - ch, r.width(), ch)
        self._reposition_status_label()

    def _reposition_status_label(self) -> None:
        if not qt_is_valid(self.status_label) or not self.status_label.isVisible():
            return
        r = self.video_host.rect()
        sw = self.status_label.sizeHint().width() + 20
        sh = self.status_label.sizeHint().height() + 10
        self.status_label.setGeometry(
            (r.width() - sw) // 2, (r.height() - sh) // 2, sw, sh
        )

    def enterEvent(self, event) -> None:
        if self.controls_frame.isVisible():
            self._fade_anim.stop()
            self._fade_anim.setStartValue(self._fade_effect.opacity())
            self._fade_anim.setEndValue(1.0)
            self._fade_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self.controls_frame.isVisible():
            self._fade_anim.stop()
            self._fade_anim.setStartValue(self._fade_effect.opacity())
            self._fade_anim.setEndValue(0.0)
            self._fade_anim.start()
        super().leaveEvent(event)

    def set_media_resolver(self, resolver: Any) -> None:
        self._media_resolver = resolver

    def set_proxy_base_url(self, base_url: str) -> None:
        self._proxy_base_url = str(base_url or "http://127.0.0.1:8000")

    def _clear_local_media_path(self) -> None:
        local_path = str(self._local_media_path or "").strip()
        self._local_media_path = ""
        if not local_path:
            return
        try:
            os.remove(local_path)
        except OSError:
            pass

    def _download_internal_media_to_temp(self, source: str) -> str:
        temp_path = self._download_internal_media_to_temp_path(source)
        if not temp_path:
            return ""
        self._clear_local_media_path()
        self._local_media_path = temp_path
        return temp_path

    def _download_internal_media_to_temp_path(self, source: str) -> str:
        return download_media_to_temp(
            getattr(self, "_dmc_video_app_instance", None) or self,
            source,
            prefix="democrai-video-",
            timeout=30.0,
        )

    @staticmethod
    def _is_internal_media_source(source: str) -> bool:
        value = str(source or "")
        parsed = urlparse(value)
        return value.startswith("/media/") or (
            parsed.scheme in {"http", "https"} and parsed.path.startswith("/media/")
        )

    def _start_internal_media_download(self, source: str) -> None:
        self._download_request_id += 1
        request_id = self._download_request_id

        def _worker() -> None:
            temp_path = self._download_internal_media_to_temp_path(source)
            QTimer.singleShot(
                0,
                self,
                lambda rid=request_id, path=temp_path: self._on_internal_media_download_finished(
                    rid, path
                ),
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_internal_media_download_finished(
        self, request_id: int, temp_path: str
    ) -> None:
        if not qt_is_valid(self) or request_id != self._download_request_id:
            if temp_path:
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return
        self._set_placeholder_loading(False)
        if not temp_path:
            self._show_placeholder("URL bloccato")
            self._pending_source = ""
            self._loaded_source = ""
            self._resolving_proxy_source = False
            self.video_host.clear_frame()
            if self.player is not None:
                self.player.setSource(QUrl())
                self.player.stop()
            return
        self._clear_local_media_path()
        self._local_media_path = temp_path
        self._pending_source = temp_path
        self._resolving_proxy_source = False
        self._show_player()
        self._load_source(temp_path, play=self._autoplay)

    def set_source(self, source: str, *, force_refresh: bool = False) -> None:
        requested_source = str(source or "")
        if not requested_source:
            self._set_status("No video source configured.")
            self._pending_source = ""
            self._loaded_source = ""
            self._requested_source = ""
            self._resolving_proxy_source = False
            self._clear_local_media_path()
            self.video_host.clear_frame()
            if self.player is not None:
                self.player.setSource(QUrl())
                self.player.stop()
            return

        if not _is_allowed_media_source(requested_source):
            self._set_status("Remote media URLs are disabled in the desktop client.")
            self._pending_source = ""
            self._loaded_source = ""
            self._requested_source = ""
            self._resolving_proxy_source = False
            self._clear_local_media_path()
            self.video_host.clear_frame()
            if self.player is not None:
                self.player.setSource(QUrl())
                self.player.stop()
            return

        self._requested_source = requested_source
        # KEEP COMMENTED: mediaResolver is intentionally bypassed for desktop media.
        # Media components now consume the final proxy/runtime URL directly.
        #
        # is_proxy_source = _is_internal_proxy_source(requested_source)
        # if self._media_resolver is not None:
        #     # self._set_status("Loading video...")
        #     self._pending_source = requested_source
        #     self._loaded_source = ""
        #     self._resolving_proxy_source = True
        #     self.video_host.clear_frame()
        #     if self.player is not None:
        #         self.player.setSource(QUrl())
        #         self.player.stop()
        #     if self._media_resolver.request_resolution(
        #         requested_source,
        #         self._on_media_resolved,
        #         force_refresh=force_refresh,
        #     ):
        #         return
        #     self._resolving_proxy_source = False
        # if is_proxy_source:
        #     self._set_status("Unable to resolve video source.")
        #     self._pending_source = ""
        #     self._loaded_source = ""
        #     self._resolving_proxy_source = False
        #     self._clear_local_media_path()
        #     self.video_host.clear_frame()
        #     if self.player is not None:
        #         self.player.setSource(QUrl())
        #         self.player.stop()
        #     return

        if self._is_internal_media_source(requested_source):
            self._pending_source = requested_source
            self._loaded_source = ""
            self._resolving_proxy_source = True
            self.video_host.clear_frame()
            self._set_status("Loading video...")
            self._set_placeholder_loading(True)
            if self.player is not None:
                self.player.setSource(QUrl())
                self.player.stop()
            self._start_internal_media_download(requested_source)
            return

        normalized_source = self._normalize_source(requested_source)
        if not normalized_source:
            self._show_placeholder("URL bloccato")
            self._pending_source = ""
            self._loaded_source = ""
            self._resolving_proxy_source = False
            self._clear_local_media_path()
            self.video_host.clear_frame()
            if self.player is not None:
                self.player.setSource(QUrl())
                self.player.stop()
            return
        self._pending_source = normalized_source
        self._resolving_proxy_source = False
        self._show_player()
        self._load_source(normalized_source, play=self._autoplay)

    def _normalize_source(self, source: str) -> str:
        value = str(source or "")
        parsed = urlparse(value)
        if value.startswith("/media/") or (
            parsed.scheme in {"http", "https"} and parsed.path.startswith("/media/")
        ):
            localized = self._download_internal_media_to_temp(value)
            return localized
        return value

    def set_autoplay(self, autoplay: bool) -> None:
        self._autoplay = bool(autoplay)
        if (
            self._autoplay
            and self._pending_source
            and self._loaded_source != self._pending_source
            and not self._resolving_proxy_source
        ):
            self._load_source(self._pending_source, play=True)

    def _reload_source(self) -> None:
        if hasattr(self, "_requested_source") and self._requested_source:
            self._set_status("")
            self._set_placeholder_loading(True)
            self.set_source(self._requested_source, force_refresh=True)

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        icon_name = "ric.volume-mute-fill" if self._muted else "ric.volume-up-fill"
        self.mute_button.setIcon(get_icon(icon_name, "#fafafa", 20))
        if self.audio_output is None:
            return
        self.audio_output.setMuted(self._muted)
        icon_name = (
            "ric.volume-mute-fill"
            if self.audio_output.isMuted()
            else "ric.volume-up-fill"
        )
        self.mute_button.setIcon(get_icon(icon_name, "#fafafa", 20))
        if self._fullscreen_overlay is not None and qt_is_valid(self._fullscreen_overlay):
            self._fullscreen_overlay.sync_mute_button(icon_name)

    def set_loop(self, loop: bool) -> None:
        self._loop = bool(loop)

    def set_poster(self, poster: str) -> None:
        self._poster = poster
        self.video_host.set_poster(
            poster,
            getattr(self, "_dmc_video_app_instance", None),
        )

    def toggle_playback(self) -> None:
        if self._pending_source and self._loaded_source != self._pending_source:
            self._load_source(self._pending_source, play=True)
            return
        if self.player is None:
            return
        if (
            self.player.playbackState()
            == self._media_player_cls.PlaybackState.PlayingState
        ):
            self.player.pause()
        else:
            self.player.play()

    def _load_source(self, source: str, *, play: bool) -> None:
        self._ensure_backend()
        if self.player is None or self.video_sink is None:
            return
        self._set_status("Loading video...")
        self._play_on_load = play
        self.video_host.clear_frame()
        self.player.stop()
        self.player.setSource(_as_media_url(source))
        self._loaded_source = source

    def _toggle_muted(self) -> None:
        if self.audio_output is None:
            self._ensure_backend()
        if self.audio_output is None:
            return
        self.set_muted(not self.audio_output.isMuted())

    def set_i18n(self, app_instance: Any) -> None:
        self._i18n = get_i18n(app_instance)
        self.reload_button.setToolTip(self._i18n["reload_url"])
        self._ph_label.setText(self._i18n["blocked_url"])
        self._ph_reload_btn.setText(self._i18n["reload"])

    def _ensure_backend(self) -> None:
        if self.player is not None:
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

        self._media_player_cls = QMediaPlayer
        try:
            self.player = _construct_qt_object(QMediaPlayer, self)
            self.audio_output = _construct_qt_object(QAudioOutput, self)
        except Exception as exc:
            self.player = None
            self.audio_output = None
            self.video_sink = None
            self._set_status(f"Embedded video backend unavailable: {exc}")
            return
        self.player.setAudioOutput(self.audio_output)
        self.audio_output.setMuted(self._muted)
        if not hasattr(self.player, "setVideoSink"):
            self.player = None
            self.audio_output = None
            self.video_sink = None
            self._set_status("Embedded video backend unavailable.")
            return
        self.video_sink = _construct_qt_object(QVideoSink, self)
        self.player.setVideoSink(self.video_sink)
        icon_name = (
            "ric.volume-mute-fill"
            if self.audio_output.isMuted()
            else "ric.volume-up-fill"
        )
        self.mute_button.setIcon(get_icon(icon_name, "#fafafa", 20))
        self.video_sink.videoFrameChanged.connect(self._on_video_frame_changed)
        self.player.playbackStateChanged.connect(self._sync_play_button)
        self.player.positionChanged.connect(self._sync_position)
        self.player.durationChanged.connect(self._sync_duration)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)

    def _sync_play_button(self, state) -> None:
        icon_name = (
            "ric.pause-fill"
            if state == self._media_player_cls.PlaybackState.PlayingState
            else "ric.play-fill"
        )
        self.play_button.setIcon(get_icon(icon_name, "#fafafa", 20))
        if self._fullscreen_overlay is not None and qt_is_valid(self._fullscreen_overlay):
            self._fullscreen_overlay.sync_play_button(icon_name)

    def _sync_position(self, position: int) -> None:
        if not self._slider_dragging:
            self.position_slider.setValue(position)
        self._update_time_label(position, self._duration)
        if self._fullscreen_overlay is not None and qt_is_valid(self._fullscreen_overlay):
            self._fullscreen_overlay.sync_position(position)

    def _sync_duration(self, duration: int) -> None:
        self._duration = max(duration, 0)
        self.position_slider.setRange(0, self._duration)
        self._update_time_label(self.player.position(), self._duration)
        if self._fullscreen_overlay is not None and qt_is_valid(self._fullscreen_overlay):
            self._fullscreen_overlay.sync_duration(self._duration)

    def _on_slider_pressed(self) -> None:
        self._slider_dragging = True

    def _on_slider_released(self) -> None:
        self._slider_dragging = False
        if self.player is not None:
            self.player.setPosition(self.position_slider.value())

    def _on_slider_value_changed(self, value: int) -> None:
        if self._slider_dragging:
            self._update_time_label(value, self._duration)

    def _on_media_status_changed(self, status) -> None:
        if status == self._media_player_cls.MediaStatus.EndOfMedia and self._loop:
            self.player.setPosition(0)
            self.player.play()
            return
        if status in {
            self._media_player_cls.MediaStatus.LoadedMedia,
            self._media_player_cls.MediaStatus.BufferedMedia,
        }:
            self._set_status("")
            if self._play_on_load:
                self._play_on_load = False
                QTimer.singleShot(0, self.player.play)
        elif status == self._media_player_cls.MediaStatus.LoadingMedia:
            self._set_status("Loading video...")
        elif status == self._media_player_cls.MediaStatus.BufferingMedia:
            self._set_status("Buffering video...")
        elif status == self._media_player_cls.MediaStatus.InvalidMedia:
            self._set_status("Unable to load video.")

    def _on_error(self, error, message: str) -> None:
        if error == self._media_player_cls.Error.NoError:
            return
        self._resolving_proxy_source = False
        self._loaded_source = ""
        self.video_host.clear_frame()
        self._show_placeholder("URL bloccato")

    def _on_video_frame_changed(self, frame: Any) -> None:
        if frame is None or not getattr(frame, "isValid", lambda: False)():
            return
        image = frame.toImage()
        if image.isNull():
            return
        pixmap = QPixmap.fromImage(image)
        self.video_host.set_frame_pixmap(pixmap)
        if self._fullscreen_overlay is not None and qt_is_valid(self._fullscreen_overlay):
            self._fullscreen_overlay.set_frame_pixmap(pixmap)

    def _on_media_resolved(self, payload: dict[str, Any]) -> None:
        if not qt_is_valid(self):
            return
        self._resolving_proxy_source = False
        self._set_placeholder_loading(False)
        if payload.get("error"):
            if str(payload.get("error_code") or "") == "not_enabled":
                self._show_placeholder(str(payload.get("error") or "URL bloccato"))
            else:
                self._set_status(str(payload.get("error")))
                if self.player is not None:
                    self.player.setSource(QUrl())
            return
        path = str(payload.get("path") or "")
        if not path:
            self._set_status("Unable to resolve video.")
            if self.player is not None:
                self.player.setSource(QUrl())
            return
        self._show_player()
        self._pending_source = path
        self._load_source(path, play=self._autoplay)

    def _show_placeholder(self, message: str = "") -> None:
        if qt_is_valid(self._ph_label):
            self._ph_label.setText(str(message or self._i18n["blocked_url"]))
        if qt_is_valid(self._ph_overlay):
            self._ph_overlay.setGeometry(self.video_container.rect())
            self._ph_overlay.show()
            self._ph_overlay.raise_()
        if self.player is not None:
            self.player.stop()
            self.player.setSource(QUrl())
        if qt_is_valid(self.video_host):
            self.video_host.clear_frame()

    def _set_placeholder_loading(self, loading: bool) -> None:
        if qt_is_valid(self._ph_reload_btn):
            self._ph_reload_btn.setEnabled(not loading)
            self._ph_reload_btn.setText(
                self._i18n["loading"] if loading else self._i18n["reload"]
            )

    def _show_player(self) -> None:
        if qt_is_valid(self._ph_overlay):
            self._ph_overlay.hide()

    def _set_status(self, text: str) -> None:
        if qt_is_valid(self.status_label):
            self.status_label.setText(str(text))
            self.status_label.setVisible(bool(text))
            if bool(text):
                self.status_label.adjustSize()
                self._reposition_status_label()
            self.update()  # Trigger repaint

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        self._clear_local_media_path()
        super().closeEvent(event)

    def _update_time_label(self, position: int, duration: int) -> None:
        text = f"{self._format_ms(position)} / {self._format_ms(duration)}"
        self.time_label.setText(text)
        if self._fullscreen_overlay is not None and qt_is_valid(self._fullscreen_overlay):
            self._fullscreen_overlay.sync_time_label(text)

    @staticmethod
    def _format_ms(value: int) -> str:
        total_seconds = max(int(value / 1000), 0)
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"
