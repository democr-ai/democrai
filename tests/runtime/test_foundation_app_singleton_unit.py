from __future__ import annotations

from types import SimpleNamespace

import democrai.core.runtime.foundation.app as app_mod


def test_app_context_double_checked_lock_inner_branch(monkeypatch):
    class _FakeLock:
        def __enter__(self):
            app_mod.AppContext._instance = SimpleNamespace(marker="precreated")
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(app_mod.AppContext, "_instance", None, raising=False)
    monkeypatch.setattr(app_mod.AppContext, "_lock", _FakeLock(), raising=False)

    instance = app_mod.AppContext()
    assert getattr(instance, "marker", None) == "precreated"
