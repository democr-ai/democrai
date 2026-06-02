from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Span:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _Profiler:
    def span(self, _name):
        return _Span()


def test_session_service_profiler_and_cleanup_error_branches(monkeypatch):
    mod = __import__("democrai.core.application.session.service", fromlist=["dummy"])

    class _Store:
        def __init__(self):
            self.items = {}
            self.deleted = []
            self.created = []
            self.marked = []
            self.saved = []

        def get(self, key):
            return self.items.get(key)

        def create(self, key, data):
            self.items[key] = dict(data)
            self.created.append((key, dict(data)))
            return self.items[key]

        def delete(self, key):
            self.deleted.append(key)

        def mark_dirty(self, key):
            self.marked.append(key)

        def save(self, key):
            self.saved.append(key)

        def is_expired(self, *_a, **_k):
            return False

        def prune_expired(self, **_k):
            raise RuntimeError("boom")

    cfg = {"session.idle_ttl_seconds": "bad", "session.absolute_ttl_seconds": "0", "session.cleanup_interval_seconds": "2"}
    logs = {"error": []}
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: SimpleNamespace(config=SimpleNamespace(get=lambda key, default=None: cfg.get(key, default)), setup_mode=False, logger=SimpleNamespace(error=lambda m, *_a, **_k: logs["error"].append(m))),
    )
    monkeypatch.setattr(mod, "resolve_home_page_path", lambda: "/home")
    monkeypatch.setattr(mod, "resolve_guest_page_path", lambda: "/guest")
    monkeypatch.setattr(mod, "get_user_access_profile", lambda _uid: None)
    monkeypatch.setattr(mod, "current_request_profiler", lambda: _Profiler())

    store = _Store()
    svc = mod.SessionService(store)

    # _read_positive_int parse failure/default branches
    assert svc.idle_ttl_seconds is None
    assert svc.absolute_ttl_seconds is None
    assert svc.cleanup_interval_seconds == 2

    # profiler get/create/persist paths
    sess = svc.get_or_create(1)
    assert sess["user"]["id"] == 1
    svc.persist("1")
    assert store.marked == ["1"] and store.saved == ["1"]

    # persist identity change with profiler and guest old key (no delete)
    key = svc.persist_identity_change({"user": {"id": "guest"}}, request_user=None)
    assert key == "guest"
    # profiler delete/create_identity branch
    key2 = svc.persist_identity_change({"user": {"id": "9"}}, request_user="7")
    assert key2 == "9"
    assert "7" in store.deleted
    assert any(k == "9" for k, _v in store.created)

    # cleanup loop error branch in _run_cleanup_loop
    class _Stop:
        def __init__(self):
            self.calls = 0

        def wait(self, _secs):
            self.calls += 1
            return self.calls > 1

        def set(self):
            return None

    svc._cleanup_stop = _Stop()
    svc._run_cleanup_loop()
    assert logs["error"]
