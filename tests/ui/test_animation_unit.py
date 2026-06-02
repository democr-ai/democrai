from __future__ import annotations

from types import SimpleNamespace

import clients.qtdesktop.ui.animation as animation_mod
import clients.qtdesktop.ui.renderers.base as base_renderer_mod
from PySide6.QtCore import QPoint


class _Signal:
    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for callback in list(self._callbacks):
            callback(*args, **kwargs)


class _FakeOpacityEffect:
    def __init__(self, parent=None):
        self.parent = parent
        self._opacity = 1.0

    def setOpacity(self, value):
        self._opacity = float(value)

    def opacity(self):
        return self._opacity


class _FakeAnimationBase:
    def __init__(self, target=None, prop=None, parent=None):
        self.target = target
        self.property_name = prop
        self.parent = parent
        self.start_value = None
        self.end_value = None
        self.duration = None
        self.easing = None
        self.loop_count = 1
        self.started = False
        self.key_values = []
        self.finished = _Signal()

    def setStartValue(self, value):
        self.start_value = value

    def setEndValue(self, value):
        self.end_value = value

    def setDuration(self, value):
        self.duration = value

    def setEasingCurve(self, value):
        self.easing = value

    def setLoopCount(self, value):
        self.loop_count = value

    def setKeyValueAt(self, step, value):
        self.key_values.append((step, value))

    def start(self):
        self.started = True


class _FakePropertyAnimation(_FakeAnimationBase):
    pass


class _FakeVariantAnimation(_FakeAnimationBase):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.valueChanged = _Signal()


class _FakeWidget:
    def __init__(self):
        self._effect = None
        self._visible = False
        self._pos = QPoint(4, 8)
        self._properties = {}

    def graphicsEffect(self):
        return self._effect

    def setGraphicsEffect(self, effect):
        self._effect = effect

    def isVisible(self):
        return self._visible

    def setVisible(self, visible):
        self._visible = bool(visible)

    def pos(self):
        return self._pos

    def property(self, name):
        return self._properties.get(name)

    def setProperty(self, name, value):
        self._properties[name] = value


def test_ensure_opacity_effect_reuses_existing_effect(monkeypatch):
    monkeypatch.setattr(animation_mod, "QGraphicsOpacityEffect", _FakeOpacityEffect)
    widget = _FakeWidget()

    created = animation_mod.ensure_opacity_effect(widget)
    reused = animation_mod.ensure_opacity_effect(widget)

    assert created is reused
    assert created.opacity() == 1.0


def test_fade_in_tracks_animation_and_makes_widget_visible(monkeypatch):
    monkeypatch.setattr(animation_mod, "QGraphicsOpacityEffect", _FakeOpacityEffect)
    monkeypatch.setattr(animation_mod, "QPropertyAnimation", _FakePropertyAnimation)
    widget = _FakeWidget()

    animation = animation_mod.fade_in(widget, duration=240, start=0.15, end=0.9)

    assert widget.isVisible() is True
    assert animation.started is True
    assert animation.start_value == 0.15
    assert animation.end_value == 0.9
    assert animation.duration == 240
    assert animation.loop_count == 1
    assert animation.property_name == b"opacity"
    assert animation in widget._dmc_active_animations

    animation.finished.emit()
    assert widget._dmc_active_animations == []


def test_slide_uses_current_position_as_default_start(monkeypatch):
    monkeypatch.setattr(animation_mod, "QPropertyAnimation", _FakePropertyAnimation)
    widget = _FakeWidget()

    animation = animation_mod.slide(widget, end=QPoint(24, 48), duration=300)

    assert animation.start_value == QPoint(4, 8)
    assert animation.end_value == QPoint(24, 48)
    assert animation.duration == 300
    assert animation.property_name == b"pos"


def test_tween_value_wires_value_callback_and_finished_cleanup(monkeypatch):
    monkeypatch.setattr(animation_mod, "QVariantAnimation", _FakeVariantAnimation)
    owner = SimpleNamespace()
    values = []
    finished = []

    animation = animation_mod.tween_value(
        owner,
        start=0.0,
        end=10.0,
        on_value=lambda value: values.append(value),
        duration=180,
        finished=lambda: finished.append(True),
    )

    assert animation.started is True
    assert animation.start_value == 0.0
    assert animation.end_value == 10.0
    assert animation.duration == 180
    assert animation.loop_count == 1
    assert animation in owner._dmc_active_animations

    animation.valueChanged.emit(4.5)
    assert values == [4.5]

    animation.finished.emit()
    assert finished == [True]
    assert owner._dmc_active_animations == []


def test_pulse_opacity_sets_keyframes(monkeypatch):
    monkeypatch.setattr(animation_mod, "QGraphicsOpacityEffect", _FakeOpacityEffect)
    monkeypatch.setattr(animation_mod, "QVariantAnimation", _FakeVariantAnimation)
    widget = _FakeWidget()

    animation = animation_mod.pulse_opacity(widget, low=0.4, high=0.95, duration=500)

    assert animation.started is True
    assert animation.start_value == 0.4
    assert animation.end_value == 0.95
    assert animation.loop_count == 1
    assert animation.key_values == [(0.0, 0.4), (0.5, 0.95), (1.0, 1.0)]

    animation.valueChanged.emit(0.8)
    assert widget.graphicsEffect().opacity() == 0.8


def test_stop_animations_stops_and_clears_bucket():
    stopped = []

    class _Anim:
        def stop(self):
            stopped.append(True)

    owner = SimpleNamespace(_dmc_active_animations=[_Anim(), object()])
    animation_mod.stop_animations(owner)

    assert stopped == [True]
    assert owner._dmc_active_animations == []


