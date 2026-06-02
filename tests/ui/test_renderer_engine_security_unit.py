from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QApplication

from clients.qtdesktop.ui.controllers.renderer_engine import RendererEngine
from clients.qtdesktop.ui.renderers.base import BaseRenderer


@pytest.fixture(autouse=True)
def _qapp():
    _ = QApplication.instance() or QApplication([])


class _Widget:
    def __init__(self, comp_id):
        self.comp_id = comp_id
        self.children = []
        self.properties = {}

    def layout(self):
        return None

    def addWidget(self, widget):
        self.children.append(widget)

    def setProperty(self, name, value):
        self.properties[name] = value


class _Renderer(BaseRenderer):
    def __init__(self, rendered_ids):
        self.rendered_ids = rendered_ids

    def render(self, props, surface_id, app_instance, comp_id="unknown"):
        self.rendered_ids.append(comp_id)
        return _Widget(comp_id)


class _TabWidget(_Widget):
    def __init__(self, comp_id):
        super().__init__(comp_id)
        self.tabs = []

    def addTab(self, widget, label):
        self.tabs.append((widget, label))


class _TabsRenderer(BaseRenderer):
    def __init__(self, rendered_ids):
        self.rendered_ids = rendered_ids

    def render(self, props, surface_id, app_instance, comp_id="unknown"):
        self.rendered_ids.append(comp_id)
        return _TabWidget(comp_id)


class _DialogRenderer(BaseRenderer):
    def __init__(self, rendered_ids):
        self.rendered_ids = rendered_ids

    def render(self, props, surface_id, app_instance, comp_id="unknown"):
        self.rendered_ids.append(comp_id)
        return _Widget(comp_id)


class _Host:
    def __init__(self, registry):
        self.registry = registry
        self.bindings = None
        self.store = SimpleNamespace(get=lambda *args, **kwargs: None, set=lambda *args, **kwargs: None)
        self.debugs = []
        self.errors = []

    def _debug(self, message):
        self.debugs.append(message)

    def _error(self, message):
        self.errors.append(message)


class _Bindings:
    def __init__(self, values):
        self.values = values

    def normalize_spec(self, value, **_kwargs):
        if isinstance(value, dict) and value.get("type") in {"store", "action", "literal"}:
            return value
        return None

    def resolve_value(self, value, item=None):
        if isinstance(value, dict) and "path" in value:
            return self.values.get(value["path"])
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            key = value[2:-2].strip()
            if item and key in item:
                return item[key]
        return value

    def resolve_value_for_surface(self, value, surface_id=None, item=None, allow_implicit_path=True):
        del surface_id
        del allow_implicit_path
        return self.resolve_value(value, item=item)

    def prepare_component_bindings(self, *args, **kwargs):
        return None

    def bind_component(self, *args, **kwargs):
        return None


def _component(comp_id, *, props=None, children=None):
    return {
        "id": comp_id,
        "component": {"Text": props or {}},
        "children": {"explicitList": children or []},
    }


def _typed_component(comp_id, ctype, *, props=None, children=None):
    return {
        "id": comp_id,
        "component": {ctype: props or {}},
        "children": {"explicitList": children or []},
    }


def test_renderer_engine_skips_unauthorized_children_in_render_tree():
    rendered_ids = []
    renderer = _Renderer(rendered_ids)
    host = _Host({"Text": renderer})
    engine = RendererEngine(host)

    surfaces = {
        "main": {
            "components": {
                "parent": _component("parent", children=["allowed", "blocked"]),
                "allowed": _component("allowed"),
                "blocked": _component("blocked", props={"required_permissions": ["admin.view"]}),
            }
        }
    }

    runtime = SimpleNamespace(user_permissions=[], user_role="User", bindings=None, store=host.store)
    widget = engine.build_widget("main", surfaces, comp_id="parent", app_instance=runtime)

    assert widget is not None
    assert rendered_ids == ["parent", "allowed"]


def test_renderer_engine_skips_children_hidden_by_compound_conditions():
    rendered_ids = []
    renderer = _Renderer(rendered_ids)
    host = _Host({"Text": renderer})
    engine = RendererEngine(host)

    surfaces = {
        "main": {
            "components": {
                "parent": _component("parent", children=["visible", "conditional"]),
                "visible": _component("visible"),
                "conditional": _component(
                    "conditional",
                    props={
                        "show_if": {
                            "mode": "AND",
                            "conditions": [
                                {"left": {"type": "store", "path": "/flag"}, "op": "==", "right": True},
                                {"left": "{{kind}}", "op": "==", "right": "safe"},
                            ],
                        },
                        "hide_if": {
                            "mode": "OR",
                            "conditions": [
                                {"left": {"type": "store", "path": "/blocked"}, "op": "==", "right": True},
                            ],
                        },
                    },
                ),
            }
        }
    }

    bindings = _Bindings({"/flag": True, "/blocked": True})
    runtime = SimpleNamespace(
        user_permissions=[],
        user_role="User",
        bindings=bindings,
        store=host.store,
    )

    widget = engine.build_widget(
        "main",
        surfaces,
        comp_id="parent",
        app_instance=runtime,
        item={"kind": "safe"},
    )

    assert widget is not None
    assert rendered_ids == ["parent", "visible"]


