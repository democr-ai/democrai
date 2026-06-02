import asyncio
from types import SimpleNamespace

from democrai.core.application.handler.request import Core
from democrai.core.application.request_cycle import RequestEnvelope


def test_core_initialization_and_reset(monkeypatch):
    calls = []

    class _SessionStore:
        def __init__(self):
            calls.append("session_store")

    class _SessionService:
        def __init__(self, store):
            self.store = store
            calls.append(("session_service", store))

        def get_or_create(self, user, role):
            return {"user": user, "role": role}

    class _RenderService:
        def __init__(self, session_service):
            self.session_service = session_service
            calls.append(("render_service", session_service))

        async def render(self, session, force_shell=False):
            return [{"render": session}]

    class _Dispatcher:
        def __init__(self):
            calls.append("dispatcher")

    class _Engine:
        def __init__(self):
            calls.append("engine")

        async def handle(self, *args, **kwargs):
            return [{"ok": True}]

    monkeypatch.setattr("democrai.core.application.handler.request.SessionStore", _SessionStore)
    monkeypatch.setattr("democrai.core.application.handler.request.SessionService", _SessionService)
    monkeypatch.setattr("democrai.core.application.handler.request.RenderService", _RenderService)
    monkeypatch.setattr("democrai.core.application.handler.request.ActionDispatcher", _Dispatcher)
    monkeypatch.setattr("democrai.core.application.handler.request.RequestCycleEngine", _Engine)

    core = Core()
    assert core.get_session("fabio", "admin") == {"user": "fabio", "role": "admin"}
    assert asyncio.run(core.render({"current_path": "/"})) == [{"render": {"current_path": "/"}}]

    previous_store = core.session_store
    previous_service = core.session_service
    core.reset_session_store()

    assert core.session_store is not previous_store
    assert calls == [
        "session_store",
        ("session_service", previous_store),
        ("render_service", previous_service),
        "dispatcher",
        "engine",
        "session_store",
        ("session_service", core.session_store),
        ("render_service", core.render_service.session_service),
    ]


def test_core_handle_delegates_to_request_engine(monkeypatch):
    class _SessionStore:
        pass

    class _SessionService:
        def __init__(self, store):
            self.store = store

        def get_or_create(self, user, role):
            return {"user": user, "role": role}

    class _RenderService:
        def __init__(self, session_service):
            self.session_service = session_service

        async def render(self, session, force_shell=False):
            return [{"render": session}]

    class _Dispatcher:
        pass

    recorded = {}

    class _Engine:
        async def handle(self, msg, **kwargs):
            recorded["msg"] = msg
            recorded.update(kwargs)
            return [{"kind": "handled"}]

    monkeypatch.setattr("democrai.core.application.handler.request.SessionStore", _SessionStore)
    monkeypatch.setattr("democrai.core.application.handler.request.SessionService", _SessionService)
    monkeypatch.setattr("democrai.core.application.handler.request.RenderService", _RenderService)
    monkeypatch.setattr("democrai.core.application.handler.request.ActionDispatcher", _Dispatcher)
    monkeypatch.setattr("democrai.core.application.handler.request.RequestCycleEngine", _Engine)

    core = Core()
    result = asyncio.run(core.handle({"kind": "click"}))

    assert result == [{"kind": "handled"}]
    assert isinstance(recorded["msg"], RequestEnvelope)
    assert recorded["msg"].message == {"kind": "click"}
    assert recorded["msg"].kind == "unknown"
    assert recorded["dispatcher"] is core.dispatcher
    assert recorded["session_service"] is core.session_service
    assert recorded["get_session"] == core.get_session
    assert recorded["render"] == core.render


def test_core_get_session_with_explicit_and_request_context_key(monkeypatch):
    class _SessionStore:
        pass

    class _SessionService:
        def __init__(self, _store):
            self.calls = []

        def get_or_create(self, user, role, session_key=None):
            self.calls.append((user, role, session_key))
            return {"user": user, "role": role, "session_key": session_key}

    monkeypatch.setattr("democrai.core.application.handler.request.SessionStore", _SessionStore)
    monkeypatch.setattr("democrai.core.application.handler.request.SessionService", _SessionService)
    monkeypatch.setattr("democrai.core.application.handler.request.RenderService", lambda ss: SimpleNamespace(session_service=ss, render=lambda *a, **k: []))
    monkeypatch.setattr("democrai.core.application.handler.request.ActionDispatcher", lambda: SimpleNamespace())
    monkeypatch.setattr("democrai.core.application.handler.request.RequestCycleEngine", lambda: SimpleNamespace())

    core = Core()
    out1 = core.get_session("u1", "r1", session_key="s-explicit")
    assert out1["session_key"] == "s-explicit"

    monkeypatch.setattr(
        "democrai.core.application.handler.request.req_ctx",
        lambda: SimpleNamespace(session_key="s-from-ctx"),
    )
    out2 = core.get_session("u2", "r2")
    assert out2["session_key"] == "s-from-ctx"
