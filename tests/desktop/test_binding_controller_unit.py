from __future__ import annotations

from types import SimpleNamespace

import clients.qtdesktop.ui.bindings as bindings_mod
from clients.qtdesktop.ui.bindings import BindingController
from PySide6.QtCore import QObject


class _Signal:
    def __init__(self):
        self.callbacks = []

    def connect(self, callback):
        self.callbacks.append(callback)


class _Timer:
    def __init__(self, parent=None):
        self.parent = parent
        self.single_shot = False
        self.interval = None
        self._active = False
        self.timeout = _Signal()

    def setSingleShot(self, value):
        self.single_shot = value

    def setInterval(self, value):
        self.interval = value

    def isActive(self):
        return self._active

    def start(self):
        self._active = True


class _Store:
    def __init__(self):
        self.values = {}
        self.calls = []

    def get(self, key, default=None, scope="page"):
        return self.values.get((scope, key), default)

    def set(self, key, value, scope="page"):
        self.values[(scope, key)] = value
        self.calls.append((scope, key, value))


class _Binder:
    def __init__(self):
        self.calls = []

    def bind_many(self, paths, callback, owner=None, immediate=False):
        self.calls.append((tuple(paths), owner, immediate, callback))


class _Window(QObject):
    def __init__(self):
        super().__init__()
        self.store = _Store()
        self.binder = _Binder()
        self._surface_roots = {"main": "root-1"}
        self._action_calls = []
        self._render_calls = []
        self._component_calls = []
        self._widget_index = {}
        self._action = SimpleNamespace(send_binding_action=lambda **kwargs: self._action_calls.append(kwargs))
        self._surfaces = SimpleNamespace(
            render_tree=lambda surface_id, root_id: self._render_calls.append((surface_id, root_id)),
            rerender_component=lambda comp_id: self._component_calls.append(comp_id),
        )

    def _get_widget_by_id(self, comp_id):
        return self._widget_index.get(comp_id)