def test_renderer_engine_skips_inline_nested_children_when_not_authorized():
    rendered_ids = []
    renderer = _Renderer(rendered_ids)
    host = _Host({"Text": renderer})
    engine = RendererEngine(host)

    parent = _component(
        "parent",
        children=[
            _component("inline-visible"),
            _component("inline-blocked", props={"required_permissions": ["admin.view"]}),
            _component(
                "inline-hidden",
                props={
                    "show_if": {
                        "mode": "AND",
                        "conditions": [
                            {"left": {"type": "store", "path": "/flag"}, "op": "==", "right": True},
                            {"left": "{{state}}", "op": "==", "right": "allowed"},
                        ],
                    }
                },
            ),
        ],
    )
    surfaces = {"main": {"components": {"parent": parent}}}

    runtime = SimpleNamespace(
        user_permissions=[],
        user_role="User",
        bindings=_Bindings({"/flag": False}),
        store=host.store,
    )
    widget = engine.build_widget(
        "main",
        surfaces,
        comp_id="parent",
        app_instance=runtime,
        item={"state": "allowed"},
    )

    assert widget is not None
    assert rendered_ids == ["parent", "inline-visible"]


def test_renderer_engine_skips_inline_children_when_bindings_are_missing_or_null():
    rendered_ids = []
    renderer = _Renderer(rendered_ids)
    host = _Host({"Text": renderer})
    engine = RendererEngine(host)

    parent = _component(
        "parent",
        children=[
            _component(
                "missing-binding",
                props={
                    "show_if": {
                        "mode": "AND",
                        "conditions": [
                            {"left": {"type": "store", "path": "/missing"}, "op": "==", "right": True},
                        ],
                    }
                },
            ),
            _component(
                "null-binding",
                props={
                    "show_if": {
                        "mode": "OR",
                        "conditions": [
                            {"left": {"type": "store", "path": "/nullable"}, "op": ">=", "right": 1},
                            {"left": "{{score}}", "op": ">=", "right": 5},
                        ],
                    }
                },
            ),
        ],
    )
    surfaces = {"main": {"components": {"parent": parent}}}

    runtime = SimpleNamespace(
        user_permissions=[],
        user_role="User",
        bindings=_Bindings({"/nullable": None}),
        store=host.store,
    )
    widget = engine.build_widget(
        "main",
        surfaces,
        comp_id="parent",
        app_instance=runtime,
        item={"score": None},
    )

    assert widget is not None
    assert rendered_ids == ["parent"]


def test_renderer_engine_skips_unauthorized_tabs_and_preserves_allowed_labels(monkeypatch):
    rendered_ids = []
    host = _Host({"Text": _Renderer(rendered_ids), "Tabs": _TabsRenderer(rendered_ids)})
    engine = RendererEngine(host)
    monkeypatch.setattr("clients.qtdesktop.ui.controllers.renderer_engine.QTabWidget", _TabWidget)

    tabs = _typed_component(
        "tabs",
        "Tabs",
        props={
            "tabs": [
                {"id": "allowed-tab", "label": "Allowed"},
                {"id": "blocked-tab", "label": "Blocked"},
            ]
        },
        children=["allowed-tab", "blocked-tab"],
    )
    surfaces = {
        "main": {
            "components": {
                "tabs": tabs,
                "allowed-tab": _component("allowed-tab"),
                "blocked-tab": _component(
                    "blocked-tab",
                    props={"required_permissions": ["admin.view"]},
                ),
            }
        }
    }

    runtime = SimpleNamespace(user_permissions=[], user_role="User", bindings=None, store=host.store)
    widget = engine.build_widget("main", surfaces, comp_id="tabs", app_instance=runtime)

    assert isinstance(widget, _TabWidget)
    assert [label for _tab_widget, label in widget.tabs] == ["Allowed", "Blocked"]
    assert rendered_ids == ["tabs", "allowed-tab"]


def test_renderer_engine_does_not_mount_dialog_children_into_parent_layout():
    rendered_ids = []
    host = _Host(
        {
            "Text": _Renderer(rendered_ids),
            "Dialog": _DialogRenderer(rendered_ids),
        }
    )
    engine = RendererEngine(host)

    parent = _component("parent", children=["visible", "modal"])
    surfaces = {
        "main": {
            "components": {
                "parent": parent,
                "visible": _component("visible"),
                "modal": _typed_component("modal", "Dialog"),
            }
        }
    }

    runtime = SimpleNamespace(user_permissions=[], user_role="User", bindings=None, store=host.store)
    widget = engine.build_widget("main", surfaces, comp_id="parent", app_instance=runtime)

    assert widget is not None
    assert [child.comp_id for child in widget.children] == ["visible"]
    assert rendered_ids == ["parent", "visible", "modal"]


def test_renderer_engine_does_not_treat_plain_item_dict_with_path_as_store_spec():
    host = _Host({"Text": _Renderer([])})
    bindings = _Bindings({"local_counter": 40})
    host.bindings = bindings
    engine = RendererEngine(host)

    payload = {"id": "overview", "label": "Overview", "path": "/components"}
    resolved = engine.resolve_bindings(payload, item=payload)

    assert isinstance(resolved, dict)
    assert resolved["id"] == "overview"
    assert resolved["label"] == "Overview"
    assert resolved["path"] == "/components"


def test_renderer_engine_keeps_action_context_path_dict_for_list_navigation():
    host = _Host({"Text": _Renderer([])})
    bindings = _Bindings({})
    host.bindings = bindings
    engine = RendererEngine(host)

    payload = {"path": "{{path}}"}
    item = {"path": "/components/index"}
    resolved = engine.resolve_bindings(payload, item=item)

    assert isinstance(resolved, dict)
    assert resolved["path"] == "/components/index"
