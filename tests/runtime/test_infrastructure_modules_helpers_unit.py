from __future__ import annotations

import asyncio
import json
import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import democrai.core.infrastructure.modules.commands as commands_mod
import democrai.core.infrastructure.modules.compat as compat_mod
import democrai.core.infrastructure.modules.lifecycle as lifecycle_mod
import democrai.core.infrastructure.modules.loading as loading_mod
import democrai.core.infrastructure.modules.manager as manager_mod
import democrai.core.infrastructure.modules.runtime as runtime_mod
from democrai.core.infrastructure.database.models import ModuleCommandState
from democrai.core.infrastructure.modules.command_state_store import ModuleCommandStateStore


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


def _patch_commands_deps(monkeypatch, *, logger, registry=None, store=None, now=None, lease_ttl=3.0, poll=0.0):
    monkeypatch.setattr(commands_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, setup_mode=False))
    monkeypatch.setattr(commands_mod, "module_command_registry", registry or SimpleNamespace(get_all=lambda module_name=None: []))
    monkeypatch.setattr(commands_mod, "module_command_state_store", store or SimpleNamespace())
    monkeypatch.setattr(commands_mod, "utc_now_naive", now or (lambda: datetime(2026, 1, 1, 10, 0, 0)))
    monkeypatch.setattr(commands_mod, "DEFAULT_LEASE_TTL_SECONDS", lease_ttl)
    monkeypatch.setattr(commands_mod, "SCHEDULE_POLL_SECONDS", poll)


def test_modules_compat_helpers(tmp_path: Path, monkeypatch):
    assert compat_mod.parse_cron_field("*/15", 0, 59)
    assert compat_mod.parse_cron_field("1-5/2", 0, 10) == {1, 3, 5}
    with pytest.raises(ValueError):
        compat_mod.parse_cron_field(" , ", 0, 10)

    dt = datetime(2026, 1, 1, 10, 30)
    assert compat_mod.cron_matches("30 10 * * *", dt) is True
    with pytest.raises(ValueError):
        compat_mod.cron_matches("bad expr", dt)

    now = datetime(2026, 1, 1, 10, 0)
    assert compat_mod.next_cron_run("2 * * * *", now).minute == 2

    icon = tmp_path / "icon.png"
    icon.write_bytes(b"x")
    assert compat_mod.resolve_module_resource(str(tmp_path), "icon.png").endswith("icon.png")
    assert compat_mod.resolve_module_resource(str(tmp_path), "http://x") == "http://x"
    assert compat_mod.module_version_match("1.2.0", ">=1.1.9") is True
    assert compat_mod.module_version_match("abc", ">=abd") is False

    monkeypatch.setattr(compat_mod, "SDK_VERSION", "2.0.0")
    monkeypatch.setattr(compat_mod, "CURRENT_PLATFORM", "linux")
    monkeypatch.setattr(compat_mod, "CURRENT_ARCH", "x86_64")
    module = SimpleNamespace(
        requirements={"core": ">=3.0.0", "python": ">=99.0"},
        _version_match=compat_mod.module_version_match,
        type="extension",
        platforms={"linux": {"arch": ["arm64"], "abi": "cp39"}},
        error_message=None,
    )
    assert compat_mod.validate_compatibility(module) is False
    module.requirements = {"core": ">=1.0.0", "python": ">=1.0"}
    assert compat_mod.validate_compatibility(module) is False
    module.platforms = {"linux": {"arch": ["x86_64"], "abi": "cp312"}}
    assert compat_mod.validate_compatibility(module) is True


def test_module_manager_reads_allowed_imports(tmp_path: Path):
    module = manager_mod.Module(
        str(tmp_path),
        {"name": "demo", "label": "Demo", "allowed_imports": ["ctypes", "ctypes.util"]},
        is_builtin=True,
        owner_id="owner",
    )
    assert module.allowed_imports == ["ctypes", "ctypes.util"]


