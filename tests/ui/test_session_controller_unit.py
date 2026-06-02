from types import SimpleNamespace

import clients.qtdesktop.ui.controllers.session as session_mod
from clients.qtdesktop.state import Store
from clients.qtdesktop.ui.controllers.session import SessionController


def test_session_controller_clears_page_scope_when_current_path_changes():
    calls = []
    window = SimpleNamespace(
        store=Store(),
        bindings=SimpleNamespace(on_page_scope_reset=lambda: calls.append("reset")),
    )
    controller = SessionController(window)

    window.store.set("/filters/query", "abc", "page")
    controller.update_current_path_from_message({"current_path": "/dashboard/index"})
    window.store.set("/filters/query", "abc", "page")

    controller.update_current_path_from_message({"current_path": "/chat/index"})

    assert window.store.get("/current_path", scope="global") == "/chat/index"
    assert window.store.get("/filters/query", default=None, scope="page") is None
    assert calls == ["reset", "reset"]


def test_session_controller_does_not_clear_page_scope_on_same_path():
    calls = []
    window = SimpleNamespace(
        store=Store(),
        bindings=SimpleNamespace(on_page_scope_reset=lambda: calls.append("reset")),
    )
    controller = SessionController(window)

    controller.update_current_path_from_message({"current_path": "/dashboard/index"})
    window.store.set("/filters/query", "abc", "page")

    controller.update_current_path_from_message(
        {"current_path": {"app_name": "dashboard", "page_path": "index"}}
    )

    assert window.store.get("/filters/query", scope="page") == "abc"
    assert calls == ["reset"]


def test_session_controller_prepares_surface_reset_when_switching_app_scope():
    calls = []
    window = SimpleNamespace(
        store=Store(),
        bindings=SimpleNamespace(on_page_scope_reset=lambda: calls.append("reset")),
        _surfaces=SimpleNamespace(prepare_for_app_switch=lambda: calls.append("prepare")),
    )
    controller = SessionController(window)

    controller.update_current_path_from_message({"current_path": "/components/index"})
    controller.update_current_path_from_message({"current_path": "/chat/index"})

    assert window.store.get("/current_path", scope="global") == "/chat/index"
    assert calls == ["reset", "prepare", "reset", "prepare"]


def test_session_controller_does_not_prepare_surface_reset_within_same_app_scope():
    calls = []
    window = SimpleNamespace(
        store=Store(),
        bindings=SimpleNamespace(on_page_scope_reset=lambda: calls.append("reset")),
        _surfaces=SimpleNamespace(prepare_for_app_switch=lambda: calls.append("prepare")),
    )
    controller = SessionController(window)

    controller.update_current_path_from_message({"current_path": "/components/index"})
    calls.clear()
    controller.update_current_path_from_message({"current_path": "/components/navigation"})

    assert window.store.get("/current_path", scope="global") == "/components/navigation"
    assert calls == ["reset"]


def test_session_controller_apply_auth_claims_uses_minimal_authenticated_state():
    window = SimpleNamespace(
        renderer=SimpleNamespace(user_role="Guest", user_permissions=["x"]),
    )
    controller = SessionController(window)

    controller.apply_auth_claims("header.payload.signature")
    assert window.renderer.user_role == "User"
    assert window.renderer.user_permissions == []

    controller.apply_auth_claims(None)
    assert window.renderer.user_role == "Guest"
    assert window.renderer.user_permissions == []


def test_session_controller_clears_media_pending_requests_on_path_change():
    calls = []
    window = SimpleNamespace(
        store=Store(),
        bindings=SimpleNamespace(on_page_scope_reset=lambda: calls.append("reset")),
        _media=SimpleNamespace(clear_pending_requests=lambda: calls.append("clear_media")),
    )
    controller = SessionController(window)

    controller.update_current_path_from_message({"current_path": "/components/index"})
    controller.update_current_path_from_message({"current_path": "/chat/index"})

    assert "clear_media" in calls


def test_session_controller_reschedules_token_refresh_on_reconnect(monkeypatch):
    monkeypatch.setattr(session_mod.shiboken6, "isValid", lambda obj: getattr(obj, "alive", True))

    calls = []
    window = SimpleNamespace(
        alive=True,
        jwt="jwt-token",
        renderer=SimpleNamespace(is_connected=False),
        reconnect_timer=SimpleNamespace(
            alive=True,
            stop=lambda: calls.append("stop"),
        ),
        store=SimpleNamespace(get=lambda *args, **kwargs: None),
        _background_tasks=SimpleNamespace(surfaces={}),
        _sync_surfaces_to_renderer=lambda: None,
        _startup_trace=lambda *args, **kwargs: None,
        _inbound_queue=[],
        surfaces={"main": {"components": {}}},
    )
    controller = SessionController(window)
    scheduled = []
    controller._schedule_token_refresh = lambda token: scheduled.append(token)
    controller.refresh_current_view = lambda clear_page_scope=False: calls.append("refresh")

    controller.on_connected()

    assert window.renderer.is_connected is False
    assert scheduled == ["jwt-token"]
    assert calls == ["refresh"]
