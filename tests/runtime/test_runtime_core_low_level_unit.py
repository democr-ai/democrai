from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import democrai.core.runtime.dependencies.ai_bootstrap as ai_bootstrap_mod
import democrai.core.runtime.foundation.di as di_mod
import democrai.core.runtime.observability.action_locks as action_locks_mod
from democrai.core.runtime.foundation.exceptions import (
    DependencyMissingError,
    SystemDependencyRequiredError,
)


def test_di_container_register_factory_and_get():
    class _Svc:
        pass

    c = di_mod.Container()
    s = _Svc()
    c.register(_Svc, s)
    assert c.resolve(_Svc) is s

    created = []
    c.register_factory(str, lambda: created.append("x") or "value")
    assert c.resolve(str) == "value"
    assert created == ["x"]

    assert c.get(_Svc) is s
    assert c.get(int) is None
    with pytest.raises(KeyError):
        c.resolve(int)


@pytest.mark.asyncio
async def test_action_lock_manager_acquire_release_and_purge(monkeypatch):
    values = [10.0, 10.5, 50.0]

    def _monotonic():
        if values:
            return values.pop(0)
        return 50.0

    monkeypatch.setattr(action_locks_mod.time, "monotonic", _monotonic)

    mgr = action_locks_mod.ActionLockManager(ttl_seconds=5)
    assert await mgr.acquire("", "") is True

    assert await mgr.acquire("k", "r1") is True
    assert await mgr.acquire("k", "r2") is False

    await mgr.release("", "")
    await mgr.release("k", "wrong")
    assert "k" in mgr._active

    await mgr.release("k", "r1")
    assert "k" not in mgr._active

    assert await mgr.acquire("k", "r3") is True
    mgr._active["old"] = action_locks_mod.ActionLockRecord("r", 1.0, 2.0)
    await mgr.acquire("new", "r4")
    assert "old" not in mgr._active


def test_ai_bootstrap_and_ensure_import_paths(monkeypatch):
    monkeypatch.delenv("DEMOCRAI_ENGINE_WORKER", raising=False)
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.dependencies.engine_env",
        SimpleNamespace(
            has_engine_env_context=lambda: False,
            bootstrap_engine_env=lambda: None,
            activate_local_engine_env=lambda: None,
        ),
    )
    assert ai_bootstrap_mod.bootstrap_ai() is False

    calls = []
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.dependencies.engine_env",
        SimpleNamespace(
            has_engine_env_context=lambda: True,
            bootstrap_engine_env=lambda: calls.append("boot"),
            activate_local_engine_env=lambda: calls.append("activate"),
        ),
    )
    assert ai_bootstrap_mod.bootstrap_ai() is True
    assert calls == ["boot"]

    monkeypatch.setattr(ai_bootstrap_mod.importlib, "import_module", lambda name: {"name": name})
    assert ai_bootstrap_mod.ensure_import("json")["name"] == "json"

    state = {"n": 0}

    def _import_then_ok(name):
        state["n"] += 1
        if state["n"] == 1:
            raise ImportError("missing")
        return f"ok:{name}"

    installs = []
    monkeypatch.setattr(ai_bootstrap_mod.importlib, "import_module", _import_then_ok)
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.dependencies.engine_env",
        SimpleNamespace(
            has_engine_env_context=lambda: True,
            bootstrap_engine_env=lambda: installs.append("boot"),
            get_current_engine_id=lambda: "demo",
        ),
    )
    engine_cls = SimpleNamespace(
        check_ready=lambda: {"ready": False},
        install=lambda force=False: installs.append(("install", force)),
    )
    monkeypatch.setattr(ai_bootstrap_mod, "bootstrap_ai", lambda: True)
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.manifests",
        SimpleNamespace(load_engine_class=lambda engine_id: engine_cls if engine_id == "demo" else None),
    )
    assert ai_bootstrap_mod.ensure_import("x", dependency_key="dep-x") == "ok:x"
    assert installs == [("install", False)]

    monkeypatch.setattr(ai_bootstrap_mod.importlib, "import_module", lambda _name: (_ for _ in ()).throw(ImportError("missing")))
    system_engine_cls = SimpleNamespace(
        check_ready=lambda: {"ready": False},
        install=lambda force=False: (_ for _ in ()).throw(
            SystemDependencyRequiredError("need system", dependency_key="ffmpeg", display_name="FFmpeg")
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.manifests",
        SimpleNamespace(load_engine_class=lambda _engine_id: system_engine_cls),
    )
    with pytest.raises(DependencyMissingError) as exc_system:
        ai_bootstrap_mod.ensure_import("pkg", dependency_key="pkg")
    assert exc_system.value.install_scope == "system"
    assert exc_system.value.system_dependency_key == "ffmpeg"

    python_engine_cls = SimpleNamespace(
        check_ready=lambda: {"ready": False},
        install=lambda force=False: (_ for _ in ()).throw(RuntimeError("pip fail")),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.ai.engine.manifests",
        SimpleNamespace(load_engine_class=lambda _engine_id: python_engine_cls),
    )
    with pytest.raises(DependencyMissingError) as exc_python:
        ai_bootstrap_mod.ensure_import("pkg2")
    assert exc_python.value.install_scope == "python"