def test_modules_loading_helpers(tmp_path: Path, monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger),
        resolve_module_resource=lambda p, v: f"RESOLVED:{v}",
        sync_module_authorization=lambda *a, **k: None,
        get_translation_service=lambda: SimpleNamespace(load_module_locales=lambda *a, **k: None),
        CURRENT_PLATFORM="linux",
        importlib=SimpleNamespace(import_module=lambda name: SimpleNamespace()),
    )
    module = SimpleNamespace(name="m", path=str(tmp_path), _manifest={"name": "m"}, label="M", priority=1)
    module._normalize_sidebar_entry = lambda entry, index: {"id": f"id{index}"} if isinstance(entry, dict) else None
    monkeypatch.setattr(loading_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(loading_mod, "resolve_module_resource", mod.resolve_module_resource)
    monkeypatch.setattr(loading_mod, "sync_module_authorization", mod.sync_module_authorization)
    monkeypatch.setattr(loading_mod, "get_translation_service", mod.get_translation_service)
    module._load_sidebar_entries_from_init = lambda module_module: loading_mod.load_sidebar_entries_from_init(module, module_module)

    assert loading_mod._load_module_rbac_manifest(module) is None
    (tmp_path / "rbac.json").write_text(json.dumps({"a": 1}), encoding="utf-8")
    assert loading_mod._load_module_rbac_manifest(module) == {"a": 1}
    (tmp_path / "rbac.json").write_text("[]", encoding="utf-8")
    with pytest.raises(Exception):
        loading_mod._load_module_rbac_manifest(module)
    assert logger.errors

    bad = loading_mod.normalize_sidebar_entry(module, {"action": {"name": "x"}, "icon": 3}, index=0)
    assert bad["icon"] is None and bad["position"] == "top"
    assert loading_mod.normalize_sidebar_entry(module, "x", index=1) is None
    assert loading_mod.normalize_sidebar_entry(module, {"action": "x"}, index=2) is None

    pkg = SimpleNamespace(init=lambda ctx=None: [{"action": {"name": "go"}}])
    loading_mod.load_sidebar_entries_from_init(module, pkg)
    assert module.sidebar_entries
    pkg_fail = SimpleNamespace(init=lambda ctx=None: (_ for _ in ()).throw(RuntimeError("boom")))
    loading_mod.load_sidebar_entries_from_init(module, pkg_fail)
    assert logger.warnings

    current_sdk = SimpleNamespace(set=lambda _sdk: "tok", reset=lambda _tok: None)
    monkeypatch.setitem(
        sys.modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=lambda *a, **k: "sdk", current_sdk=current_sdk),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.platform.utils.discovery",
        SimpleNamespace(discover_submodules=lambda pkg: [f"{pkg}.one"]),
    )
    imports = []
    monkeypatch.setattr(loading_mod.importlib, "import_module", lambda name: imports.append(name) or SimpleNamespace())
    loading_mod.load_python_modules(module, "modules.m", load_ui=True)
    assert any(name.endswith(".actions.one") for name in imports)

    # load_modules main branches
    m2 = SimpleNamespace(
        name="m2",
        path=str(tmp_path),
        is_builtin=True,
        type="python",
        validate_compatibility=lambda: False,
        error_message="incompatible",
    )
    loading_mod.load_modules(m2, load_ui=True)
    assert logger.warnings



