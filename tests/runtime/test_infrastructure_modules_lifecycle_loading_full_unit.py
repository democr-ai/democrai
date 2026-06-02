from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.infrastructure.modules.lifecycle as lifecycle_mod
import democrai.core.infrastructure.modules.loading as loading_mod


class _Logger:
    def __init__(self):
        self.debugs = []
        self.infos = []
        self.warnings = []
        self.errors = []

    def debug(self, msg, *args, **kwargs):
        self.debugs.append(str(msg))

    def info(self, msg, *args, **kwargs):
        self.infos.append(str(msg))

    def warning(self, msg, *args, **kwargs):
        self.warnings.append(str(msg))

    def error(self, msg, *args, **kwargs):
        self.errors.append(str(msg))


@pytest.mark.asyncio
async def test_lifecycle_legacy_binary_stop_and_reload_branches(tmp_path: Path, monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger, setup_mode=False),
        CURRENT_PLATFORM="linux",
        CURRENT_ARCH="x86_64",
        importlib=SimpleNamespace(invalidate_caches=lambda: None, import_module=lambda _n: SimpleNamespace()),
        sys=SimpleNamespace(path_importer_cache={}, modules={}),
        get_base_dir=lambda: str(tmp_path),
        validate_module_name=lambda n: n,
    )

    # stop_module branches
    class _Evt:
        def __init__(self):
            self.set_calls = 0

        def set(self):
            self.set_calls += 1

    class _Task:
        def __init__(self):
            self.cancel_calls = 0

        def cancel(self):
            self.cancel_calls += 1

    evt = _Evt()
    task = _Task()
    module_s = SimpleNamespace(name="ms", _stop_events={"a": evt}, _background_tasks=[task])
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: (_ for _ in ()).throw(RuntimeError("stop fail"))),
    )
    lifecycle_mod.stop_module(module_s)
    assert evt.set_calls == 1 and task.cancel_calls == 1

    # reload_module branches: non-python types short-circuit
    rel = SimpleNamespace(name="x", type="extension-skip", is_builtin=True)
    lifecycle_mod.reload_module(rel)  # early return on type

    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(lifecycle_mod.importlib, "invalidate_caches", lambda: None)
    monkeypatch.setattr(lifecycle_mod.sys, "path_importer_cache", {})
    monkeypatch.setitem(lifecycle_mod.sys.modules, "modules.x", object())
    monkeypatch.setitem(lifecycle_mod.sys.modules, "modules.x.a", object())
    rel = SimpleNamespace(
        name="x",
        type="python",
        path=str(tmp_path / "x"),
        is_builtin=True,
        _stop_events={"z": _Evt()},
        _background_tasks=[_Task()],
        _load_sidebar_entries_from_init=lambda _m: None,
        is_active=True,
        error_message=None,
        sidebar_entries=["old"],
        sidebar_init_declared=True,
    )
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "manifest.json").write_text('{"enabled": true}', encoding="utf-8")
    # router/action/runtime stop failure branches
    monkeypatch.setitem(sys.modules, "democrai.core.application.routing.router", SimpleNamespace(Router=SimpleNamespace(invalidate_module_routes=lambda _n: (_ for _ in ()).throw(RuntimeError("router")))))
    monkeypatch.setitem(sys.modules, "democrai.core.application.handler.action_resolution", SimpleNamespace(invalidate_legacy_action_cache=lambda _n: (_ for _ in ()).throw(RuntimeError("action"))))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.modules.runtime", SimpleNamespace(get_module_runtime=lambda: (_ for _ in ()).throw(RuntimeError("runtime"))))

    def _import_ui_fail(name):
        if name == "modules.x":
            return SimpleNamespace()
        if name == "modules.x.ui":
            raise RuntimeError("ui boom")
        return SimpleNamespace()

    monkeypatch.setattr(lifecycle_mod.importlib, "import_module", _import_ui_fail)
    lifecycle_mod.reload_module(rel)
    assert rel.is_active is False and "(ui)" in (rel.error_message or "")

    rel.is_active = True
    rel.error_message = None

    def _import_commands_fail(name):
        if name == "modules.x":
            return SimpleNamespace()
        if name == "modules.x.ui":
            raise ImportError("ui missing")
        if name == "modules.x.actions":
            raise ImportError("actions missing")
        if name == "modules.x.commands":
            raise RuntimeError("cmd boom")
        return SimpleNamespace()

    monkeypatch.setattr(lifecycle_mod.importlib, "import_module", _import_commands_fail)
    lifecycle_mod.reload_module(rel)
    assert rel.is_active is False and "(commands)" in (rel.error_message or "")


