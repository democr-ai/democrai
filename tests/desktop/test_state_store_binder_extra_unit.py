from __future__ import annotations

from types import SimpleNamespace

import clients.qtdesktop.state as state_mod
from clients.qtdesktop.state import Binder, Binding, Store
from PySide6.QtCore import QObject, Signal


class _Widget(QObject):
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.value = None


def test_state_helper_functions_cover_paths_and_merges():
    assert state_mod._path_to_segments("") == []
    assert state_mod._path_to_segments("/a/0/b") == ["a", 0, "b"]
    assert state_mod._path_to_segments("a.b.2") == ["a", "b", 2]
    assert state_mod._segments_to_path([]) == "/"
    assert state_mod._segments_to_path(["a", 1, "b"]) == "/a/1/b"
    assert state_mod._flatten_paths({"a": {"b": [1, {"c": 2}]}}) == [
        "/a",
        "/a/b",
        "/a/b/0",
        "/a/b/1",
        "/a/b/1/c",
    ]
    assert state_mod._flatten_paths([{"a": 1}]) == ["/0", "/0/a"]
    assert state_mod._flatten_paths("x") == ["/"]

    original = {"a": [1, {"b": 2}]}
    copied = state_mod._deep_copy(original)
    copied["a"][1]["b"] = 9
    assert original == {"a": [1, {"b": 2}]}

    merged = state_mod._deep_merge({"a": {"b": 1}, "c": 1}, {"a": {"d": 2}, "c": [1]})
    assert merged == {"a": {"b": 1, "d": 2}, "c": [1]}


def test_store_internal_paths_scopes_snapshot_and_signals():
    store = Store(initial={"/boot": 1})
    changed = []
    scoped = []
    key_changes = []
    store.changed.connect(lambda path, value: changed.append((path, value)))
    store.scoped_changed.connect(lambda scope, path, value: scoped.append((scope, path, value)))
    store.signal_for("/items/0/name").connect(lambda value: key_changes.append(value))

    assert store._normalize_scope_and_path("$global.user.name", "auto") == ("global", "/user/name")
    assert store._normalize_scope_and_path("$state.filters.q", "auto") == ("page", "/filters/q")
    assert store._normalize_scope_and_path("plain.path", "weird") == ("auto", "/plain/path")
    assert store._scopes_for_read("auto") == ["page", "global"]

    store.set("/items/0/name", "Fabio", "page")
    store.set("/items/1/name", "Ada", "page")
    store.set("/", {"root": {"ok": True}}, "global")
    store.set("/settings/theme", "dark", "global")
    store.set("/items/1/extra/0", "x", "page")
    store._set_in_scope("page", "/items/0", {"name": "Override"})
    store._set_in_scope("page", "/broken/0/value", "nope")
    store._data["page"]["not_list"] = {}
    store._set_in_scope("page", "/not_list/0", "nope")

    assert store.get("/boot", scope="page") == 1
    assert store.get("/items/0/name", scope="page") == "Override"
    assert store.get("/items/1/extra/0", scope="page") == "x"
    assert store.get("/settings/theme", scope="global") == "dark"
    assert store.get_all()["root"]["ok"] is True
    assert store._get_from_scope("page", "/missing", "fallback") == "fallback"
    assert store._get_from_scope("page", "/items/9", "fallback") == "fallback"

    store.update({"status": "ok"}, "global")
    store.merge({"nested": {"items": [1, 2]}}, "page")
    store.merge("ignored", "page")
    snapshot = store.snapshot(("missing", "global", "page"))
    assert snapshot["nested"]["items"] == [1, 2]
    assert key_changes
    assert changed
    assert scoped

    store.clear_scope("page")
    assert store.get("/items/0/name", default=None, scope="page") is None
    store.clear_scope("weird")
    sig1 = store.signal_for("status")
    sig2 = store.signal_for("/status")
    assert sig1 is sig2


def test_binder_covers_bind_bind_many_and_guard_paths(monkeypatch):
    monkeypatch.setattr(state_mod.shiboken6, "isValid", lambda obj: getattr(obj, "_alive", True))

    store = Store()
    widget = _Widget()
    widget._alive = True
    events = []
    binder = Binder(store)

    binding = Binding(
        key="/value",
        widget=widget,
        set_widget=lambda value: setattr(widget, "value", value),
        get_widget=lambda: widget.value,
        widget_signal=widget.changed,
        transform_from_store=lambda value: f"from:{value}",
        transform_to_store=lambda value: f"to:{value}",
    )

    store.set("/value", "initial")
    binder.bind(binding)
    assert widget.value == "from:initial"

    store.set("/value", "next")
    assert widget.value == "from:next"

    widget.value = "typed"
    widget.changed.emit()
    assert store.get("/value") == "to:typed"

    binder.bind_many(["/value"], lambda: events.append("immediate"), immediate=True)
    binder.bind_many(["/value"], lambda: events.append("deferred"), owner=widget, immediate=False)
    assert events == ["immediate"]
    store.set("/value", "again")
    assert "deferred" in events

    binder._guard.add("/value")
    binder._on_store_changed(binding, "ignored")
    binder._on_widget_changed(binding)
    binder._guard.clear()
    assert store.get("/value") == "again"

    invalid_events = []
    invalid_binding = Binding(
        key="/other",
        widget=SimpleNamespace(),
        set_widget=lambda value: invalid_events.append(("set", value)),
        get_widget=lambda: invalid_events.append("get") or "x",
    )
    proxy = state_mod._BindingProxy(binder, invalid_binding)
    monkeypatch.setattr(state_mod.shiboken6, "isValid", lambda obj: False)
    proxy.on_store_value("ignored")
    proxy.on_widget_changed()
    assert invalid_events == []