@pytest.mark.asyncio
async def test_modules_lifecycle_helpers(tmp_path: Path, monkeypatch):
    logger = _Logger()
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger, setup_mode=False),
        CURRENT_PLATFORM="linux",
        CURRENT_ARCH="x86_64",
        importlib=SimpleNamespace(invalidate_caches=lambda: None, import_module=lambda name: SimpleNamespace()),
        sys=SimpleNamespace(path_importer_cache={}, modules={}),
        os=__import__("os"),
        get_base_dir=lambda: str(tmp_path),
        validate_module_name=lambda n: n,
        Module=lambda path, manifest, is_builtin=True, owner_id="o": SimpleNamespace(
            name=manifest["name"],
            version="1.0.0",
            is_active=True,
            error_message=None,
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
    lifecycle_mod.configure_trust(manager, trust_mode="unknown", allow_user_modules=False, trusted_modules=["a", " ", "b"])
    assert manager._trust_mode == "all" and manager._trusted_modules == {"a", "b"}
    assert lifecycle_mod.is_trusted(manager, "x", is_builtin=True) is True
    manager._trust_mode = "trusted_only"
    manager._allow_user_modules = True
    manager._trusted_modules = {"ok"}
    assert lifecycle_mod.is_trusted(manager, "ok", is_builtin=False) is True
    assert lifecycle_mod.is_trusted(manager, "ko", is_builtin=False) is False

    mod_dir = tmp_path / "mods"
    (mod_dir / "a").mkdir(parents=True)
    real_exists = lifecycle_mod.os.path.exists
    monkeypatch.setattr(lifecycle_mod.os.path, "exists", lambda p: True if p == str(mod_dir) else real_exists(p))
    monkeypatch.setattr(lifecycle_mod.os, "scandir", lambda p: [SimpleNamespace(path=str(mod_dir / "a"), is_dir=lambda: True)])
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.platform.utils.discovery",
        SimpleNamespace(discover_submodules=lambda _pkg: ["modules.builtin_mod"]),
    )
    called = []
    manager._try_register_module = lambda path, is_builtin, load_ui=True: called.append((path, is_builtin, load_ui))
    lifecycle_mod.discover_modules(manager, str(mod_dir), is_builtin=True, load_ui=True)
    assert called

    mpath = tmp_path / "m1"
    mpath.mkdir()
    (mpath / "manifest.json").write_text(json.dumps({"name": "mod1", "label": "Mod 1"}), encoding="utf-8")
    manager._is_trusted = lambda name, is_builtin: True
    monkeypatch.setattr(lifecycle_mod, "validate_module_name", mod.validate_module_name)
    lifecycle_mod.try_register_module(manager, mod.Module, str(mpath), is_builtin=True, load_ui=True)
    assert "mod1" in manager._modules

    module = SimpleNamespace(
        name="modx",
        type="python",
        path=str(tmp_path),
        platforms={"linux": {}},
        _background_tasks=[],
        _stop_events={},
    )

    # stop module
    stop_event = asyncio.Event()
    module._stop_events = {"x": stop_event}
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(stop_module=lambda _name: None)),
    )
    lifecycle_mod.stop_module(module)
    assert stop_event.is_set()

    # ensure_started/schedule/shutdown/reload-all
    manager.start_all_modules = lambda: asyncio.sleep(0)
    manager.ensure_started = lambda: lifecycle_mod.ensure_started(manager)
    await lifecycle_mod.ensure_started(manager)
    await lifecycle_mod.ensure_started(manager)
    manager._background_started = False
    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=True))
    await lifecycle_mod.ensure_started(manager)
    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(setup_mode=False))
    manager._background_started = False

    captured = []
    monkeypatch.setattr(
        lifecycle_mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: (coro.close(), SimpleNamespace(done=lambda: False))[1],
    )
    lifecycle_mod.schedule_startup(manager, loop=object())
    assert manager._start_future is not None
    manager._modules = {
        "m": SimpleNamespace(
            stop=lambda: captured.append("stop"),
            is_active=True,
            reload=lambda: captured.append("reload"),
            name="m",
            path=str(mpath),
        )
    }
    lifecycle_mod.shutdown(manager)
    assert "stop" in captured
    lifecycle_mod.reload_all_modules(manager)
    assert "reload" in captured

    # reload_module failure/success branches
    prefix = "modules.testmod"
    monkeypatch.setattr(lifecycle_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(lifecycle_mod.importlib, "invalidate_caches", lambda: None)
    monkeypatch.setattr(lifecycle_mod.sys, "path_importer_cache", {})
    monkeypatch.setitem(lifecycle_mod.sys.modules, f"{prefix}.x", object())
    monkeypatch.setitem(lifecycle_mod.sys.modules, prefix, object())
    rel_module = SimpleNamespace(
        name="testmod",
        type="python",
        is_builtin=True,
        path=str(mpath),
        _stop_events={},
        _background_tasks=[],
        _load_sidebar_entries_from_init=lambda module_module: None,
        is_active=True,
        error_message=None,
        sidebar_entries=[],
        sidebar_init_declared=False,
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(stop_module=lambda _name: None)),
    )

    def _import_fail_init(name):
        if name == prefix:
            raise RuntimeError("init-fail")
        return SimpleNamespace()

    monkeypatch.setattr(lifecycle_mod.importlib, "import_module", _import_fail_init)
    lifecycle_mod.reload_module(rel_module)
    assert rel_module.is_active is False and "init" in (rel_module.error_message or "")

    rel_module.is_active = True
    rel_module.error_message = None

    def _import_fail_actions(name):
        if name == prefix:
            return SimpleNamespace()
        if name == f"{prefix}.ui":
            raise ImportError("missing ui")
        if name == f"{prefix}.actions":
            raise RuntimeError("actions-fail")
        return SimpleNamespace()

    monkeypatch.setattr(lifecycle_mod.importlib, "import_module", _import_fail_actions)
    lifecycle_mod.reload_module(rel_module)
    assert rel_module.is_active is False and "actions" in (rel_module.error_message or "")

    rel_module.is_active = True
    rel_module.error_message = None
    monkeypatch.setattr(lifecycle_mod.importlib, "import_module", lambda _name: SimpleNamespace())
    lifecycle_mod.reload_module(rel_module)
    assert rel_module.is_active is True