@pytest.mark.asyncio
async def test_lifecycle_manager_flow_branches(tmp_path: Path, monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger, setup_mode=False),
        get_base_dir=lambda: str(tmp_path),
        validate_module_name=lambda n: n,
        Module=lambda path, manifest, is_builtin=True, owner_id="o": SimpleNamespace(
            name=manifest["name"],
            version="1.2.3",
            is_active=False,
            error_message="x",
            load_modules=lambda load_ui=True: None,
        ),
    )
    manager = SimpleNamespace(
        _trust_mode="all",
        _allow_user_modules=True,
        _trusted_modules=set(),
        _modules={},
        _owner_id="owner",
        _background_started=False,
        _start_lock=asyncio.Lock(),
        _start_future=None,
    )

    monkeypatch.setattr(lifecycle_mod, "app_ctx", mod.app_ctx)
    lifecycle_mod.configure_trust(manager, trust_mode="trusted_only", allow_user_modules=False, trusted_modules=[" a ", "", "b"])
    assert manager._trust_mode == "trusted_only"
    assert lifecycle_mod.is_trusted(manager, "x", is_builtin=True) is True
    assert lifecycle_mod.is_trusted(manager, "x", is_builtin=False) is False
    manager._allow_user_modules = True
    assert lifecycle_mod.is_trusted(manager, "x", is_builtin=False) is False
    manager._trusted_modules = {"x"}
    assert lifecycle_mod.is_trusted(manager, "x", is_builtin=False) is True

    # discover_modules branches
    manager._modules = {"builtin": object()}
    calls = []
    manager._try_register_module = lambda path, is_builtin, load_ui=True: calls.append((path, is_builtin, load_ui))
    real_exists = lifecycle_mod.os.path.exists
    monkeypatch.setattr(lifecycle_mod.os.path, "exists", lambda p: False)
    lifecycle_mod.discover_modules(manager, str(tmp_path / "missing"), is_builtin=False, load_ui=False)

    mods_dir = tmp_path / "mods"
    mods_dir.mkdir()
    monkeypatch.setattr(lifecycle_mod.os.path, "exists", lambda p: True if p == str(mods_dir) else real_exists(p))
    monkeypatch.setattr(
        lifecycle_mod.os,
        "scandir",
        lambda p: [
            SimpleNamespace(path=str(mods_dir / "d1"), is_dir=lambda: False),
            SimpleNamespace(path=str(mods_dir / "d2"), is_dir=lambda: True),
        ],
    )
    monkeypatch.setitem(sys.modules, "democrai.core.platform.utils.discovery", SimpleNamespace(discover_submodules=lambda _pkg: ["modules.builtin", "modules.newone"]))
    lifecycle_mod.discover_modules(manager, str(mods_dir), is_builtin=True, load_ui=True)
    assert any(item[0].endswith("d2") for item in calls)
    assert any(item[0].endswith("newone") for item in calls)

    # try_register_module branches
    mpath = tmp_path / "module1"
    mpath.mkdir()
    monkeypatch.setattr(lifecycle_mod, "validate_module_name", mod.validate_module_name)
    lifecycle_mod.try_register_module(manager, mod.Module, str(mpath), is_builtin=True, load_ui=True)  # missing manifest
    (mpath / "manifest.json").write_text("{", encoding="utf-8")
    lifecycle_mod.try_register_module(manager, mod.Module, str(mpath), is_builtin=True, load_ui=True)  # json error
    assert logger.errors
    (mpath / "manifest.json").write_text(json.dumps({"name": "x", "label": "X"}), encoding="utf-8")
    manager._is_trusted = lambda name, is_builtin: False
    lifecycle_mod.try_register_module(manager, mod.Module, str(mpath), is_builtin=True, load_ui=True)
    assert logger.warnings
    manager._is_trusted = lambda name, is_builtin: True
    manager._modules = {"x": object()}
    lifecycle_mod.try_register_module(manager, mod.Module, str(mpath), is_builtin=True, load_ui=True)
    manager._modules = {}
    lifecycle_mod.try_register_module(manager, mod.Module, str(mpath), is_builtin=False, load_ui=False)
    assert "x" in manager._modules

    assert lifecycle_mod.enable_runtime() is None
    manager._modules = {
        "a": SimpleNamespace(start_background_commands=lambda: asyncio.sleep(0)),
        "b": SimpleNamespace(start_background_commands=lambda: asyncio.sleep(0)),
    }
    await lifecycle_mod.start_all_modules(manager)

    # ensure_started branches
    manager._background_started = True
    await lifecycle_mod.ensure_started(manager)
    manager._background_started = False
    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=True))
    await lifecycle_mod.ensure_started(manager)
    assert manager._background_started is True

    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False))
    manager._background_started = False
    manager.start_all_modules = lambda: asyncio.sleep(0)
    await lifecycle_mod.ensure_started(manager)
    manager._background_started = True
    await lifecycle_mod.ensure_started(manager)
    manager._background_started = False

    # inner lock branch where background_started flips before second check
    async def _start_then_flip():
        manager._background_started = True
        return None

    manager.start_all_modules = _start_then_flip
    await lifecycle_mod.ensure_started(manager)

    # schedule_startup branches
    manager._background_started = True
    lifecycle_mod.schedule_startup(manager, loop=object())
    manager._background_started = False
    lifecycle_mod.schedule_startup(manager, loop=None)
    manager._start_future = SimpleNamespace(done=lambda: False)
    lifecycle_mod.schedule_startup(manager, loop=object())
    manager._start_future = None
    manager.ensure_started = lambda: lifecycle_mod.ensure_started(manager)
    monkeypatch.setattr(
        lifecycle_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: (coro.close(), SimpleNamespace(done=lambda: True))[1],
    )
    lifecycle_mod.schedule_startup(manager, loop=object())
    assert manager._start_future is not None

    # shutdown/reload_all_modules branches
    manager._modules = {
            "ok": SimpleNamespace(stop=lambda: None, is_active=True, reload=lambda: None, name="ok", path=str(tmp_path / "ok")),
            "inactive": SimpleNamespace(stop=lambda: None, is_active=False, reload=lambda: (_ for _ in ()).throw(RuntimeError("no")), name="inactive", path=str(tmp_path / "inactive")),
            "boom": SimpleNamespace(stop=lambda: None, is_active=True, reload=lambda: (_ for _ in ()).throw(RuntimeError("reload")), name="boom", error_message=None, path=str(tmp_path / "boom")),
        }
    for name in ("ok", "inactive", "boom"):
        (tmp_path / name).mkdir(exist_ok=True)
        (tmp_path / name / "manifest.json").write_text('{"enabled": true}', encoding="utf-8")
    lifecycle_mod.shutdown(manager)
    monkeypatch.setattr(lifecycle_mod, "app_ctx", mod.app_ctx)
    lifecycle_mod.reload_all_modules(manager)
    assert manager._modules["boom"].is_active is False


