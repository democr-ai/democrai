from __future__ import annotations

import os
import threading
from typing import Any, Dict
from urllib.parse import urlparse

from PySide6.QtCore import Qt, QTimer
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
from PySide6.QtCore import Qt, QSize, QUrl
from shiboken6 import isValid as qt_is_valid

from ...base import BaseRenderer
from ....i18n import get_i18n
from ....theme.tokens import theme_token
from .....utils.paths import resolve_resource
from .audio_levels import AnimatedWaveformWidget, _extract_audio_levels
from .common import (
    _apply_explicit_size,
    _as_media_url,
    _construct_qt_object,
    _is_allowed_media_source,
    _is_internal_proxy_source,
    _literal,
    load_runtime_image_pixmap,
)
from ...icon import get_icon
from .common import localize_runtime_media_source
from .http import download_media_to_temp
from .video_player_widget import VideoPlayerWidget


class AudioPlayerWidget(QFrame):
    def __init__(
        self,
        *,
        title: str = "",
        width: int = 640,
        height: int = 180,
        controls: bool = True,
    ):
        super().__init__()
        self._autoplay = False
        self._loop = False
        self._duration = 0
        self._slider_dragging = False
        self._media_player_cls = None
        self._proxy_base_url = "http://127.0.0.1:8000"
        self._media_resolver = None
        self._requested_source = ""
        self._local_media_path = ""
        self._source_loading = False
        self._ignore_expected_abort_error = False
        self._download_request_id = 0
        self._i18n = get_i18n(self)

        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setProperty("ui_role", "audio_player_root")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        _apply_explicit_size(self, max(width, 320), max(height, 140))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        self.title_label = QLabel(title)
        self.title_label.setVisible(bool(title))
        self.title_label.setProperty("ui_role", "media_title")
        layout.addWidget(self.title_label)

        hero = QHBoxLayout()
        hero.setContentsMargins(0, 0, 0, 0)
        hero.setSpacing(12)

        self.poster_label = QLabel()
        self.poster_label.setFixedSize(72, 72)
        self.poster_label.setProperty("ui_role", "media_audio_poster")
        self.poster_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.poster_label.setText("AUDIO")
        hero.addWidget(self.poster_label)

        center = QVBoxLayout()
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(8)
        self.waveform = AnimatedWaveformWidget()
        self.waveform.setFixedHeight(32)
        center.addWidget(self.waveform)
        self.status_label = QLabel("")
        self.status_label.setProperty("ui_role", "media_status")
        self.status_label.setVisible(False)
        center.addWidget(self.status_label)
        self.controls_frame = QWidget()
        controls_layout = QHBoxLayout(self.controls_frame)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(12)

        self.play_button = QPushButton()
        self.play_button.setIconSize(QSize(20, 20))
        self.play_button.setProperty("ui_role", "media_control_btn")
        self.play_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.mute_button = QPushButton()
        self.mute_button.setIconSize(QSize(20, 20))
        self.mute_button.setProperty("ui_role", "media_control_btn")
        self.mute_button.setCursor(Qt.CursorShape.PointingHandCursor)

        self.reload_button = QPushButton()
        self.reload_button.setIconSize(QSize(20, 20))
        self.reload_button.setProperty("ui_role", "media_control_btn")
        self.reload_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reload_button.setToolTip(self._i18n["reload_url"])

        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setProperty("ui_role", "media_position_slider")
        self.position_slider.setRange(0, 0)
        self.position_slider.setCursor(Qt.CursorShape.PointingHandCursor)

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setProperty("ui_role", "media_time")
        self._set_control_icons()

        controls_layout.addWidget(self.play_button)
        controls_layout.addWidget(self.mute_button)
        controls_layout.addWidget(self.reload_button)
        controls_layout.addWidget(self.position_slider, 1)
        controls_layout.addWidget(self.time_label)
        self.controls_frame.setVisible(bool(controls))
        center.addWidget(self.controls_frame)
        hero.addLayout(center, 1)
        layout.addLayout(hero)

        # Placeholder overlay (shown when URL is blocked, covers entire widget)
        self._ph_overlay = QWidget(self)
        self._ph_overlay.setProperty("ui_role", "media_placeholder")
        ph_ov_layout = QVBoxLayout(self._ph_overlay)
        ph_ov_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ph_ov_layout.setSpacing(8)
        self._ph_label = QLabel(self._i18n["blocked_url"])
        self._ph_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ph_label.setProperty("ui_role", "media_status")
        self._ph_reload_btn = QPushButton(self._i18n["reload"])
        self._ph_reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._ph_reload_btn.clicked.connect(self._reload_source)
        ph_ov_layout.addWidget(self._ph_label)
        ph_ov_layout.addWidget(self._ph_reload_btn, 0, Qt.AlignmentFlag.AlignCenter)
        self._ph_overlay.hide()

        # Backend initialized lazily on first successful URL resolution.
        self.player = None
        self.audio_output = None
        self.audio_buffer_output = None

        self.play_button.clicked.connect(self.toggle_playback)
        self.mute_button.clicked.connect(self._toggle_muted)
        self.reload_button.clicked.connect(self._reload_source)
        self.position_slider.sliderPressed.connect(self._on_slider_pressed)
        self.position_slider.sliderReleased.connect(self._on_slider_released)
        self.position_slider.valueChanged.connect(self._on_slider_value_changed)

    def _ensure_backend(self) -> None:
        if self.player is not None:
            return
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        self._media_player_cls = QMediaPlayer
        try:
            self.player = _construct_qt_object(QMediaPlayer, self)
            self.audio_output = _construct_qt_object(QAudioOutput, self)
        except Exception as exc:
            self.player = None
            self.audio_output = None
            self.audio_buffer_output = None
            self._set_status(f"Embedded audio backend unavailable: {exc}")
            self.play_button.setEnabled(False)
            self.mute_button.setEnabled(False)
            self.position_slider.setEnabled(False)
            return
        self.player.setAudioOutput(self.audio_output)
        try:
            from PySide6.QtMultimedia import QAudioBufferOutput
            if hasattr(self.player, "setAudioBufferOutput"):
                self.audio_buffer_output = _construct_qt_object(QAudioBufferOutput, self)
                self.audio_buffer_output.audioBufferReceived.connect(self._on_audio_buffer)
                self.player.setAudioBufferOutput(self.audio_buffer_output)
        except Exception:
            self.audio_buffer_output = None
        self.player.playbackStateChanged.connect(self._sync_play_button)
        self.player.positionChanged.connect(self._sync_position)
        self.player.durationChanged.connect(self._sync_duration)
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)
        self.player.errorOccurred.connect(self._on_error)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if qt_is_valid(self._ph_overlay):
            self._ph_overlay.setGeometry(self.rect())

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)
        self.title_label.setVisible(bool(title))

    def set_media_resolver(self, resolver: Any) -> None:
        self._media_resolver = resolver

    def set_i18n(self, app_instance: Any) -> None:
        self._i18n = get_i18n(app_instance)
        self.reload_button.setToolTip(self._i18n["reload_url"])
        self._ph_label.setText(self._i18n["blocked_url"])
        self._ph_reload_btn.setText(self._i18n["reload"])
        self._set_control_icons(app_instance=app_instance)

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

    def _stop_player(self, *, clear_source: bool) -> None:
        if self.player is None:
            return
        self.player.stop()
        if clear_source:
            self._ignore_expected_abort_error = True
            self.player.setSource(QUrl())

    def _set_loading_state(self, loading: bool) -> None:
        self._source_loading = bool(loading)
        if qt_is_valid(self.play_button):
            self.play_button.setEnabled(not loading)
        if qt_is_valid(self.reload_button):
            self.reload_button.setEnabled(not loading)

    def _download_internal_media_to_temp(self, source: str) -> str:
        temp_path = self._download_internal_media_to_temp_path(source)
        if not temp_path:
            return ""
        self._clear_local_media_path()
        self._local_media_path = temp_path
        return temp_path

    def _download_internal_media_to_temp_path(self, source: str) -> str:
        return download_media_to_temp(
            getattr(self, "_dmc_audio_app_instance", None) or self,
            source,
            prefix="democrai-audio-",
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
        self._set_loading_state(False)
        self._set_placeholder_loading(False)
        if not temp_path:
            self._show_placeholder("URL bloccato")
            self.waveform.set_active(False)
            self.waveform.set_levels([])
            self._stop_player(clear_source=True)
            return
        self._clear_local_media_path()
        self._local_media_path = temp_path
        self._show_player()
        self._ensure_backend()
        if self.player is None:
            return
        self._ignore_expected_abort_error = False
        self._set_status("")
        self.player.stop()
        self.player.setSource(_as_media_url(temp_path))
        if self._autoplay:
            self.player.play()

    def set_source(self, source: str, *, force_refresh: bool = False) -> None:
        requested_source = str(source or "")
        self._requested_source = requested_source
        if not requested_source:
            self._set_loading_state(False)
            self._set_status("No audio source configured.")
            self._stop_player(clear_source=True)
            self._clear_local_media_path()
            self.waveform.set_active(False)
            self.waveform.set_levels([])
            return

        if not _is_allowed_media_source(requested_source):
            self._set_loading_state(False)
            self._set_status("Remote media URLs are disabled in the desktop client.")
            self._stop_player(clear_source=True)
            self._clear_local_media_path()
            self.waveform.set_active(False)
            self.waveform.set_levels([])
            return

        is_proxy_source = _is_internal_proxy_source(requested_source)
        # KEEP COMMENTED: mediaResolver is intentionally bypassed for desktop media.
        # Media components now consume the final proxy/runtime URL directly.
        #
        # if self._media_resolver is not None:
        #     self._set_loading_state(True)
        #     self._set_status("Loading audio...")
        #     self._stop_player(clear_source=False)
        #     self.waveform.set_active(False)
        #     self.waveform.set_levels([])
        #     if self._media_resolver.request_resolution(
        #         requested_source,
        #         self._on_media_resolved,
        #         force_refresh=force_refresh,
        #     ):
        #         return
        #     self._set_loading_state(False)

        # Direct URL: create backend lazily and load.
        self._set_loading_state(False)
        self._ensure_backend()
        if self.player is None:
            return
        if self._is_internal_media_source(requested_source):
            self._set_loading_state(True)
            self._set_placeholder_loading(True)
            self._set_status("Loading audio...")
            self._stop_player(clear_source=False)
            self.waveform.set_active(False)
            self.waveform.set_levels([])
            self._start_internal_media_download(requested_source)
            return
        source = self._normalize_source(requested_source)
        if not source:
            self._show_placeholder("URL bloccato")
            self._clear_local_media_path()
            self.waveform.set_active(False)
            self.waveform.set_levels([])
            self._stop_player(clear_source=True)
            return
        self._show_player()
        self._ignore_expected_abort_error = False
        self._set_status("")
        self.player.stop()
        self.player.setSource(_as_media_url(source))
        if self._autoplay:
            self.player.play()

    def _reload_source(self) -> None:
        if self._requested_source:
            self._set_status("")
            self._set_placeholder_loading(True)
            self.set_source(self._requested_source, force_refresh=True)

    def _normalize_source(self, source: str) -> str:
        value = str(source or "")
        parsed = urlparse(value)
        if value.startswith("/media/") or (
            parsed.scheme in {"http", "https"} and parsed.path.startswith("/media/")
        ):
            localized = self._download_internal_media_to_temp(value)
            return localized
        if value.startswith("/media/proxy"):
            return f"{self._proxy_base_url}{value}"
        return value

    def set_autoplay(self, autoplay: bool) -> None:
        self._autoplay = bool(autoplay)

    def set_muted(self, muted: bool) -> None:
        if self.audio_output is None:
            return
        self.audio_output.setMuted(bool(muted))
        self._set_mute_icon()

    def set_loop(self, loop: bool) -> None:
        self._loop = bool(loop)

    def set_poster(self, poster: str) -> None:
        if not poster:
            self.poster_label.setPixmap(QPixmap())
            self.poster_label.setText("AUDIO")
            return
        pixmap = load_runtime_image_pixmap(
            poster,
            getattr(self, "_dmc_audio_app_instance", None),
        )
        if pixmap.isNull():
            self.poster_label.setPixmap(QPixmap())
            self.poster_label.setText("AUDIO")
            return
        self.poster_label.setText("")
        self.poster_label.setPixmap(
            pixmap.scaled(
                self.poster_label.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def toggle_playback(self) -> None:
        if self._source_loading:
            return
        if self.player is None or self._media_player_cls is None:
            return
        if (
            self.player.playbackState()
            == self._media_player_cls.PlaybackState.PlayingState
        ):
            self.player.pause()
        else:
            self.player.play()

    def _toggle_muted(self) -> None:
        if self.audio_output is None:
            return
        self.set_muted(not self.audio_output.isMuted())

    def _sync_play_button(self, state) -> None:
        playing = state == self._media_player_cls.PlaybackState.PlayingState
        icon_name = "ric.pause-fill" if playing else "ric.play-fill"
        self.play_button.setIcon(get_icon(icon_name, self._control_icon_color(), 20))
        self.waveform.set_active(playing)
        if not playing:
            self.waveform.set_levels([])

    def _sync_position(self, position: int) -> None:
        self.waveform.set_position(position)
        if not self._slider_dragging:
            self.position_slider.setValue(position)
        self._update_time_label(position, self._duration)

    def _sync_duration(self, duration: int) -> None:
        self._duration = max(duration, 0)
        self.position_slider.setRange(0, self._duration)
        self._update_time_label(self.player.position() if self.player else 0, self._duration)

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
        if status in {
            self._media_player_cls.MediaStatus.LoadedMedia,
            self._media_player_cls.MediaStatus.BufferedMedia,
            self._media_player_cls.MediaStatus.InvalidMedia,
            self._media_player_cls.MediaStatus.NoMedia,
        }:
            self._ignore_expected_abort_error = False
        if status == self._media_player_cls.MediaStatus.EndOfMedia and self._loop:
            self.player.setPosition(0)
            self.player.play()

    def _on_error(self, error, message: str) -> None:
        if error == self._media_player_cls.Error.NoError:
            return
        normalized = str(message or "").strip().lower()
        if self._ignore_expected_abort_error and "immediate exit requested" in normalized:
            self._ignore_expected_abort_error = False
            return
        self._set_loading_state(False)
        self._show_placeholder("URL bloccato")
        self.waveform.set_active(False)
        self.waveform.set_levels([])

    def _update_time_label(self, position: int, duration: int) -> None:
        self.time_label.setText(
            f"{VideoPlayerWidget._format_ms(position)} / {VideoPlayerWidget._format_ms(duration)}"
        )

    def _on_audio_buffer(self, buffer: Any) -> None:
        levels = _extract_audio_levels(buffer)
        if levels:
            self.waveform.set_levels(levels)

    def _on_media_resolved(self, payload: dict[str, Any]) -> None:
        if not qt_is_valid(self):
            return
        self._set_loading_state(False)
        self._set_placeholder_loading(False)
        if payload.get("error"):
            if str(payload.get("error_code") or "") == "not_enabled":
                self._show_placeholder(str(payload.get("error") or "URL bloccato"))
            else:
                self._set_status(str(payload.get("error")))
                self._stop_player(clear_source=True)
            return
        path = str(payload.get("path") or "")
        if not path:
            self._set_status("Unable to resolve audio.")
            return
        self._show_player()
        self._ensure_backend()
        if self.player is None:
            return
        self._ignore_expected_abort_error = False
        self._set_status("")
        self.player.stop()
        self.player.setSource(_as_media_url(path))
        if self._autoplay:
            self.player.play()

    def _show_placeholder(self, message: str = "") -> None:
        if qt_is_valid(self._ph_label):
            self._ph_label.setText(str(message or self._i18n["blocked_url"]))
        if qt_is_valid(self._ph_overlay):
            self._ph_overlay.setGeometry(self.rect())
            self._ph_overlay.show()
            self._ph_overlay.raise_()
        self._set_loading_state(False)
        self._stop_player(clear_source=True)
        if qt_is_valid(self.waveform):
            self.waveform.set_active(False)
            self.waveform.set_levels([])

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
            value = str(text)
            self.status_label.setText(value)
            self.status_label.setVisible(bool(value))

    def _control_icon_color(self, app_instance: Any | None = None) -> str:
        return theme_token("text.primary", app_instance=app_instance) or "#111827"

    def _set_mute_icon(self, app_instance: Any | None = None) -> None:
        audio_output = getattr(self, "audio_output", None)
        muted = bool(audio_output is not None and audio_output.isMuted())
        icon_name = "ric.volume-mute-fill" if muted else "ric.volume-up-fill"
        self.mute_button.setIcon(
            get_icon(icon_name, self._control_icon_color(app_instance), 20)
        )

    def _set_control_icons(self, app_instance: Any | None = None) -> None:
        color = self._control_icon_color(app_instance)
        self.play_button.setIcon(get_icon("ric.play-fill", color, 20))
        self.reload_button.setIcon(get_icon("ric.refresh-line", color, 20))
        self._set_mute_icon(app_instance=app_instance)