@pytest.mark.asyncio
async def test_modules_commands_and_runtime_helpers(monkeypatch, tmp_path: Path):
    logger = _Logger()
    module = SimpleNamespace(
        name="m",
        type="python",
        is_active=True,
        owner_id="owner",
        _background_tasks=[],
        _stop_events={},
        _command_states={},
        _start_scheduled_command=lambda d: module._background_tasks.append(("sched", d.name)),
        _start_managed_command=lambda d, restart_on_exit, run_once_after_completion: module._background_tasks.append(("man", d.name, restart_on_exit, run_once_after_completion)),
    )
    module._state_for = lambda d: commands_mod.state_for(module, d)
    definition = SimpleNamespace(name="cmd", lifecycle="schedule")
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        registry=SimpleNamespace(get_all=lambda module_name=None: [definition]),
        store=SimpleNamespace(ensure_registered=lambda d: None),
    )
    commands_mod.start_background_commands(module)
    assert module._background_tasks

    state = commands_mod.state_for(module, SimpleNamespace(name="x", lifecycle="single_run"))
    assert state.name == "x"
    _patch_commands_deps(monkeypatch, logger=logger, store=SimpleNamespace(get=lambda _name: None))
    assert commands_mod.refresh_state(module, SimpleNamespace(name="x")) is state

    async def _invoke(**kwargs):
        return {"ok": True}

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(invoke=_invoke)),
    )
    module._refresh_state = lambda d: SimpleNamespace(last_status="idle", last_error=None)
    def_func = lambda command_name=None, module_name=None: None
    await commands_mod.invoke_command(module, SimpleNamespace(name="run", lifecycle="single_run", func=def_func, handler_module="a", handler_name="b"))

    fut = asyncio.create_task(asyncio.sleep(0))
    commands_mod.track_task(module, fut)
    await fut
    assert isinstance(commands_mod.compute_next_run(module, SimpleNamespace(name="n", interval_seconds=1, cron=None), datetime(2026, 1, 1)), datetime)
    assert isinstance(commands_mod.compute_next_run(module, SimpleNamespace(name="n", interval_seconds=None, cron="* * * * *"), datetime(2026, 1, 1)), datetime)
    with pytest.raises(ValueError):
        commands_mod.compute_next_run(module, SimpleNamespace(name="n", interval_seconds=None, cron=None), datetime(2026, 1, 1))

    _patch_commands_deps(monkeypatch, logger=logger, store=SimpleNamespace(heartbeat=lambda *a, **k: False))
    await commands_mod.lease_heartbeat(module, "cmd")
    assert logger.warnings

    # runtime helpers
    assert runtime_mod.build_module_reuse_key("m", {"user": {"id": "2", "organization_id": "9"}, "session_key": "s"})
    runtime_mod._install_module_import_paths(str(tmp_path), is_builtin=False)
    assert runtime_mod._module_allowed_imports(SimpleNamespace(allowed_imports=["ctypes", "ctypes.util", ""])) == ["ctypes"]
    snap = runtime_mod.restore_builder_snapshot({"components": [{"id": "c1"}], "template": "full", "surface_id": "main"})
    assert snap._components[0].id == "c1"

    guard_calls = []

    @contextmanager
    def _guard(**kwargs):
        guard_calls.append(kwargs)
        yield

    monkeypatch.setattr(runtime_mod, "process_guard_context", _guard)
    monkeypatch.setattr(
        runtime_mod,
        "set_req_ctx",
        lambda ctx: "tok",
    )
    monkeypatch.setattr(runtime_mod, "reset_req_ctx", lambda tok: None)
    monkeypatch.setattr(runtime_mod, "app_ctx", lambda: SimpleNamespace(module_runtime=None))
    monkeypatch.setitem(
        sys.modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=lambda **kwargs: "sdk", current_sdk=SimpleNamespace(set=lambda _s: "s", reset=lambda _t: None)),
    )
    def _import_router(name):
        if name == "render_mod":
            return SimpleNamespace(render=lambda params, session: runtime_mod.Builder())
        if name == "action_mod":
            return SimpleNamespace(handler=lambda ctx, session, sdk: {"ok": True})
        if name == "command_mod":
            return SimpleNamespace(handler=lambda *a, **k: {"cmd": True})
        if name == "bad_render_mod":
            return SimpleNamespace(render=lambda params, session: "bad")
        return SimpleNamespace()

    monkeypatch.setattr(runtime_mod.importlib, "import_module", _import_router)
    rt = runtime_mod.ModuleRuntime()
    module_rt = SimpleNamespace(
        name="m",
        path=str(tmp_path),
        is_builtin=False,
        access=[],
        allowed_imports=["ctypes"],
    )
    rendered = await rt.invoke(
        module=module_rt,
        operation="render",
        payload={"page_module": "render_mod", "current_path": "/render", "session": {}},
        persistent=False,
    )
    assert hasattr(rendered, "_components")
    action_out = await rt.invoke(
        module=module_rt,
        operation="action",
        payload={
            "handler_module": "action_mod",
            "handler_name": "handler",
            "action_name": "demo.action",
            "ctx": {},
            "session": {"current_path": "/action"},
        },
        persistent=False,
    )
    assert action_out["result"]["ok"] is True
    cmd_out = await rt.invoke(
        module=module_rt,
        operation="command",
        payload={
            "handler_module": "command_mod",
            "handler_name": "handler",
            "command_name": "demo.command",
            "call_args": [],
            "call_kwargs": {},
            "session": {},
            "include_stop_event": True,
        },
        persistent=False,
    )
    assert guard_calls and guard_calls[0]["allowed_imports"] == ["ctypes"]
    assert cmd_out["cmd"] is True
    with pytest.raises(RuntimeError):
        await rt.invoke(
            module=module_rt,
            operation="render",
            payload={"page_module": "bad_render_mod", "current_path": "/bad", "session": {}},
            persistent=False,
        )
    with pytest.raises(RuntimeError):
        await rt.invoke(module=module_rt, operation="unknown", payload={}, persistent=False)
    rt.stop_module("m")
    rt.shutdown()


