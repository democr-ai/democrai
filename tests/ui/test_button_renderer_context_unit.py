from types import SimpleNamespace

from PySide6.QtWidgets import QApplication
from clients.qtdesktop.ui.controllers.action_locks import ActionLockController

from clients.qtdesktop.ui.renderers.domains.actions.button import ButtonRenderer
from clients.qtdesktop.ui.renderers.domains.actions.vertical_button import VerticalButtonRenderer


def test_button_renderer_resolves_bound_context_via_bindings():
    renderer = ButtonRenderer()

    def _resolve(value):
        if isinstance(value, dict) and value.get("type") == "store":
            return 3
        return value

    app = SimpleNamespace(
        bindings=SimpleNamespace(
            resolve_value=_resolve
        )
    )

    resolved = renderer._resolve_action_context(
        app,
        {
            "scope": "page",
            "current_value": {
                "type": "store",
                "scope": "page",
                "path": "local_counter",
                "default": 0,
            },
        },
    )

    assert resolved == {"scope": "page", "current_value": 3}


def test_vertical_button_renderer_falls_back_to_original_context_on_error():
    renderer = VerticalButtonRenderer()
    context = {"path": "/components/index"}
    app = SimpleNamespace(
        bindings=SimpleNamespace(resolve_value=lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))
    )

    resolved = renderer._resolve_action_context(app, context)

    assert resolved == context


def test_button_renderer_keeps_plain_path_context_dict():
    renderer = ButtonRenderer()
    app = SimpleNamespace(
        bindings=SimpleNamespace(
            resolve_value=lambda value: value
        )
    )
    context = {"path": "/components/index"}

    resolved = renderer._resolve_action_context(app, context)

    assert resolved == {"path": "/components/index"}


def test_button_renderer_uses_updated_action_context_after_property_update():
    _ = QApplication.instance() or QApplication([])

    emitted = []

    class _Signal:
        def emit(self, name, context, surface_id, comp_id):
            emitted.append((name, context, surface_id, comp_id))

    app = SimpleNamespace(
        bindings=SimpleNamespace(resolve_value=lambda value: value),
        action_triggered=_Signal(),
        _action_locks=None,
    )

    renderer = ButtonRenderer()
    widget = renderer.render(
        {
            "label": {"literalString": "Run"},
            "action": {"name": "components.wizard_prev", "context": {"wizard_id": "demo_wizard", "active_step_id": "s1"}},
        },
        "main",
        app,
        comp_id="btn_runtime_action",
    )

    renderer.update_widget_property(
        widget,
        "action",
        {"name": "components.wizard_next", "context": {"wizard_id": "demo_wizard", "active_step_id": "s2"}},
    )

    widget.click()

    assert emitted, "expected one click action emission"
    name, ctx, surface_id, comp_id = emitted[0]
    assert name == "components.wizard_next"
    assert ctx["wizard_id"] == "demo_wizard"
    assert ctx["active_step_id"] == "s2"
    assert surface_id == "main"
    assert comp_id == "btn_runtime_action"


def test_button_renderer_disables_when_tracked_action_is_pending():
    _ = QApplication.instance() or QApplication([])

    app = SimpleNamespace(
        bindings=SimpleNamespace(resolve_value=lambda value: value),
        action_triggered=SimpleNamespace(emit=lambda *args: None),
        _action_locks=SimpleNamespace(
            is_pending=lambda action_name: action_name == "system.refresh",
            sync_widget=lambda widget: widget.setEnabled(False),
        ),
    )

    renderer = ButtonRenderer()
    widget = renderer.render(
        {
            "label": {"literalString": "Save"},
            "action": {"name": "system.save", "context": {}},
            "track_loading": ["system.refresh", "system.save"],
        },
        "main",
        app,
        comp_id="btn_tracked_loading",
    )

    assert widget.isEnabled() is False
    assert widget.property("_track_loading_names") == ["system.refresh", "system.save"]


def test_vertical_button_renderer_uses_track_loading_list():
    _ = QApplication.instance() or QApplication([])

    app = SimpleNamespace(
        bindings=SimpleNamespace(resolve_value=lambda value: value),
        action_triggered=SimpleNamespace(emit=lambda *args: None),
        _action_locks=SimpleNamespace(
            is_pending=lambda action_name: action_name == "system.sync",
            sync_widget=lambda widget: widget.setEnabled(False),
        ),
    )

    renderer = VerticalButtonRenderer()
    widget = renderer.render(
        {
            "label": {"literalString": "Sync"},
            "icon": {"iconName": "ri-refresh-line"},
            "action": {"name": "system.open_sync", "context": {}},
            "track_loading": "system.sync",
        },
        "main",
        app,
        comp_id="btn_vertical_tracked_loading",
    )

    assert widget.isEnabled() is False
    assert widget.property("_track_loading_names") == ["system.sync"]


def test_action_lock_controller_sync_widget_starts_and_stops_loading_feedback():
    _ = QApplication.instance() or QApplication([])

    class _Window:
        def findChildren(self, _cls):
            return []

    controller = ActionLockController(_Window())
    renderer = ButtonRenderer()
    app = SimpleNamespace(
        bindings=SimpleNamespace(resolve_value=lambda value: value),
        action_triggered=SimpleNamespace(emit=lambda *args: None),
        _action_locks=controller,
    )
    widget = renderer.render(
        {
            "label": {"literalString": "Login"},
            "action": {"name": "auth.login_submit", "context": {}},
            "track_loading": "auth.login_submit",
        },
        "main",
        app,
        comp_id="btn_loading_feedback",
    )

    controller.acquire(request_id="req-1", action_name="auth.login_submit")
    controller.sync_widget(widget)

    assert widget.isEnabled() is False
    assert widget.property("_loading_feedback_active") is True
    assert getattr(widget, "_loading_feedback_timer", None) is not None

    controller.release("req-1")
    controller.sync_widget(widget)

    assert widget.isEnabled() is True
    assert widget.property("_loading_feedback_active") is False