def test_loading_full_branches(tmp_path: Path, monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger),
        resolve_module_resource=lambda p, v: f"{p}:{v}",
        sync_module_authorization=lambda *a, **k: None,
        get_translation_service=lambda: SimpleNamespace(load_module_locales=lambda *a, **k: None),
        CURRENT_PLATFORM="linux",
        importlib=SimpleNamespace(import_module=lambda _name: SimpleNamespace()),
    )
    module = SimpleNamespace(
        name="m",
        path=str(tmp_path / "m"),
        _manifest={"name": "m"},
        label="M",
        priority=3,
        is_builtin=False,
        type="python",
        platforms={"linux": {"entry": "run.sh"}},
        validate_compatibility=lambda: True,
        _load_python_modules=lambda *a, **k: None,
        is_active=False,
        error_message=None,
    )
    os.makedirs(module.path, exist_ok=True)

    # load_modules: deps path + warning + non-builtin parent path + migrations/locales
    deps = Path(module.path) / "deps"
    deps.mkdir()
    (deps / "x.so").write_text("x", encoding="utf-8")
    (Path(module.path) / "migrations").mkdir()
    (Path(module.path) / "locales").mkdir()

    called = {"migr": 0}
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.storage.data.migrations_handler",
        SimpleNamespace(run_module_migration=lambda *a, **k: called.__setitem__("migr", called["migr"] + 1)),
    )
    monkeypatch.setattr(loading_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(loading_mod, "sync_module_authorization", mod.sync_module_authorization)
    monkeypatch.setattr(loading_mod, "get_translation_service", mod.get_translation_service)

    prev_sys_path = list(sys.path)
    try:
        loading_mod.load_modules(module, load_ui=False)
    finally:
        sys.path[:] = prev_sys_path
    assert logger.warnings and called["migr"] == 1 and module.is_active is True

    # exception branch with remove path ValueError path
    module_e = SimpleNamespace(
        name="me",
        path=str(tmp_path / "outer" / "me"),
        is_builtin=False,
        type="python",
        platforms={"linux": {}},
        validate_compatibility=lambda: True,
        _load_python_modules=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("load fail")),
        is_active=False,
        error_message=None,
    )
    os.makedirs(module_e.path, exist_ok=True)
    class _PathList(list):
        def remove(self, _value):
            raise ValueError("gone")

    monkeypatch.setattr(loading_mod.sys, "path", _PathList())
    loading_mod.load_modules(module_e, load_ui=True)
    assert module_e.error_message == "load fail"

    # load_python_modules branches (import errors, load_ui false)
    cur = SimpleNamespace(set=lambda _sdk: "tok", reset=lambda _tok: None)
    monkeypatch.setitem(sys.modules, "democrai.sdk.client", SimpleNamespace(SDK=lambda *a, **k: "sdk", current_sdk=cur))
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.platform.utils.discovery",
        SimpleNamespace(discover_submodules=lambda pkg: [f"{pkg}.ok", f"{pkg}.missing"]),
    )
    imports = []

    def _import(name):
        imports.append(name)
        if name.endswith(".missing"):
            raise ImportError("missing")
        if name.endswith(".actions"):
            raise ImportError("actions package missing")
        if name.endswith(".commands"):
            raise ImportError("commands package missing")
        if name.endswith(".ui"):
            raise ImportError("ui missing")
        return SimpleNamespace()

    monkeypatch.setattr(loading_mod.importlib, "import_module", _import)
    module_p = SimpleNamespace(path=module.path, name="m", _load_sidebar_entries_from_init=lambda _m: None, actions_module=None, commands_module=None, ui_module=None)
    loading_mod.load_python_modules(module_p, "modules.m", load_ui=True)
    loading_mod.load_python_modules(module_p, "modules.m", load_ui=False)
    assert imports

    # load_sidebar_entries_from_init branches
    module_s = SimpleNamespace(name="m", label="M", priority=3, path=module.path, _manifest={"x": 1}, sidebar_entries=["x"], sidebar_init_declared=True)
    module_s._normalize_sidebar_entry = lambda raw, index: None if raw == "skip" else {"id": str(index)}
    monkeypatch.setattr(loading_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(loading_mod, "resolve_module_resource", mod.resolve_module_resource)
    loading_mod.load_sidebar_entries_from_init(module_s, SimpleNamespace(init=None))
    assert module_s.sidebar_entries == [] and module_s.sidebar_init_declared is False

    class _InitTypeError:
        def __call__(self, ctx):
            return [{"a": 1}, "skip"]

        @property
        def __signature__(self):
            raise TypeError("sig fail")

    loading_mod.load_sidebar_entries_from_init(module_s, SimpleNamespace(init=_InitTypeError()))
    assert module_s.sidebar_entries == [{"id": "0"}]

    loading_mod.load_sidebar_entries_from_init(module_s, SimpleNamespace(init=lambda ctx: {"sidebar_entries": [{"a": 1}]}))
    assert module_s.sidebar_entries == [{"id": "0"}]

    # normalize_sidebar_entry branches
    nm = loading_mod.normalize_sidebar_entry
    assert nm(module_s, {"action": {"name": "go"}, "id": " ", "label": 1, "icon": 3, "position": "x", "visible_for": "x"}, index=4)["id"] == "m_4"
    assert nm(module_s, {"action": {"name": "go", "context": "x"}}, index=1)["action"]["context"] == {}
    out = nm(
        module_s,
        {
            "action": {"name": "go"},
            "priority": "bad",
            "active_path": " /a ",
            "authenticated_label": " al ",
            "authenticated_icon": " ai ",
            "guest_label": " gl ",
            "guest_icon": " gi ",
            "authenticated_action": {"name": "auth", "context": "x"},
            "guest_action": {"name": "guest", "context": "x"},
        },
        index=2,
    )
    assert out["priority"] == 3
    assert out["active_path"] == "/a"
    assert out["authenticated_action"]["context"] == {}
    assert out["guest_action"]["context"] == {}


@pytest.mark.asyncio
async def test_lifecycle_remaining_branches(monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(app_ctx=lambda: SimpleNamespace(logger=logger))

    manager = SimpleNamespace(_trust_mode="all", _allow_user_modules=False, _trusted_modules=set())
    assert lifecycle_mod.is_trusted(manager, "u", is_builtin=False) is False

    # stop_module false process branch
    class _Evt:
        def __init__(self):
            self.n = 0

        def set(self):
            self.n += 1

    class _Task:
        def __init__(self):
            self.n = 0

        def cancel(self):
            self.n += 1

    evt = _Evt()
    task = _Task()
    module = SimpleNamespace(name="m", _stop_events={"x": evt}, _background_tasks=[task], _process=None)
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.modules.runtime", SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(stop_module=lambda _n: None)))
    lifecycle_mod.stop_module(module)
    assert evt.n == 1 and task.n == 1

    # reload_module commands ImportError branch
    rel = SimpleNamespace(
        name="k",
        type="python",
        path="/tmp/k",
        is_builtin=True,
        _stop_events={},
        _background_tasks=[],
        _load_sidebar_entries_from_init=lambda _m: None,
        is_active=True,
        error_message=None,
        sidebar_entries=[],
        sidebar_init_declared=False,
    )
    monkeypatch.setattr(lifecycle_mod, "_load_module_manifest", lambda _path: {"enabled": True})
    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(lifecycle_mod.importlib, "invalidate_caches", lambda: None)
    monkeypatch.setattr(lifecycle_mod.sys, "path_importer_cache", {})
    monkeypatch.setitem(lifecycle_mod.sys.modules, "modules.k", object())
    monkeypatch.setitem(sys.modules, "democrai.core.application.routing.router", SimpleNamespace(Router=SimpleNamespace(invalidate_module_routes=lambda _n: None)))
    monkeypatch.setitem(sys.modules, "democrai.core.application.handler.action_resolution", SimpleNamespace(invalidate_legacy_action_cache=lambda _n: None))
    monkeypatch.setitem(sys.modules, "democrai.core.infrastructure.modules.runtime", SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(stop_module=lambda _n: None)))

    def _import(name):
        if name == "modules.k.commands":
            raise ImportError("missing commands")
        return SimpleNamespace()

    monkeypatch.setattr(lifecycle_mod.importlib, "import_module", _import)
    lifecycle_mod.reload_module(rel)
    assert rel.commands_module is None
    assert rel.is_active is True

    # ensure_started inner check line 312
    class _Lock:
        async def __aenter__(self):
            mgr._background_started = True
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    mgr = SimpleNamespace(
        _background_started=False,
        _start_lock=_Lock(),
        _start_future=None,
        start_all_modules=lambda: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False))
    await lifecycle_mod.ensure_started(mgr)