def test_module_command_state_store_sqlite(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    ModuleCommandState.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    store = ModuleCommandStateStore()
    monkeypatch.setattr(store, "_session", lambda: Session())
    definition = SimpleNamespace(name="cmd.one", module_name="mod", lifecycle="schedule")
    snap = store.ensure_registered(definition)
    assert snap.command_name == "cmd.one"
    assert store.get("cmd.one") is not None
    assert store.list_states(module_name="mod")
    store.set_next_run("cmd.one", datetime(2026, 1, 1, 12, 0, 0))
    store.mark_started(definition, owner="owner-1")
    assert store.try_acquire_lease(definition, owner="owner-1", lease_ttl_seconds=10, increment_run_count=True) is True
    assert store.heartbeat("cmd.one", owner="owner-1", lease_ttl_seconds=10) is True
    store.finish_run("cmd.one", owner="owner-1", status="completed", release_lease=True)
    assert store.get("cmd.one").status == "completed"
    store.finish_run("cmd.one", owner="owner-1", status="failed", last_error="x", release_lease=False)
    assert store.get("cmd.one").to_dict()["status"] == "failed"


def test_module_command_state_store_error_branches(monkeypatch):
    store = ModuleCommandStateStore()

    class _NoDbCtx:
        db = None

    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: _NoDbCtx(),
    )
    with pytest.raises(RuntimeError):
        store._session()

    class _Row:
        module_name = "m"
        command_name = "c"
        lifecycle = "schedule"
        status = "idle"
        run_count = 0
        last_started_at = None
        last_finished_at = None
        next_run_at = None
        last_error = None
        lease_owner = None
        lease_expires_at = None
        created_at = None
        updated_at = None

    class _Q:
        def filter_by(self, **kwargs):
            return self

        def one_or_none(self):
            return None

        def one(self):
            return _Row()

    class _S:
        def query(self, model):
            return _Q()

        def add(self, row):
            return None

        def commit(self):
            from sqlalchemy.exc import IntegrityError

            raise IntegrityError("x", {}, Exception("dup"))

        def refresh(self, row):
            return None

        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(store, "_session", lambda: _S())
    snap = store.ensure_registered(SimpleNamespace(name="c", module_name="m", lifecycle="schedule"))
    assert snap.command_name == "c"


