from __future__ import annotations

import mimetypes
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget

from ...base import BaseRenderer, publish_bound_value


def _audio_extension(mime: str) -> str:
    normalized = str(mime or "").lower()
    if "wav" in normalized:
        return ".wav"
    if "mpeg" in normalized or "mp3" in normalized:
        return ".mp3"
    if "ogg" in normalized:
        return ".ogg"
    if "mp4" in normalized:
        return ".m4a"
    return ".wav"


class AudioRecorderRenderer(BaseRenderer):
    component_type = "AudioRecorder"

    def render(
        self,
        props: dict,
        surface_id: str,
        app_instance: Any,
        comp_id: str = "unknown",
    ):
        del surface_id
        container = QWidget()
        container.setObjectName(comp_id)
        container.setProperty("is_input", True)
        container.setProperty("value", [])
        publish_bound_value(app_instance, container, comp_id, [])

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label_text = self._literal_text(props.get("label"))
        if label_text:
            label = QLabel(label_text)
            label.setProperty("ui_role", "form_label")
            layout.addWidget(label)

        controls = QWidget()
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)
        record_btn = QPushButton("Record")
        remove_btn = QPushButton("Remove")
        remove_btn.hide()
        status_label = QLabel("")
        status_label.setProperty("ui_role", "form_help_text")
        controls_layout.addWidget(record_btn)
        controls_layout.addWidget(remove_btn)
        controls_layout.addWidget(status_label)
        controls_layout.addStretch(1)
        layout.addWidget(controls)

        error_label = QLabel()
        error_label.setProperty("ui_role", "form_error_label")
        error_label.setWordWrap(True)
        error_label.hide()
        layout.addWidget(error_label)

        state: dict[str, Any] = {
            "app_instance": app_instance,
            "comp_id": comp_id,
            "container": container,
            "record_btn": record_btn,
            "remove_btn": remove_btn,
            "status_label": status_label,
            "error_label": error_label,
            "recording": False,
            "started_at": 0.0,
            "local_path": "",
        }
        container._audio_recorder_state = state  # type: ignore[attr-defined]

        try:
            from PySide6.QtMultimedia import (
                QAudioInput,
                QMediaCaptureSession,
                QMediaDevices,
                QMediaFormat,
                QMediaRecorder,
            )
        except Exception:
            record_btn.setEnabled(False)
            error_label.setText("Audio recording is not available in this Qt build")
            error_label.show()
            return container

        audio_input = QAudioInput(QMediaDevices.defaultAudioInput(), container)
        capture_session = QMediaCaptureSession(container)
        recorder = QMediaRecorder(container)
        capture_session.setAudioInput(audio_input)
        capture_session.setRecorder(recorder)
        state["recorder"] = recorder

        media_format = QMediaFormat()
        media_format.setFileFormat(QMediaFormat.FileFormat.Wave)
        media_format.setAudioCodec(QMediaFormat.AudioCodec.Wave)
        recorder.setMediaFormat(media_format)

        def _set_value(entries: list[dict[str, Any]]) -> None:
            container.setProperty("value", entries)
            publish_bound_value(app_instance, container, comp_id, entries)

        def _start() -> None:
            error_label.hide()
            suffix = _audio_extension(str(recorder.mediaFormat().mimeType().name()))
            target = tempfile.NamedTemporaryFile(
                prefix="democrai_recording_",
                suffix=suffix,
                delete=False,
            )
            target.close()
            state["local_path"] = target.name
            state["started_at"] = time.monotonic()
            recorder.setOutputLocation(QUrl.fromLocalFile(target.name))
            recorder.record()
            state["recording"] = True
            record_btn.setText("Stop")
            status_label.setText("Recording")

        def _stop() -> None:
            recorder.stop()

        def _remove() -> None:
            local_path = str(state.get("local_path") or "")
            if local_path:
                try:
                    Path(local_path).unlink(missing_ok=True)
                except OSError:
                    pass
            state["local_path"] = ""
            remove_btn.hide()
            status_label.setText("")
            _set_value([])

        def _on_stopped() -> None:
            state["recording"] = False
            record_btn.setText("Record")
            local_path = str(state.get("local_path") or "")
            path = Path(local_path)
            if not local_path or not path.is_file() or path.stat().st_size <= 0:
                error_label.setText("Recording failed")
                error_label.show()
                _set_value([])
                return
            duration_seconds = round(max(0.0, time.monotonic() - float(state.get("started_at") or 0.0)), 2)
            guessed_mime, _ = mimetypes.guess_type(str(path))
            entry = {
                "name": path.name,
                "size": int(path.stat().st_size),
                "type": str(guessed_mime or "audio/wav"),
                "mime": str(guessed_mime or "audio/wav"),
                "local_path": str(path),
                "kind": "audio",
                "duration_seconds": duration_seconds,
            }
            remove_btn.show()
            status_label.setText(f"{duration_seconds}s")
            _set_value([entry])

        def _toggle() -> None:
            if state.get("recording"):
                _stop()
            else:
                _start()

        record_btn.clicked.connect(_toggle)
        remove_btn.clicked.connect(_remove)
        recorder.recorderStateChanged.connect(
            lambda state_value: _on_stopped()
            if state_value == QMediaRecorder.RecorderState.StoppedState
            else None
        )

        return container

    def update_widget_property(self, widget: QWidget, prop: str, value: Any) -> None:
        if prop == "error":
            state = getattr(widget, "_audio_recorder_state", {})
            error_label = state.get("error_label") if isinstance(state, dict) else None
            if error_label is not None:
                text = self._literal_text(value)
                error_label.setText(text)
                error_label.setVisible(bool(text))
            return
        if prop == "value":
            entries = value if isinstance(value, list) else []
            widget.setProperty("value", entries)
            return
        super().update_widget_property(widget, prop, value)
