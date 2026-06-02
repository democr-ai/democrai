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


class _Binder:
    def __init__(self):
        self.calls = []

    def bind_many(self, paths, callback, owner=None, immediate=False):
        self.calls.append((tuple(paths), owner, immediate, callback))


class _Window(QObject):
    def __init__(self):
        super().__init__()
        self.binder = _Binder()
        self.store = SimpleNamespace(get=lambda key, default=None, scope="page": default)
        self._action = SimpleNamespace(send_binding_action=lambda **kwargs: None)
        self._surface_roots = {"main": "root"}
        self._surfaces = SimpleNamespace(render_tree=lambda *_: None, rerender_component=lambda *_: None)
        self._widget_index = {}

    def _get_widget_by_id(self, comp_id):
        return self._widget_index.get(comp_id)


class _Renderer:
    PROPERTY = "property"
    COMPONENT = "component"

    def binding_strategies(self):
        return {
            "children": self.COMPONENT,
            "style": self.PROPERTY,
        }

    def update_widget_property(self, widget, prop_name, value):
        widget.updated = (prop_name, value)


def test_inline_child_property_binding_is_owned_by_child_not_parent(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.shiboken6, "isValid", lambda widget: True)
    window = _Window()
    controller = BindingController(window)

    inline_grid = {
        "id": "inline_grid",
        "component": {
            "Grid": {
                "style": {
                    "type": "store",
                    "path": "/child/style",
                    "scope": "page",
                    "default": "margin-top: 4px;",
                }
            }
        },
        "children": {"explicitList": []},
    }
    parent = {
        "id": "tabs",
        "component": {"Tabs": {}},
        "children": {"explicitList": [inline_grid]},
    }

    controller.bind_component(
        QObject(),
        surface_id="main",
        comp_id="tabs",
        comp_def=parent,
        renderer=_Renderer(),
        item=None,
    )

    watched = {paths for paths, _owner, _immediate, _callback in window.binder.calls}
    assert ("/child/style",) not in watched

    controller.bind_component(
        SimpleNamespace(updated=None),
        surface_id="main",
        comp_id="inline_grid",
        comp_def=inline_grid,
        renderer=_Renderer(),
        item=None,
    )

    watched = {paths for paths, _owner, _immediate, _callback in window.binder.calls}
    assert ("/child/style",) in watched


def test_direct_children_collection_binding_still_belongs_to_parent(monkeypatch):
    monkeypatch.setattr(bindings_mod, "QTimer", _Timer)
    monkeypatch.setattr(bindings_mod.shiboken6, "isValid", lambda widget: True)
    window = _Window()
    controller = BindingController(window)

    parent = {
        "id": "dynamic_parent",
        "component": {"Column": {}},
        "children": {
            "explicitList": [
                {
                    "type": "store",
                    "path": "/parent/children",
                    "scope": "page",
                    "default": [],
                }
            ]
        },
    }

    controller.bind_component(
        QObject(),
        surface_id="main",
        comp_id="dynamic_parent",
        comp_def=parent,
        renderer=_Renderer(),
        item=None,
    )

    watched = {paths for paths, _owner, _immediate, _callback in window.binder.calls}
    assert ("/parent/children",) in watched