@pytest.mark.asyncio
async def test_modules_commands_runner_branches(monkeypatch):
    logger = _Logger()
    definition = SimpleNamespace(name="cmd", lifecycle="long_run")
    module = SimpleNamespace(
        name="m",
        owner_id="owner",
        _stop_events={},
        _background_tasks=[],
        _lease_heartbeat=lambda _name: asyncio.sleep(999),
        _refresh_state=lambda _d: None,
        _invoke_command=lambda _d, stop_event=None: asyncio.sleep(0),
        _track_task=lambda task: module._background_tasks.append(task),
    )

    # run_once branch with lease not acquired
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(
            try_acquire_lease=lambda *a, **k: False,
            get=lambda _name: SimpleNamespace(run_count=1, status="completed"),
            finish_run=lambda *a, **k: None,
        ),
    )
    commands_mod.start_managed_command(module, definition, restart_on_exit=False, run_once_after_completion=True)
    task = module._background_tasks.pop()
    await task

    # failure branch when acquired and invoke fails
    async def _boom(*_a, **_k):
        raise RuntimeError("boom")

    module._invoke_command = _boom
    calls = []
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(
            try_acquire_lease=lambda *a, **k: True,
            get=lambda _name: None,
            finish_run=lambda *a, **k: calls.append(("finish", k.get("status"))),
        ),
    )
    commands_mod.start_managed_command(module, definition, restart_on_exit=False, run_once_after_completion=False)
    task2 = module._background_tasks.pop()
    await task2
    assert ("finish", "failed") in calls

    # scheduled command cancelled branch
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(
            set_next_run=lambda *a, **k: None,
            try_acquire_lease=lambda *a, **k: False,
            finish_run=lambda *a, **k: calls.append(("finish_sched", k.get("status"))),
        ),
    )

    async def _cancel_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _cancel_sleep)
    commands_mod.start_scheduled_command(module, definition)
    task3 = module._background_tasks.pop()
    with pytest.raises(asyncio.CancelledError):
        await task3


@pytest.mark.asyncio
async def test_modules_commands_additional_loops_and_errors(monkeypatch):
    logger = _Logger()
    module = SimpleNamespace(
        name="m",
        owner_id="owner",
        _stop_events={},
        _background_tasks=[],
        _track_task=lambda task: module._background_tasks.append(task),
        _lease_heartbeat=lambda _name: asyncio.sleep(999),
        _refresh_state=lambda _d: SimpleNamespace(next_run_at=datetime(2026, 1, 1, 10, 0, 0)),
        _compute_next_run=lambda _d, now: now,
        _invoke_command=lambda _d, stop_event=None: asyncio.sleep(0),
    )
    definition = SimpleNamespace(name="cmd", lifecycle="schedule")

    # start_background_commands for all lifecycles
    module.is_active = True
    module.type = "python"
    module._start_scheduled_command = lambda d: module._background_tasks.append(("sched", d.name))
    module._start_managed_command = (
        lambda d, restart_on_exit, run_once_after_completion: module._background_tasks.append(
            ("managed", d.name, restart_on_exit, run_once_after_completion)
        )
    )
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(ensure_registered=lambda d: None),
        registry=SimpleNamespace(
            get_all=lambda module_name=None: [
                SimpleNamespace(name="a", lifecycle="schedule", restart_on_exit=False),
                SimpleNamespace(name="b", lifecycle="long_run", restart_on_exit=True),
                SimpleNamespace(name="c", lifecycle="single_run", restart_on_exit=False),
            ]
        ),
    )
    commands_mod.start_background_commands(module)
    assert any(item[0] == "managed" and item[2] is True for item in module._background_tasks)
    assert any(item[0] == "managed" and item[3] is True for item in module._background_tasks)

    # invoke_command cancelled and failed branches
    async def _cancel_invoke(**kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(invoke=_cancel_invoke)),
    )
    module._refresh_state = lambda _d: SimpleNamespace(last_status="idle", last_error=None)
    with pytest.raises(asyncio.CancelledError):
        await commands_mod.invoke_command(
            module,
            SimpleNamespace(name="cmd", lifecycle="single_run", func=lambda: None, handler_module="x", handler_name="y"),
        )

    async def _fail_invoke(**kwargs):
        raise RuntimeError("x")

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.modules.runtime",
        SimpleNamespace(get_module_runtime=lambda: SimpleNamespace(invoke=_fail_invoke)),
    )
    with pytest.raises(RuntimeError):
        await commands_mod.invoke_command(
            module,
            SimpleNamespace(name="cmd", lifecycle="single_run", func=lambda: None, handler_module="x", handler_name="y"),
        )

    # managed loop: acquired false + sleep branch
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(
            try_acquire_lease=lambda *a, **k: False,
            get=lambda _name: None,
            finish_run=lambda *a, **k: None,
        ),
    )

    async def _cancel_sleep(_seconds):
        raise asyncio.CancelledError()

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _cancel_sleep)
    commands_mod.start_managed_command(
        module,
        SimpleNamespace(name="mcmd", lifecycle="long_run"),
        restart_on_exit=False,
        run_once_after_completion=False,
    )
    with pytest.raises(asyncio.CancelledError):
        await module._background_tasks.pop()

    # managed loop: success + restart warning + post-loop sleep cancel
    sleep_calls = {"n": 0}

    async def _sleep_once(_seconds):
        sleep_calls["n"] += 1
        raise asyncio.CancelledError()

    monkeypatch.setattr(commands_mod.asyncio, "sleep", _sleep_once)
    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(
            try_acquire_lease=lambda *a, **k: True,
            get=lambda _name: None,
            finish_run=lambda *a, **k: None,
        ),
    )
    async def _ok_invoke(_d, stop_event=None):
        return None

    module._invoke_command = _ok_invoke
    commands_mod.start_managed_command(
        module,
        SimpleNamespace(name="mcmd2", lifecycle="long_run"),
        restart_on_exit=True,
        run_once_after_completion=False,
    )
    with pytest.raises(asyncio.CancelledError):
        await module._background_tasks.pop()
    assert logger.warnings

    # scheduled loop: one success iteration then cancel next pass
    acquire_count = {"n": 0}

    def _acquire(*_a, **_k):
        acquire_count["n"] += 1
        if acquire_count["n"] == 1:
            return True
        raise asyncio.CancelledError()

    _patch_commands_deps(
        monkeypatch,
        logger=logger,
        store=SimpleNamespace(
            set_next_run=lambda *a, **k: None,
            try_acquire_lease=_acquire,
            finish_run=lambda *a, **k: None,
        ),
    )
    _orig_sleep = asyncio.sleep
    monkeypatch.setattr(commands_mod.asyncio, "sleep", lambda _s: _orig_sleep(0))
    commands_mod.start_scheduled_command(module, SimpleNamespace(name="scmd", lifecycle="schedule"))
    with pytest.raises(asyncio.CancelledError):
        await module._background_tasks.pop()


