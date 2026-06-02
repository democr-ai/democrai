from types import SimpleNamespace

from PySide6.QtWidgets import QApplication, QWidget

import clients.qtdesktop.ui.renderers.domains.layout.tabs as tabs_mod
from clients.qtdesktop.ui.renderers.domains.layout.tabs import TabsRenderer


def test_tabs_renderer_route_only_tab_renders_in_surface_host(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    emitted = []
    monkeypatch.setattr(
        tabs_mod,
        "emit_action",
        lambda app, name, context, surface_id, comp_id: emitted.append(
            (name, context, surface_id, comp_id)
        ),
    )

    renderer = TabsRenderer()
    app = SimpleNamespace(
        store=SimpleNamespace(get=lambda path, default=None, scope="global": "/components/_complex/tabs"),
    )
    props = {
        "tabs": [
            {"id": "tab_route", "label": "Route", "route": "/components/_complex/card"},
            {"id": "tab_inline", "label": "Inline"},
        ]
    }
    widget = renderer.render(props, "main", app, comp_id="tabs_demo")
    inline_child = QWidget()
    inline_child.setObjectName("tab_inline")
    widget.addTab(inline_child, "Inline")

    renderer.after_children_render(widget, props, "main", app, "tabs_demo")
    QApplication.processEvents()

    assert widget.count() == 2
    route_host = widget.widget(0)
    route_surface_id = str(route_host.property("surface_host_id") or "")
    assert route_surface_id

    widget._tab_change_origin = "user"  # type: ignore[attr-defined]
    widget.setCurrentIndex(1)
    widget._tab_change_origin = "user"  # type: ignore[attr-defined]
    widget.setCurrentIndex(0)
    QApplication.processEvents()

    assert emitted
    action_names = [name for name, *_ in emitted]
    assert "render_route_surface" in action_names
    render_route_call = next(item for item in emitted if item[0] == "render_route_surface")
    assert render_route_call[1]["path"] == "/components/_complex/card"
    assert render_route_call[1]["surface_id"] == route_surface_id
    assert render_route_call[2] == "main"
    assert render_route_call[3] == "tabs_demo"
    navigate_calls = [item for item in emitted if item[0] == "navigate"]
    assert navigate_calls
    navigate_call = next(item for item in navigate_calls if "tab_tabs_demo=tab_route" in str(item[1].get("path", "")))
    assert navigate_call[1]["render"] is False
    assert "tab_tabs_demo=tab_route" in navigate_call[1]["path"]


def test_tabs_renderer_inline_tab_with_route_does_not_emit_route_action(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    emitted = []
    monkeypatch.setattr(
        tabs_mod,
        "emit_action",
        lambda app, name, context, surface_id, comp_id: emitted.append(
            (name, context, surface_id, comp_id)
        ),
    )

    renderer = TabsRenderer()
    app = SimpleNamespace(
        store=SimpleNamespace(get=lambda path, default=None, scope="global": "/components/_complex/tabs"),
    )
    props = {
        "tabs": [
            {"id": "tab_page", "label": "Page", "route": "/components/_complex/card"},
        ]
    }
    widget = renderer.render(props, "main", app, comp_id="tabs_inline_route")
    inline_child = QWidget()
    inline_child.setObjectName("tab_page")
    widget.addTab(inline_child, "Page")

    renderer.after_children_render(widget, props, "main", app, "tabs_inline_route")
    QApplication.processEvents()

    assert all(name != "render_route_surface" for name, *_ in emitted)
    assert all(name != "navigate" for name, *_ in emitted)


def test_tabs_renderer_restores_active_tab_from_query(monkeypatch):
    _ = QApplication.instance() or QApplication([])
    emitted = []
    monkeypatch.setattr(
        tabs_mod,
        "emit_action",
        lambda app, name, context, surface_id, comp_id: emitted.append(
            (name, context, surface_id, comp_id)
        ),
    )

    renderer = TabsRenderer()
    app = SimpleNamespace(
        store=SimpleNamespace(
            get=lambda path, default=None, scope="global": "/components/_complex/tabs?tab_tabs_restore=1"
        ),
    )
    props = {
        "tabs": [
            {"id": "t1", "label": "First"},
            {"id": "t2", "label": "Second"},
        ]
    }
    widget = renderer.render(props, "main", app, comp_id="tabs_restore")
    first = QWidget()
    first.setObjectName("t1")
    second = QWidget()
    second.setObjectName("t2")
    widget.addTab(first, "First")
    widget.addTab(second, "Second")

    renderer.after_children_render(widget, props, "main", app, "tabs_restore")
    QApplication.processEvents()

    assert widget.currentIndex() == 1
    assert all(name != "navigate" for name, *_ in emitted)
