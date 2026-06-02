from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QVariantAnimation
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget


AnimationCallback = Callable[[Any], None]


def _animation_bucket(owner: object) -> list[object]:
    bucket = getattr(owner, "_dmc_active_animations", None)
    if bucket is None:
        bucket = []
        setattr(owner, "_dmc_active_animations", bucket)
    return bucket


def _track_animation(owner: object, animation: object) -> object:
    bucket = _animation_bucket(owner)
    bucket.append(animation)

    def _cleanup() -> None:
        active = getattr(owner, "_dmc_active_animations", None)
        if active and animation in active:
            active.remove(animation)

    finished = getattr(animation, "finished", None)
    if finished is not None:
        finished.connect(_cleanup)
    return animation


def stop_animations(owner: object) -> None:
    active = getattr(owner, "_dmc_active_animations", None)
    if not active:
        return
    for animation in list(active):
        stopper = getattr(animation, "stop", None)
        if callable(stopper):
            try:
                stopper()
            except Exception:
                pass
    active.clear()


def ensure_opacity_effect(widget: QWidget) -> QGraphicsOpacityEffect:
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsOpacityEffect):
        return effect
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(1.0)
    widget.setGraphicsEffect(effect)
    return effect


def tween_value(
    owner: object,
    *,
    start: Any,
    end: Any,
    on_value: AnimationCallback,
    duration: int = 180,
    easing: QEasingCurve.Type = QEasingCurve.Type.InOutCubic,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QVariantAnimation:
    animation = QVariantAnimation(owner if hasattr(owner, "destroyed") else None)
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(max(int(duration), 1))
    animation.setEasingCurve(easing)
    animation.setLoopCount(loop_count if loop_count != 0 else 1)
    animation.valueChanged.connect(on_value)
    if finished is not None:
        animation.finished.connect(finished)
    _track_animation(owner, animation)
    animation.start()
    return animation


def fade(
    widget: QWidget,
    *,
    start: float | None = None,
    end: float,
    duration: int = 180,
    easing: QEasingCurve.Type = QEasingCurve.Type.InOutCubic,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    effect = ensure_opacity_effect(widget)
    if start is None:
        start = effect.opacity()
    if end > 0.0 and not widget.isVisible():
        widget.setVisible(True)

    animation = QPropertyAnimation(effect, b"opacity", widget)
    animation.setStartValue(max(0.0, min(float(start), 1.0)))
    animation.setEndValue(max(0.0, min(float(end), 1.0)))
    animation.setDuration(max(int(duration), 1))
    animation.setEasingCurve(easing)
    animation.setLoopCount(loop_count if loop_count != 0 else 1)
    if finished is not None:
        animation.finished.connect(finished)
    _track_animation(widget, animation)
    animation.start()
    return animation


def fade_in(
    widget: QWidget,
    *,
    duration: int = 180,
    start: float = 0.0,
    end: float = 1.0,
    easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    return fade(
        widget,
        start=start,
        end=end,
        duration=duration,
        easing=easing,
        loop_count=loop_count,
        finished=finished,
    )


def fade_out(
    widget: QWidget,
    *,
    duration: int = 150,
    start: float | None = None,
    end: float = 0.0,
    easing: QEasingCurve.Type = QEasingCurve.Type.InCubic,
    hide_on_finish: bool = True,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    def _finalize() -> None:
        if hide_on_finish:
            widget.setVisible(False)
        if finished is not None:
            finished()

    return fade(
        widget,
        start=start,
        end=end,
        duration=duration,
        easing=easing,
        loop_count=loop_count,
        finished=_finalize,
    )


def slide(
    widget: QWidget,
    *,
    end: QPoint,
    start: QPoint | None = None,
    duration: int = 220,
    easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QPropertyAnimation:
    animation = QPropertyAnimation(widget, b"pos", widget)
    animation.setStartValue(widget.pos() if start is None else start)
    animation.setEndValue(end)
    animation.setDuration(max(int(duration), 1))
    animation.setEasingCurve(easing)
    animation.setLoopCount(loop_count if loop_count != 0 else 1)
    if finished is not None:
        animation.finished.connect(finished)
    _track_animation(widget, animation)
    animation.start()
    return animation


def pulse_opacity(
    widget: QWidget,
    *,
    low: float = 0.72,
    high: float = 1.0,
    duration: int = 520,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QVariantAnimation:
    effect = ensure_opacity_effect(widget)
    low = max(0.0, min(float(low), 1.0))
    high = max(low, min(float(high), 1.0))

    def _apply(value: Any) -> None:
        effect.setOpacity(float(value))

    animation = tween_value(
        widget,
        start=low,
        end=high,
        on_value=_apply,
        duration=duration,
        easing=QEasingCurve.Type.InOutSine,
        loop_count=loop_count,
        finished=finished,
    )
    animation.setKeyValueAt(0.0, low)
    animation.setKeyValueAt(0.5, high)
    animation.setKeyValueAt(1.0, 1.0)
    return animation


def highlight_color(
    owner: object,
    *,
    start: QColor,
    end: QColor,
    on_color: Callable[[QColor], None],
    duration: int = 420,
    loop_count: int = 1,
    finished: Callable[[], None] | None = None,
) -> QVariantAnimation:
    return tween_value(
        owner,
        start=start,
        end=end,
        on_value=lambda value: on_color(QColor(value)),
        duration=duration,
        easing=QEasingCurve.Type.OutCubic,
        loop_count=loop_count,
        finished=finished,
    )


__all__ = [
    "ensure_opacity_effect",
    "fade",
    "fade_in",
    "fade_out",
    "highlight_color",
    "pulse_opacity",
    "slide",
    "stop_animations",
    "tween_value",
]