def test_loading_remaining_branches(tmp_path: Path, monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger),
        resolve_module_resource=lambda p, v: f"{p}:{v}",
        sync_module_authorization=lambda *a, **k: None,
        get_translation_service=lambda: SimpleNamespace(load_module_locales=lambda *a, **k: None),
        CURRENT_PLATFORM="linux",
    )
    monkeypatch.setattr(loading_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(loading_mod, "sync_module_authorization", mod.sync_module_authorization)
    monkeypatch.setattr(loading_mod, "get_translation_service", mod.get_translation_service)
    base = tmp_path / "mx"
    base.mkdir()
    (base / "deps").mkdir()
    (base / "deps" / "note.txt").write_text("x", encoding="utf-8")
    (base / "run.sh").write_text("#!/bin/sh\n", encoding="utf-8")

    # non-builtin path already present to cover 51->56 and 53->56
    old_path = list(loading_mod.sys.path)
    try:
        loading_mod.sys.path[:] = [str(base), str(base.parent)]
        module = SimpleNamespace(
            name="mx",
            path=str(base),
            is_builtin=False,
            type="python",
            platforms={"linux": {"entry": "run.sh"}},
            validate_compatibility=lambda: True,
            _load_python_modules=lambda *a, **k: None,
            is_active=False,
            error_message=None,
        )
        loading_mod.load_modules(module, load_ui=True)
        assert module.is_active is True

        module_parent_only = SimpleNamespace(
            name="myp",
            path=str(base / "child"),
            is_builtin=False,
            type="python",
            platforms={"linux": {}},
            validate_compatibility=lambda: True,
            _load_python_modules=lambda *a, **k: None,
            is_active=False,
            error_message=None,
        )
        os.makedirs(module_parent_only.path, exist_ok=True)
        loading_mod.sys.path[:] = [str(Path(module_parent_only.path).parent)]
        loading_mod.load_modules(module_parent_only, load_ui=True)
        assert module_parent_only.is_active is True

        module_other = SimpleNamespace(
            name="other",
            path=str(base),
            is_builtin=True,
            type="other",
            platforms={"linux": {}},
            validate_compatibility=lambda: True,
            _load_python_modules=lambda *a, **k: None,
            is_active=False,
            error_message=None,
        )
        loading_mod.load_modules(module_other, load_ui=True)
        assert module_other.is_active is True
    finally:
        loading_mod.sys.path[:] = old_path

    module_s = SimpleNamespace(name="mx", label="MX", priority=1, path=str(base), _manifest={"z": 1}, sidebar_entries=[], sidebar_init_declared=False)
    monkeypatch.setattr(loading_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(loading_mod, "resolve_module_resource", mod.resolve_module_resource)
    module_s._normalize_sidebar_entry = lambda raw, index: loading_mod.normalize_sidebar_entry(module_s, raw, index=index)

    # line 162 and branch 174->179
    loading_mod.load_sidebar_entries_from_init(
        module_s,
        SimpleNamespace(init=lambda: {"sidebar_entries": "bad"}),
    )
    assert module_s.sidebar_entries == []

    # branch 176->179
    loading_mod.load_sidebar_entries_from_init(
        module_s,
        SimpleNamespace(init=lambda ctx: "no-list"),
    )
    assert module_s.sidebar_entries == []

    out = loading_mod.normalize_sidebar_entry(
        module_s,
        {
            "id": "ok",
            "icon": "ico.svg",
            "action": {"name": "go", "context": {"a": 1}},
            "authenticated_action": {"name": "ag", "context": {"x": 1}},
            "guest_action": {"name": "gg", "context": {"y": 2}},
        },
        index=1,
    )
    assert out["id"] == "ok"
    assert out["icon"].endswith("ico.svg")
    assert out["action"]["context"] == {"a": 1}
    assert out["authenticated_action"]["context"] == {"x": 1}
    assert out["guest_action"]["context"] == {"y": 2}