def test_base_renderer_applies_declared_slide_animation(monkeypatch):
    class _Renderer(base_renderer_mod.BaseRenderer):
        component_type = "Test"

        def render(self, props, surface_id, app_instance, comp_id="unknown"):
            return None

    widget = _FakeWidget()
    timer_calls = []
    slide_calls = []
    fade_calls = []

    monkeypatch.setattr(base_renderer_mod, "QTimer", type("Timer", (), {"singleShot": staticmethod(lambda delay, fn: (timer_calls.append(delay), fn()))}))
    monkeypatch.setattr(base_renderer_mod, "slide", lambda *args, **kwargs: slide_calls.append(kwargs))
    monkeypatch.setattr(base_renderer_mod, "fade_in", lambda *args, **kwargs: fade_calls.append(kwargs))

    renderer = _Renderer()
    renderer.apply_declared_animation(
        widget,
        {"name": "slide_left", "distance": 64, "duration": 280, "fade": True},
    )

    assert timer_calls == [0]
    assert slide_calls[0]["duration"] == 280
    assert slide_calls[0]["start"] == QPoint(68, 8)
    assert slide_calls[0]["end"] == QPoint(4, 8)
    assert fade_calls[0]["duration"] == 280


def test_base_renderer_applies_blink_animation(monkeypatch):
    class _Renderer(base_renderer_mod.BaseRenderer):
        component_type = "Test"

        def render(self, props, surface_id, app_instance, comp_id="unknown"):
            return None

    widget = _FakeWidget()
    pulse_calls = []

    monkeypatch.setattr(base_renderer_mod, "QTimer", type("Timer", (), {"singleShot": staticmethod(lambda delay, fn: fn())}))
    monkeypatch.setattr(base_renderer_mod, "pulse_opacity", lambda *args, **kwargs: pulse_calls.append(kwargs))

    renderer = _Renderer()
    renderer.apply_declared_animation(widget, {"name": "blink", "duration": 900, "loop": -1})

    assert pulse_calls == [{"low": 0.28, "high": 1.0, "duration": 900, "loop_count": -1}]


def test_base_renderer_applies_delay_and_stagger(monkeypatch):
    class _Renderer(base_renderer_mod.BaseRenderer):
        component_type = "Test"

        def render(self, props, surface_id, app_instance, comp_id="unknown"):
            return None

    container = _FakeWidget()
    children = [_FakeWidget(), _FakeWidget(), _FakeWidget()]
    timer_calls = []
    fade_calls = []

    monkeypatch.setattr(
        base_renderer_mod,
        "QTimer",
        type("Timer", (), {"singleShot": staticmethod(lambda delay, fn: (timer_calls.append(delay), fn()))}),
    )
    monkeypatch.setattr(base_renderer_mod, "fade_in", lambda *args, **kwargs: fade_calls.append(kwargs))

    renderer = _Renderer()
    monkeypatch.setattr(renderer, "_direct_child_widgets", lambda widget: children)

    renderer.apply_declared_animation(
        container,
        {"name": "fade_in", "duration": 210, "delay": 75},
    )
    renderer.apply_post_children_effects(
        container,
        {
            "animation_stagger": {
                "step": 90,
                "delay": 40,
                "animation": {"name": "fade_in", "duration": 180},
            }
        },
    )

    assert timer_calls[:4] == [75, 40, 130, 220]
    assert fade_calls[0]["duration"] == 210
    assert [call["duration"] for call in fade_calls[1:]] == [180, 180, 180]


def test_base_renderer_retries_animation_until_widget_ready(monkeypatch):
    class _Renderer(base_renderer_mod.BaseRenderer):
        component_type = "Test"

        def render(self, props, surface_id, app_instance, comp_id="unknown"):
            return None

    class _NotReadyWidget(_FakeWidget):
        def __init__(self):
            super().__init__()
            self._w = 0
            self._h = 0
            self._visible = True

        def width(self):
            return self._w

        def height(self):
            return self._h

    widget = _NotReadyWidget()
    timer_calls = []
    fade_calls = []

    def _single_shot(delay, fn):
        timer_calls.append(delay)
        if delay == 16:
            widget._w = 120
            widget._h = 32
        fn()

    monkeypatch.setattr(base_renderer_mod, "QTimer", type("Timer", (), {"singleShot": staticmethod(_single_shot)}))
    monkeypatch.setattr(base_renderer_mod, "fade_in", lambda *args, **kwargs: fade_calls.append(kwargs))

    renderer = _Renderer()
    renderer.apply_declared_animation(widget, {"name": "fade_in", "duration": 210})

    assert timer_calls[:2] == [0, 16]
    assert fade_calls == [{"duration": 210, "start": 0.0, "end": 1.0, "loop_count": 1}]


def test_base_renderer_skips_animation_when_widget_deleted_before_timer(monkeypatch):
    class _Renderer(base_renderer_mod.BaseRenderer):
        component_type = "Test"

        def render(self, props, surface_id, app_instance, comp_id="unknown"):
            return None

    class _DeletedWidget(_FakeWidget):
        def width(self):
            raise RuntimeError("already deleted")

        def height(self):
            raise RuntimeError("already deleted")

    widget = _DeletedWidget()
    fade_calls = []

    monkeypatch.setattr(base_renderer_mod, "QTimer", type("Timer", (), {"singleShot": staticmethod(lambda delay, fn: fn())}))
    monkeypatch.setattr(base_renderer_mod, "fade_in", lambda *args, **kwargs: fade_calls.append(kwargs))

    renderer = _Renderer()
    renderer.apply_declared_animation(widget, {"name": "fade_in", "duration": 210})

    assert fade_calls == []