def test_binding_controller_normalize_resolve_and_inline_keys(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    window = _Window()
    controller = BindingController(window)
    window.store.set("/user/name", "Fabio", "global")

    literal = controller.normalize_spec({"type": "literal", "value": 7})
    store = controller.normalize_spec({"type": "store", "path": "/user/name", "scope": "global", "default": "x"})
    action = controller.normalize_spec({"type": "action", "name": "demo.fetch", "args": {"id": 1}, "default": []})

    assert literal is not None and literal.kind == "literal"
    assert store is not None and store.kind == "store"
    assert action is not None and action.kind == "action"
    assert controller.resolve_value({"type": "store", "path": "/user/name", "scope": "global"}, None) == "Fabio"
    assert controller.resolve_value("{{name}}", {"name": "Inline"}) == "Inline"
    assert controller.resolve_value("$item.kind", {"kind": "alpha"}) == "alpha"
    assert controller._extract_inline_store_key("{{ user.name }}", None) == "/user.name"
    assert controller._extract_inline_store_key("{{name}}", {"name": "Inline"}) is None


def test_binding_controller_prepare_action_binding_deduplicates_and_caches(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.uuid, "uuid4", lambda: "req-1")
    window = _Window()
    controller = BindingController(window)

    comp_def = {
        "component": {
            "Text": {
                "value": {
                    "type": "action",
                    "name": "demo.fetch",
                    "args": {"slug": "{{slug}}"},
                    "default": ["loading"],
                }
            }
        }
    }

    controller.prepare_component_bindings(comp_def, surface_id="main", comp_id="card", item={"slug": "a"})
    controller.prepare_component_bindings(comp_def, surface_id="main", comp_id="card", item={"slug": "a"})

    assert len(window._action_calls) == 1
    sent = window._action_calls[0]
    assert sent["request_id"] == "req-1"
    assert sent["name"] == "demo.fetch"
    assert sent["context"] == {"slug": "a"}
    cache_path = sent["binding_id"]
    assert cache_path.startswith("/_bindings/actions/")
    assert window.store.get(cache_path, scope="page") == ["loading"]


def test_binding_controller_handles_action_result_page_epoch_and_reset(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.uuid, "uuid4", lambda: "req-1")
    window = _Window()
    controller = BindingController(window)

    spec = {
        "component": {
            "Text": {
                "value": {
                    "type": "action",
                    "name": "demo.fetch",
                    "args": {"slug": "x"},
                    "default": "loading",
                }
            }
        }
    }
    controller.prepare_component_bindings(spec, surface_id="main", comp_id="card")
    cache_path = window._action_calls[0]["binding_id"]

    controller.handle_action_result({"requestId": "req-1", "ok": True, "value": "done"})
    assert window.store.get(cache_path, scope="page") == "done"

    monkeypatch.setattr(bindings_mod.uuid, "uuid4", lambda: "req-2")
    controller.prepare_component_bindings(spec, surface_id="main", comp_id="card")
    controller._schedule_component_rerender("card")
    controller._schedule_rerender("main")
    controller.on_page_scope_reset()
    controller.handle_action_result({"requestId": "req-2", "ok": True, "value": "stale"})
    assert window.store.get(cache_path, scope="page") == "done"
    assert controller._pending_component_rerenders == set()
    assert controller._pending_rerenders == set()


def test_binding_controller_bind_component_and_flush_rerenders(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.shiboken6, "isValid", lambda widget: True)
    window = _Window()
    controller = BindingController(window)

    class _Renderer:
        PROPERTY = "property"
        COMPONENT = "component"

        def binding_strategies(self):
            return {
                "text": self.PROPERTY,
                "children": self.COMPONENT,
            }

        def update_widget_property(self, widget, prop_name, value):
            widget.updated = (prop_name, value)

    widget = SimpleNamespace(updated=None)
    window._widget_index["card"] = widget
    comp_def = {
        "id": "card",
        "component": {
                "Text": {
                    "text": "{{title}}",
                    "children": [{"type": "store", "path": "/items"}],
                    "extra": {"type": "store", "path": "/status"},
                }
            },
        "show_if": {
            "conditions": [
                {"left": {"type": "store", "path": "/flag"}, "op": "==", "right": True}
            ]
        },
    }

    controller.bind_component(
        widget,
        surface_id="main",
        comp_id="card",
        comp_def=comp_def,
        renderer=_Renderer(),
        item=None,
    )

    watched = {paths for paths, _owner, _immediate, _callback in window.binder.calls}
    assert ("/title",) in watched
    assert ("/items",) in watched
    assert ("/status",) in watched
    assert all("/flag" not in paths for paths in watched)

    controller._schedule_component_rerender("card")
    controller._schedule_rerender("main")
    controller._flush_rerenders()

    assert window._component_calls == ["card"]
    assert window._render_calls == [("main", "root-1")]


def test_binding_controller_covers_helper_resolution_and_recursive_collection(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    original_dumps = bindings_mod.json.dumps
    calls = {"count": 0}

    def _flaky_dumps(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TypeError("boom")
        return original_dumps(*args, **kwargs)

    monkeypatch.setattr(bindings_mod.json, "dumps", _flaky_dumps)
    assert bindings_mod._stable_json(object()).startswith('"')

    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    window = _Window()
    controller = BindingController(window)
    window.store.set("title", "FromStore", "auto")
    action_spec = bindings_mod.BoundSpec(kind="action", name="", default="fallback")

    assert controller.resolve_value(["{{title}}", {"nested": "$item.slug"}, 3], {"slug": "x"}) == [
        "FromStore",
        {"nested": "x"},
        3,
    ]
    assert controller._resolve_spec(bindings_mod.BoundSpec(kind="literal", value=9), None) == 9
    assert controller._resolve_spec(action_spec, None) == "fallback"
    assert controller._resolve_string("Hello $item.name {{name}}", {"name": "Ada"}) == "Hello Ada Ada"
    assert controller._resolve_string("plain", None) == "plain"
    assert controller._collect_specs([{"type": "literal", "value": 1}, {"type": "store", "path": "/x"}])[1].kind == "store"
    watch_paths = controller._collect_watch_paths(
        {"value": {"type": "action", "name": "demo.fetch", "args": {"slug": "x"}}},
        surface_id="main",
        comp_id="card",
        item=None,
    )
    assert next(iter(watch_paths)).startswith("/_bindings/actions/")
    assert controller._extract_component_props({"component": {"Text": "bad"}}) == {}
    assert controller._extract_component_props({"component": []}) == {}
    assert controller._extract_inline_store_key("plain", None) is None


def test_binding_controller_prepare_bind_component_and_action_result_edges(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.uuid, "uuid4", lambda: "req-extra")
    monkeypatch.setattr(bindings_mod.shiboken6, "isValid", lambda widget: getattr(widget, "_alive", True))
    window = _Window()
    controller = BindingController(window)

    class _Renderer:
        PROPERTY = "property"
        COMPONENT = "component"

        def binding_strategies(self):
            return {
                "unused": self.PROPERTY,
                "empty": self.PROPERTY,
                "layout": "surface",
                "show_if": self.COMPONENT,
            }

        def update_widget_property(self, widget, prop_name, value):
            widget.updated = (prop_name, value)

    invalid_widget = SimpleNamespace(_alive=False)
    comp_def = {
        "component": {
            "Text": {
                "value": {"type": "literal", "value": 1},
                "layout": "{{layout.path}}",
                "empty": "plain",
            }
        },
        "show_if": "{{visible}}",
        "hide_if": "plain",
        "children": [],
    }

    controller.prepare_component_bindings(
        {"component": {"Text": {"value": {"type": "store", "path": "/x"}}}},
        surface_id="main",
        comp_id="card",
    )
    assert window._action_calls == []

    controller.bind_component(
        invalid_widget,
        surface_id="main",
        comp_id="card",
        comp_def=comp_def,
        renderer=_Renderer(),
    )
    assert window.binder.calls == []

    widget = SimpleNamespace(updated=None, _alive=True)
    window._widget_index["card"] = widget
    controller.bind_component(
        widget,
        surface_id="main",
        comp_id="card",
        comp_def=comp_def,
        renderer=_Renderer(),
    )

    watched = [(paths, owner) for paths, owner, _immediate, _callback in window.binder.calls]
    assert (("/layout.path",), widget) in watched
    assert not any(paths == ("/visible",) and owner is widget for paths, owner in watched)

    controller.handle_action_result({"requestId": "missing", "ok": True, "value": "ignored"})
    controller._pending_actions["stale"] = {
        "cache_path": "/_bindings/actions/x",
        "cache_scope": "page",
        "default": "default",
        "page_epoch": -1,
    }
    controller.handle_action_result({"requestId": "stale", "ok": True, "value": "late"})
    controller._pending_actions["failed"] = {
        "cache_path": "/_bindings/actions/y",
        "cache_scope": "global",
        "default": "default",
        "page_epoch": controller._page_epoch,
    }
    controller.handle_action_result({"requestId": "failed", "ok": False, "value": "late"})
    assert window.store.get("/_bindings/actions/y", scope="global") == "default"


def test_binding_controller_apply_property_binding_and_schedule_guards(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    valid = {"value": True}
    monkeypatch.setattr(bindings_mod.shiboken6, "isValid", lambda widget: valid["value"])
    window = _Window()
    controller = BindingController(window)
    renderer_calls = []
    renderer = SimpleNamespace(update_widget_property=lambda widget, prop_name, value: renderer_calls.append((widget, prop_name, value)))
    widget = SimpleNamespace()

    valid["value"] = False
    controller._apply_property_binding(widget, renderer, "text", "{{name}}", {"name": "Ada"})
    assert renderer_calls == []

    valid["value"] = True
    controller._apply_property_binding(widget, renderer, "text", "{{name}}", {"name": "Ada"})
    assert renderer_calls == [(widget, "text", "Ada")]

    controller._rerender_timer._active = True
    controller._schedule_rerender("main")
    controller._schedule_component_rerender("card")
    assert controller._pending_rerenders == {"main"}
    assert controller._pending_component_rerenders == {"card"}

    window._surface_roots.clear()
    controller._rerender_surface("ghost")
    controller._flush_rerenders()
    assert window._component_calls == ["card"]
    assert window._render_calls == []


def test_binding_controller_ensure_action_request_handles_existing_cache_and_non_dict_context(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.uuid, "uuid4", lambda: "req-non-dict")
    window = _Window()
    controller = BindingController(window)
    spec = bindings_mod.BoundSpec(
        kind="action",
        name="demo.fetch",
        args={"slug": "$item.slug"},
        default="loading",
        cache_scope="global",
        cache_path="/_bindings/actions/manual",
    )

    original_resolve_value_for_surface = controller.resolve_value_for_surface
    controller.resolve_value_for_surface = (
        lambda data, surface_id=None, item=None: "not-a-dict"
    )
    controller._ensure_action_request(spec, None, {"slug": "x"})
    assert window.store.get("/_bindings/actions/manual", scope="global") == "loading"
    assert window._action_calls[0]["context"] == {}

    controller._pending_actions["dup"] = {"fingerprint": bindings_mod._stable_json({"name": "demo.fetch", "args": "not-a-dict", "cache_path": "/_bindings/actions/manual"})}
    controller._ensure_action_request(spec, None, {"slug": "x"})
    assert len(window._action_calls) == 1

    controller.resolve_value_for_surface = original_resolve_value_for_surface


def test_binding_controller_covers_remaining_action_and_string_edges(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    window = _Window()
    controller = BindingController(window)

    cache_spec = bindings_mod.BoundSpec(
        kind="action",
        name="demo.fetch",
        args={"slug": "x"},
        default="loading",
        cache_scope="page",
    )
    resolved_cache_spec = controller._with_action_cache(cache_spec, "main", "card", None)
    window.store.set(resolved_cache_spec.cache_path, "done", resolved_cache_spec.cache_scope)
    assert controller._resolve_spec(cache_spec, None) == "done"

    controller._pending_actions["no-cache"] = {
        "cache_path": None,
        "cache_scope": "page",
        "default": "fallback",
        "page_epoch": controller._page_epoch,
    }
    store_call_count = len(window.store.calls)
    controller.handle_action_result({"requestId": "no-cache", "ok": True, "value": "ignored"})
    assert len(window.store.calls) == store_call_count

    assert controller._collect_specs([]) == []
    assert controller._resolve_string("$item.missing {{name}}", {"name": "Ada"}) == "$item.missing Ada"

    controller._rerender_timer._active = False
    controller._schedule_rerender("main")
    assert controller._rerender_timer._active is True
