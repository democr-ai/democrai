from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Store:
    def __init__(self):
        self.items = {}
        self.deleted = []
        self.created = []
        self.marked = []
        self.saved = []
        self.expired = False

    def get(self, key):
        return self.items.get(key)

    def create(self, key, data):
        self.items[key] = dict(data)
        self.created.append((key, dict(data)))
        return self.items[key]

    def delete(self, key):
        self.deleted.append(key)
        self.items.pop(key, None)

    def is_expired(self, *_a, **_k):
        return self.expired

    def mark_dirty(self, key):
        self.marked.append(key)

    def save(self, key):
        self.saved.append(key)

    def prune_expired(self, **_kwargs):
        return ["k1"]


def test_core_model_registry_paths():
    mod = __import__("democrai.core.application.models.registry", fromlist=["dummy"])
    orig = dict(mod._CORE_MODEL_REGISTRY)
    try:
        mod._CORE_MODEL_REGISTRY.clear()
        with pytest.raises(ValueError):
            mod.register_core_model("", lambda _ctx: None)
        mod.register_core_model("Users", lambda ctx: {"ctx": ctx})
        assert mod.list_core_models() == ["users"]
        assert mod.build_core_model("users", {"k": 1}) == {"ctx": {"k": 1}}
        with pytest.raises(KeyError):
            mod.build_core_model("missing", {})
    finally:
        mod._CORE_MODEL_REGISTRY.clear()
        mod._CORE_MODEL_REGISTRY.update(orig)


def test_session_service_core_flows(monkeypatch):
    mod = __import__("democrai.core.application.session.service", fromlist=["dummy"])
    store = _Store()
    cfg = {
        "session.idle_ttl_seconds": "10",
        "session.absolute_ttl_seconds": "20",
        "session.cleanup_interval_seconds": "30",
    }
    ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: cfg.get(key, default)),
        setup_mode=False,
        logger=SimpleNamespace(error=lambda *_a, **_k: None),
    )
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(mod, "resolve_home_page_path", lambda: "/home")
    monkeypatch.setattr(mod, "resolve_guest_page_path", lambda: "/guest")
    monkeypatch.setattr(mod, "current_request_profiler", lambda: None)
    monkeypatch.setattr(mod, "get_user_access_profile", lambda _uid: None)

    service = mod.SessionService(store)
    assert service.idle_ttl_seconds == 10
    assert service.absolute_ttl_seconds == 20
    assert service.cleanup_interval_seconds == 30
    assert service._is_ttl_enabled() is True
    assert service._read_positive_int("missing", default=7) == 7

    # create guest session
    guest = service.get_or_create(None)
    assert guest["current_path"] == "/guest"
    assert guest["user"]["username"] == "guest"

    # existing session + sanitize + touch
    store.items["42"] = {
        "user": {"id": 42},
        "pending_modal": True,
        "_active_aux_surfaces": ["x"],
        "_active_shell_route": "r",
    }
    store.touch = lambda _k: True
    session = service.get_or_create(42)
    assert "pending_modal" not in session
    assert session["_active_aux_surfaces"] == ["x"]
    assert session["_active_shell_route"] == "r"

    # expired path
    store.items["99"] = {"user": {"id": 99}}
    store.expired = True
    assert service.get_or_create(99)["user"]["id"] == 99  # recreated
    assert "99" in store.deleted
    store.expired = False

    # setup mode path
    ctx.setup_mode = True
    setup_session = service.get_or_create("u")
    assert setup_session["current_path"] == "/system/setup"
    ctx.setup_mode = False

    # identity resolution with profile
    monkeypatch.setattr(
        mod,
        "get_user_access_profile",
        lambda _uid: {
            "username": "fabio",
            "role": "admin",
            "access_level": 1,
            "organization_id": 10,
            "language": "it",
        },
    )
    username, user_data = service._resolve_session_user_identity(7, "Guest")
    assert username == "fabio" and user_data["language"] == "it"
    assert service._storage_key_for_identity(None, None) == "guest"
    assert service._storage_key_for_identity("abc", None) == "abc"
    assert service._storage_key_for_identity(None, "sess-1") == "sess-1"

    # persist + cleanup
    service.persist("42")
    assert store.marked == ["42"] and store.saved == ["42"]
    assert service.cleanup_expired_sessions() == ["k1"]


def test_session_service_identity_change_and_cleanup_loop(monkeypatch):
    mod = __import__("democrai.core.application.session.service", fromlist=["dummy"])
    store = _Store()
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(get=lambda *_a, **_k: None),
            setup_mode=False,
            logger=SimpleNamespace(error=lambda *_a, **_k: None),
        ),
    )
    monkeypatch.setattr(mod, "current_request_profiler", lambda: None)
    service = mod.SessionService(store)

    # identity changed deletes old non-guest and creates new
    session = {"user": {"id": 9}}
    new_key = service.persist_identity_change(session, request_user="7", request_session_key=None)
    assert new_key == "9"
    assert "7" in store.deleted
    assert any(key == "9" for key, _data in store.created)

    # no identity change
    store.deleted.clear()
    store.created.clear()
    same_key = service.persist_identity_change({"user": {"id": 9}}, request_user="9")
    assert same_key == "9"
    assert not store.deleted and not store.created
    with pytest.raises(RuntimeError, match="session_user_required"):
        service.persist_identity_change({}, request_user="9")

    # cleanup loop startup guards and shutdown path
    started = {"count": 0}

    class _Thread:
        def __init__(self, target=None, name=None, daemon=None):
            self._alive = False
            self.target = target

        def start(self):
            started["count"] += 1
            self._alive = True

        def is_alive(self):
            return self._alive

        def join(self, timeout=None):
            self._alive = False

    monkeypatch.setattr(mod.threading, "Thread", _Thread)

    service.idle_ttl_seconds = None
    service.absolute_ttl_seconds = None
    service.start_cleanup_loop()
    assert started["count"] == 0

    service.idle_ttl_seconds = 10
    service.cleanup_interval_seconds = None
    service.start_cleanup_loop()
    assert started["count"] == 0

    service.cleanup_interval_seconds = 5
    service.start_cleanup_loop()
    assert started["count"] == 1
    service.start_cleanup_loop()
    assert started["count"] == 1
    service.shutdown()
    assert service._cleanup_thread is None


def test_task_manager_basic_state():
    from democrai.core.application.tasks.task_manager import BackgroundTask, TaskManager

    tm = TaskManager()
    tm.set_loop("loop")
    assert tm._loop == "loop"
    task = BackgroundTask(id="t", user_id=1, module="core", label="L")
    tm._tasks[task.id] = task
    assert tm.get_task("t") is task
