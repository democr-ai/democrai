from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import pytest

import democrai.sdk.hooks as hooks_mod
import democrai.core.platform.utils.discovery as discovery_mod
import democrai.core.platform.utils.env as env_mod
import democrai.core.platform.utils.nvml as nvml_mod
import democrai.core.platform.utils.system as system_mod


class _Logger:
    def __init__(self):
        self.warning_msgs = []
        self.debug_msgs = []
        self.info_msgs = []

    def warning(self, msg):
        self.warning_msgs.append(msg)

    def debug(self, msg):
        self.debug_msgs.append(msg)

    def info(self, msg):
        self.info_msgs.append(msg)


@pytest.mark.asyncio
async def test_hooks_facade_branches(monkeypatch):
    sdk = SimpleNamespace(module_name="mod", session={"k": 1})
    hooks = hooks_mod.Hooks(sdk)

    assert hooks.qualify_render_hook_name("slot") == "mod.slot"
    assert hooks.qualify_render_hook_name("mod.slot") == "mod.slot"
    assert hooks.qualify_render_hook_name("  ") == ""
    assert hooks.qualify_render_hook_name(5) == "5"

    core_hooks = hooks_mod.Hooks(SimpleNamespace(module_name="core", session={}))
    assert core_hooks.qualify_render_hook_name("slot") == "slot"

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.registry",
        SimpleNamespace(render_hook_registry=SimpleNamespace(get_definitions=lambda module_name=None: [module_name])),
    )
    assert hooks.get_render_hook_slots() == [None]
    assert hooks.get_render_hook_slots("mod") == ["mod"]

    async def _resolve(name, params=None, session=None):
        return {"name": name, "params": params, "session": session}

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.platform.ui.hooks",
        SimpleNamespace(resolve_render_hook_components=_resolve),
    )
    resolved = await hooks.resolve_render_hook("slot")
    assert resolved["name"] == "mod.slot"
    assert resolved["params"] == {}
    assert resolved["session"] == {"k": 1}


def test_env_and_nvml_helpers(monkeypatch):
    monkeypatch.setattr(env_mod.os, "getenv", lambda _k: None)
    assert env_mod.get_ipc_server_name() == env_mod.SERVER_NAME
    monkeypatch.setattr(env_mod.os, "getenv", lambda _k: "custom")
    assert env_mod.get_ipc_server_name() == "custom"
    assert env_mod.build_desktop_ipc_server_name(1234).endswith(".1234")

    real_import = __import__

    def _fake_import(name, *args, **kwargs):
        if name == "pynvml":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fake_import)
    assert nvml_mod.load_nvml() is None

    fake_bindings = SimpleNamespace(x=1)
    monkeypatch.setitem(sys.modules, "pynvml", fake_bindings)
    monkeypatch.setattr("builtins.__import__", real_import)
    assert nvml_mod.load_nvml() is fake_bindings

    monkeypatch.setattr(nvml_mod, "nvml", None)
    assert nvml_mod.has_nvml() is False
    monkeypatch.setattr(nvml_mod, "nvml", object())
    assert nvml_mod.has_nvml() is True


def test_discovery_and_system_error_paths(monkeypatch, tmp_path):
    logger = _Logger()
    monkeypatch.setattr(discovery_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    # discover_submodules import error path
    monkeypatch.setattr(discovery_mod.importlib, "import_module", lambda _name: (_ for _ in ()).throw(ImportError("no")))
    assert discovery_mod.discover_submodules("missing.pkg") == []
    assert logger.warning_msgs

    # discover_submodules pkgutil failure path
    pkg = ModuleType("pkg.ok")
    pkg.__path__ = [str(tmp_path)]
    monkeypatch.setattr(discovery_mod.importlib, "import_module", lambda _name: pkg)
    monkeypatch.setattr(discovery_mod.pkgutil, "iter_modules", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("iter fail")))
    assert discovery_mod.discover_submodules("pkg.ok", recursive=False) == []
    assert logger.debug_msgs

    # discover_module_ui_modules with filesystem merge and no ui dir
    module_root = tmp_path / "module"
    (module_root / "ui" / "nested").mkdir(parents=True)
    (module_root / "ui" / "main.py").write_text("x=1\n", encoding="utf-8")
    (module_root / "ui" / "nested" / "sub.py").write_text("x=1\n", encoding="utf-8")
    monkeypatch.setattr(discovery_mod, "discover_submodules", lambda *_a, **_k: ["x.y"])
    merged = discovery_mod.discover_module_ui_modules("modx", str(module_root), is_builtin=True)
    assert any(name.endswith("main") for name in merged)
    assert any(name.endswith("nested.sub") for name in merged)
    assert "x.y" in merged

    no_ui = discovery_mod.discover_module_ui_modules("modx", str(tmp_path / "none"), is_builtin=False)
    assert isinstance(no_ui, list)

    # SystemResourceMonitor branches
    monkeypatch.setattr(system_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))
    monkeypatch.setattr(system_mod.psutil, "virtual_memory", lambda: SimpleNamespace(available=10 * 1024 * 1024, total=20 * 1024 * 1024))

    # nvml None branch in __init__
    monkeypatch.setattr(system_mod, "nvml", None)
    monitor_none = system_mod.SystemResourceMonitor()
    assert monitor_none.get_free_vram_mb() == 0
    assert monitor_none.get_total_vram_mb() == 0

    # nvml init failure branch
    class _BadInit:
        def nvmlInit(self):
            raise RuntimeError("init fail")

    monkeypatch.setattr(system_mod, "nvml", _BadInit())
    monitor_bad = system_mod.SystemResourceMonitor()
    assert monitor_bad.get_resources()["has_nvidia_gpu"] is False

    # runtime VRAM read errors
    class _BadRead:
        def __init__(self):
            self.shutdown_called = 0

        def nvmlInit(self):
            return None

        def nvmlDeviceGetCount(self):
            raise RuntimeError("read fail")

        def nvmlShutdown(self):
            self.shutdown_called += 1

    bad_read = _BadRead()
    monkeypatch.setattr(system_mod, "nvml", bad_read)
    monitor_read = system_mod.SystemResourceMonitor()
    assert monitor_read.get_free_vram_mb() == 0
    assert monitor_read.get_total_vram_mb() == 0

    # shutdown success path with missing logger and shutdown exception fallback print
    monkeypatch.setattr(system_mod, "app_ctx", lambda: (_ for _ in ()).throw(RuntimeError("ctx gone")))
    monitor_read.shutdown()  # inner logger retrieval fails but is swallowed
    assert bad_read.shutdown_called == 1

    class _BadShutdown(_BadRead):
        def nvmlShutdown(self):
            raise RuntimeError("shutdown fail")

    monkeypatch.setattr(system_mod, "nvml", _BadShutdown())
    monitor_shutdown = system_mod.SystemResourceMonitor()
    monitor_shutdown._nvml_initialized = True
    printed = []
    monkeypatch.setattr("builtins.print", lambda msg: printed.append(msg))
    monitor_shutdown.shutdown()
    assert printed

    # global monitor helpers
    system_mod._resource_monitor = None
    first = system_mod.get_resource_monitor()
    second = system_mod.get_resource_monitor()
    assert first is second
    system_mod.shutdown_resource_monitor()
    assert system_mod._resource_monitor is None
