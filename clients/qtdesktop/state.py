from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

import shiboken6
from PySide6.QtCore import QObject, Slot

from .state_store import (
    Store,
    _deep_copy,
    _deep_merge,
    _flatten_paths,
    _path_to_segments,
    _segments_to_path,
)


@dataclass(frozen=True)
class Binding:
    key: str
    widget: QObject
    set_widget: Callable[[Any], None]
    get_widget: Optional[Callable[[], Any]] = None
    widget_signal: Optional[Any] = None
    transform_from_store: Callable[[Any], Any] = lambda v: v
    transform_to_store: Callable[[Any], Any] = lambda v: v


class _CallbackProxy(QObject):
    def __init__(self, callback, parent=None):
        super().__init__(parent)
        self._callback = callback

    @Slot(object)
    def on_value(self, _value):
        cb = self._callback
        if cb is not None:
            cb()


class _BindingProxy(QObject):
    def __init__(self, binder, binding, parent=None):
        super().__init__(parent)
        self._binder = binder
        self._binding = binding

    @Slot(object)
    def on_store_value(self, value):
        b = self._binding
        if b.widget is not None and not shiboken6.isValid(b.widget):
            return
        self._binder._on_store_changed(b, value)

    @Slot()
    def on_widget_changed(self):
        b = self._binding
        if b.widget is not None and not shiboken6.isValid(b.widget):
            return
        self._binder._on_widget_changed(b)


class Binder(QObject):
    """Bind store keys to widgets (one-way or two-way)."""

    def __init__(self, store: Store, parent: QObject | None = None):
        super().__init__(parent)
        self._store = store
        self._bindings: list[Binding] = []
        self._guard: set[str] = set()
        self._proxies = []

    def bind(self, b: Binding) -> None:
        _, normalized_key = self._store._normalize_scope_and_path(b.key, "auto")
        normalized = Binding(
            key=normalized_key,
            widget=b.widget,
            set_widget=b.set_widget,
            get_widget=b.get_widget,
            widget_signal=b.widget_signal,
            transform_from_store=b.transform_from_store,
            transform_to_store=b.transform_to_store,
        )
        self._bindings.append(normalized)

        v = self._store.get(normalized.key, None, "auto")
        normalized.set_widget(normalized.transform_from_store(v))

        owner = normalized.widget if isinstance(normalized.widget, QObject) else self
        proxy = _BindingProxy(self, normalized, parent=owner)
        self._proxies.append(proxy)

        self._store.signal_for(normalized.key).connect(proxy.on_store_value)

        if normalized.widget_signal is not None and normalized.get_widget is not None:
            normalized.widget_signal.connect(proxy.on_widget_changed)

    def bind_many(
        self,
        keys: list[str],
        callback: Callable[[], None],
        owner: QObject | None = None,
        *,
        immediate: bool = True,
    ) -> None:
        if immediate:
            callback()

        if owner is None:
            owner = self

        proxy = _CallbackProxy(callback, parent=owner)

        for k in keys:
            _, normalized_key = self._store._normalize_scope_and_path(k, "auto")
            sig = self._store.signal_for(normalized_key)
            sig.connect(proxy.on_value)

    @Slot(object)
    def _on_store_changed(self, b: Binding, value: Any) -> None:
        if b.key in self._guard:
            return
        if b.widget is not None and not shiboken6.isValid(b.widget):
            return
        b.set_widget(b.transform_from_store(value))

    @Slot()
    def _on_widget_changed(self, b: Binding) -> None:
        if b.key in self._guard:
            return
        self._guard.add(b.key)
        try:
            raw = b.get_widget()
            self._store.set(b.key, b.transform_to_store(raw))
        finally:
            self._guard.remove(b.key)