def test_modules_loading_and_lifecycle_additional_branches(tmp_path: Path, monkeypatch):
    logger = _Logger()
    locales_loaded = []
    sync_calls = []
    mod = SimpleNamespace(
        app_ctx=lambda: SimpleNamespace(logger=logger, setup_mode=False),
        resolve_module_resource=lambda p, v: v,
        sync_module_authorization=lambda *a, **k: sync_calls.append(a),
        get_translation_service=lambda: SimpleNamespace(load_module_locales=lambda *a: locales_loaded.append(a)),
        CURRENT_PLATFORM="linux",
        importlib=SimpleNamespace(import_module=lambda name: SimpleNamespace()),
        validate_module_name=lambda n: n,
        Module=lambda path, manifest, is_builtin=True, owner_id="o": SimpleNamespace(
            name=manifest["name"],
            version="1.0.0",
            is_active=True,
            error_message=None,
            load_modules=lambda load_ui=True: None,
        ),
    )

    module_dir = tmp_path / "mod"
    module_dir.mkdir()
    deps_dir = module_dir / "deps"
    deps_dir.mkdir()
    (deps_dir / "x.so").write_text("x", encoding="utf-8")
    (module_dir / "migrations").mkdir()
    (module_dir / "locales").mkdir()
    (module_dir / "rbac.json").write_text("{}", encoding="utf-8")

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.storage.data.migrations_handler",
        SimpleNamespace(run_module_migration=lambda *a, **k: None),
    )
    monkeypatch.setattr(loading_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(loading_mod, "sync_module_authorization", mod.sync_module_authorization)
    monkeypatch.setattr(loading_mod, "get_translation_service", mod.get_translation_service)

    module = SimpleNamespace(
        name="m",
        path=str(module_dir),
        is_builtin=False,
        type="python",
        platforms={},
        validate_compatibility=lambda: True,
        error_message=None,
        is_active=False,
        _load_python_modules=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("load-fail")),
    )
    loading_mod.load_modules(module, load_ui=True)
    assert module.error_message == "load-fail"
    assert logger.errors

    # load_python_modules import-error branches
    module2 = SimpleNamespace(
        name="m2",
        path=str(module_dir),
        _load_sidebar_entries_from_init=lambda _m: None,
    )
    imports = []

    def _imp(name):
        imports.append(name)
        if name.endswith(".actions"):
            raise ImportError("actions missing")
        if name.endswith(".commands"):
            raise ImportError("commands missing")
        if name.endswith(".ui"):
            raise ImportError("ui missing")
        return SimpleNamespace()

    monkeypatch.setattr(loading_mod.importlib, "import_module", _imp)
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.platform.utils.discovery",
        SimpleNamespace(discover_submodules=lambda pkg: [f"{pkg}.x"]),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=lambda *a, **k: "sdk", current_sdk=SimpleNamespace(set=lambda _v: "t", reset=lambda _t: None)),
    )
    loading_mod.load_python_modules(module2, "modules.m2", load_ui=True)
    assert any(name.endswith(".actions.x") for name in imports)

    # lifecycle: untrusted, duplicate and bad manifest parse
    manager = SimpleNamespace(_modules={"dup": object()}, _owner_id="owner", _is_trusted=lambda *_a, **_k: False)
    manifest_dir = tmp_path / "manifest_mod"
    manifest_dir.mkdir()
    (manifest_dir / "manifest.json").write_text(json.dumps({"name": "dup", "label": "Dup"}), encoding="utf-8")
    monkeypatch.setattr(lifecycle_mod, "app_ctx", mod.app_ctx)
    monkeypatch.setattr(lifecycle_mod, "validate_module_name", lambda name: name)
    lifecycle_mod.try_register_module(manager, mod.Module, str(manifest_dir), is_builtin=False, load_ui=True)
    assert logger.warnings

    (manifest_dir / "manifest.json").write_text("{bad", encoding="utf-8")
    lifecycle_mod.try_register_module(manager, mod.Module, str(manifest_dir), is_builtin=False, load_ui=True)
    assert logger.errors


