from __future__ import annotations

import math
import struct
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QWidget

class AnimatedWaveformWidget(QWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._phase = 0.0
        self._active = False
        self._position_ms = 0
        self._levels: list[float] = []
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick)
        self.setMinimumHeight(64)

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        if self._active:
            self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def set_position(self, position_ms: int) -> None:
        self._position_ms = max(position_ms, 0)
        if not self._active:
            self.update()

    def set_levels(self, levels: list[float]) -> None:
        self._levels = [max(0.0, min(float(level), 1.0)) for level in levels]
        self.update()

    def _tick(self) -> None:
        self._phase += 0.32
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        painter.fillRect(rect, QColor("#050505")) # @bg-deep

        bar_count = 28
        gap = 4
        usable_width = max(rect.width() - ((bar_count - 1) * gap), 1)
        bar_width = max(usable_width / bar_count, 3)
        center_y = rect.height() / 2
        max_height = rect.height() * 0.62
        base = 0.01 if not self._active else 0.015

        for index in range(bar_count):
            if self._levels:
                level = self._levels[index % len(self._levels)]
                boosted = min(level ** 0.38, 1.0)
                amplitude = base + boosted * (1.06 if self._active else 0.30)
            else:
                offset = self._phase + index * 0.55 + (self._position_ms / 1000.0) * 0.8
                amplitude = base + abs(math.sin(offset)) * (0.92 if self._active else 0.18)
            bar_height = max(2.0, min(max_height * amplitude, rect.height() * 0.92))
            x = index * (bar_width + gap)
            y = center_y - (bar_height / 2)
            color = QColor("#3b82f6" if self._active else "#3f3f46") # @color-info / @border-strong
            color.setAlpha(210 if self._active else 170)
            path = QPainterPath()
            path.addRoundedRect(x, y, bar_width, bar_height, 3, 3)
            painter.fillPath(path, color)


def _read_audio_buffer_bytes(buffer: Any) -> bytes:
    for accessor in ("data", "constData"):
        getter = getattr(buffer, accessor, None)
        if getter is None:
            continue
        try:
            raw = getter()
        except TypeError:
            continue
        if raw is None:
            continue
        try:
            return bytes(raw)
        except TypeError:
            try:
                return memoryview(raw).tobytes()
            except TypeError:
                continue
    return b""


def _decode_pcm_samples(audio_format: Any, raw: bytes) -> list[float]:
    sample_format = audio_format.sampleFormat()
    bytes_per_sample = max(int(audio_format.bytesPerSample() or 0), 0)
    if bytes_per_sample <= 0 or not raw:
        return []

    samples: list[float] = []
    step = bytes_per_sample
    sample_enum = getattr(type(audio_format), "SampleFormat", None)
    if sample_enum is None:
        return []

    for offset in range(0, len(raw) - bytes_per_sample + 1, step):
        chunk = raw[offset : offset + bytes_per_sample]
        if sample_format == sample_enum.UInt8:
            samples.append(abs((chunk[0] - 128) / 128.0))
        elif sample_format == sample_enum.Int16 and len(chunk) == 2:
            samples.append(abs(int.from_bytes(chunk, "little", signed=True) / 32768.0))
        elif sample_format == sample_enum.Int32 and len(chunk) == 4:
            samples.append(abs(int.from_bytes(chunk, "little", signed=True) / 2147483648.0))
        elif sample_format == sample_enum.Float and len(chunk) == 4:
            samples.append(min(abs(struct.unpack("<f", chunk)[0]), 1.0))
        else:
            return []
    return samples


def _extract_audio_levels(buffer: Any, *, bars: int = 28) -> list[float]:
    if buffer is None or not getattr(buffer, "isValid", lambda: False)():
        return []

    audio_format = buffer.format()
    if audio_format is None or not audio_format.isValid():
        return []

    raw = _read_audio_buffer_bytes(buffer)
    samples = _decode_pcm_samples(audio_format, raw)
    if not samples:
        return []

    levels: list[float] = []
    chunk_size = max(len(samples) // bars, 1)
    for start in range(0, len(samples), chunk_size):
        window = samples[start : start + chunk_size]
        if not window:
            continue
        levels.append(min(sum(window) / len(window), 1.0))
        if len(levels) >= bars:
            break

    if len(levels) < bars and levels:
        levels.extend([levels[-1]] * (bars - len(levels)))
    return levels


