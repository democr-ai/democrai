from __future__ import annotations

from typing import Any

import shiboken6
from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QLayout, QScrollArea, QTabWidget, QWidget

from ..animation import fade_in, pulse_opacity, slide, stop_animations


def _widget_alive(widget: Any) -> bool:
    try:
        return widget is not None and shiboken6.isValid(widget)
    except Exception:
        return widget is not None


def normalize_animation_spec(spec: Any) -> dict[str, Any] | None:
    if isinstance(spec, str):
        text = spec.strip()
        if not text:
            return None
        return {"name": text}
    if isinstance(spec, dict):
        name = str(spec.get("name") or spec.get("type") or "").strip()
        if not name:
            return None
        animation = dict(spec)
        animation["name"] = name
        return animation
    return None


def run_declared_animation(
    widget: QWidget,
    spec: Any,
    *,
    extra_delay: int = 0,
    force: bool = False,
    qtimer_cls: type[QTimer] = QTimer,
    stop_animations_fn=stop_animations,
    fade_in_fn=fade_in,
    pulse_opacity_fn=pulse_opacity,
    slide_fn=slide,
) -> None:
    animation = normalize_animation_spec(spec)
    if not animation:
        return

    signature = repr(animation)
    current_signature = widget.property("_dmc_last_animation_signature")
    if not force and current_signature == signature:
        return
    widget.setProperty("_dmc_last_animation_signature", signature)
    widget.setProperty("_dmc_animation_retry_count", 0)

    def _start() -> None:
        if not _widget_alive(widget):
            return
        width_getter = getattr(widget, "width", None)
        height_getter = getattr(widget, "height", None)
        try:
            width = int(width_getter() if callable(width_getter) else 1)
            height = int(height_getter() if callable(height_getter) else 1)
        except RuntimeError:
            return

        if width <= 0 or height <= 0:
            if not _widget_alive(widget):
                return
            retries = int(widget.property("_dmc_animation_retry_count") or 0)
            if retries < 3:
                widget.setProperty("_dmc_animation_retry_count", retries + 1)
                qtimer_cls.singleShot(16, _start)
            return

        stop_animations_fn(widget)
        name = animation["name"]
        duration = int(animation.get("duration", 220) or 220)
        loop_count = int(animation.get("loop", 1) or 1)

        if name in {"fade", "fade_in"}:
            fade_in_fn(
                widget,
                duration=duration,
                start=float(animation.get("opacity_from", 0.0)),
                end=float(animation.get("opacity_to", 1.0)),
                loop_count=loop_count,
            )
            return
        if name in {"pulse", "blink"}:
            pulse_opacity_fn(
                widget,
                low=float(animation.get("low", 0.28 if name == "blink" else 0.72)),
                high=float(animation.get("high", 1.0)),
                duration=duration,
                loop_count=loop_count,
            )
            return

        if name.startswith("slide_"):
            distance = int(animation.get("distance", 36) or 36)
            end = widget.pos()
            start = QPoint(end)
            if name == "slide_left":
                start.setX(end.x() + distance)
            elif name == "slide_right":
                start.setX(end.x() - distance)
            elif name == "slide_up":
                start.setY(end.y() + distance)
            elif name == "slide_down":
                start.setY(end.y() - distance)
            slide_fn(widget, start=start, end=end, duration=duration, loop_count=loop_count)
            if animation.get("fade", True):
                fade_in_fn(
                    widget,
                    duration=duration,
                    start=float(animation.get("opacity_from", 0.0)),
                    end=float(animation.get("opacity_to", 1.0)),
                )

    delay = max(int(animation.get("delay", 0) or 0) + int(extra_delay), 0)
    qtimer_cls.singleShot(delay, _start)


def normalize_stagger_spec(spec: Any) -> dict[str, Any] | None:
    if spec is None or spec is False:
        return None
    if isinstance(spec, (int, float)):
        return {"step": int(spec), "animation": {"name": "fade_in", "duration": 220}}
    if isinstance(spec, str):
        text = spec.strip()
        if not text:
            return None
        return {"step": 70, "animation": {"name": text}}
    if isinstance(spec, dict):
        animation = normalize_animation_spec(
            spec.get("animation") or spec.get("preset") or {"name": "fade_in", "duration": 220}
        )
        normalized = dict(spec)
        normalized["animation"] = animation or {"name": "fade_in", "duration": 220}
        return normalized
    return None


def direct_child_widgets(widget: QWidget) -> list[QWidget]:
    layout = widget.layout()
    if layout is not None:
        return widgets_from_layout(layout)
    if isinstance(widget, QScrollArea):
        inner = widget.widget()
        if inner and inner.layout() is not None:
            return widgets_from_layout(inner.layout())
    if isinstance(widget, QTabWidget):
        return [widget.widget(index) for index in range(widget.count()) if widget.widget(index) is not None]
    return []


def widgets_from_layout(layout: QLayout) -> list[QWidget]:
    children: list[QWidget] = []
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is None:
            continue
        child = item.widget()
        if child is not None:
            children.append(child)
    return children