@pytest.mark.asyncio
async def test_modules_runtime_additional_branches(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(runtime_mod, "process_guard_context", contextmanager(lambda **k: (yield)))
    monkeypatch.setattr(runtime_mod, "set_req_ctx", lambda _ctx: "tok")
    monkeypatch.setattr(runtime_mod, "reset_req_ctx", lambda _tok: None)
    monkeypatch.setitem(
        sys.modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=lambda **kwargs: "sdk", current_sdk=SimpleNamespace(set=lambda _s: "s", reset=lambda _t: None)),
    )

    async def _async_handler(*_a, **_k):
        return {"async": True}

    monkeypatch.setattr(
        runtime_mod.importlib,
        "import_module",
        lambda name: SimpleNamespace(handler=_async_handler),
    )

    rt = runtime_mod.ModuleRuntime()
    module = SimpleNamespace(
        name="m",
        path=str(tmp_path),
        is_builtin=True,
        access=[],
        allowed_imports=[],
    )

    out1 = await rt.invoke(
        module=module,
        operation="command",
        payload={
            "handler_module": "x",
            "handler_name": "handler",
            "command_name": "demo.command",
            "call_args": [],
            "call_kwargs": {},
            "session": {},
        },
        session={"session_key": "s"},
        persistent=True,
    )
    assert out1["async"] is True
    assert rt._handles

    out2 = await rt.invoke(
        module=module,
        operation="command",
        payload={
            "handler_module": "x",
            "handler_name": "handler",
            "command_name": "demo.command",
            "call_args": [],
            "call_kwargs": {},
            "session": {},
        },
        session={"session_key": "s"},
        persistent=True,
    )
    assert out2["async"] is True
    rt.stop_module("m")
    assert not rt._handles

    # get_module_runtime branch when runtime already exists
    shared_rt = runtime_mod.ModuleRuntime()
    monkeypatch.setattr(runtime_mod, "app_ctx", lambda: SimpleNamespace(module_runtime=shared_rt))
    assert runtime_mod.get_module_runtime() is shared_rt


@pytest.mark.asyncio
async def test_module_runtime_lock_key_serializes_per_action(monkeypatch, tmp_path: Path):
    active = 0
    max_active = 0

    async def _invoke_subject(**_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.02)
        active -= 1
        return {"ok": True}

    monkeypatch.setattr(
        runtime_mod.ModuleRuntime,
        "_invoke_subject",
        staticmethod(_invoke_subject),
    )
    rt = runtime_mod.ModuleRuntime()
    module = SimpleNamespace(
        name="m",
        path=str(tmp_path),
        is_builtin=True,
        access=[],
        allowed_imports=[],
    )
    session = {"session_key": "s", "current_path": "/action"}
    payload = {
        "handler_module": "x",
        "handler_name": "handler",
        "action_name": "demo.action",
        "ctx": {},
        "session": session,
    }

    await asyncio.gather(
        rt.invoke(
            module=module,
            operation="action",
            payload=payload,
            session=session,
            persistent=True,
            lock_key="action:a",
        ),
        rt.invoke(
            module=module,
            operation="action",
            payload=payload,
            session=session,
            persistent=True,
            lock_key="action:b",
        ),
    )
    assert max_active == 2

    active = 0
    max_active = 0
    await asyncio.gather(
        rt.invoke(
            module=module,
            operation="action",
            payload=payload,
            session=session,
            persistent=True,
            lock_key="action:a",
        ),
        rt.invoke(
            module=module,
            operation="action",
            payload=payload,
            session=session,
            persistent=True,
            lock_key="action:a",
        ),
    )
    assert max_active == 1
