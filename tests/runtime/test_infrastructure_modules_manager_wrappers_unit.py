from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

import democrai.core.infrastructure.modules.constants as constants_mod
import democrai.core.infrastructure.modules.manager as manager_mod


def test_manager_top_level_helpers_and_arch_mapping():
    assert not hasattr(manager_mod, "_parse_cron_field")
    assert not hasattr(manager_mod, "_cron_matches")
    assert not hasattr(manager_mod, "_next_cron_run")
    assert not hasattr(manager_mod, "_CTX")
    assert constants_mod.CURRENT_PLATFORM
    assert constants_mod.CURRENT_ARCH


def test_module_init_and_method_wrappers(monkeypatch):
    monkeypatch.setattr(manager_mod, "validate_module_name", lambda name: f"ok:{name}")
    monkeypatch.setattr(manager_mod, "resolve_module_resource", lambda path, icon: f"{path}:{icon}")

    manifest = {
        "name": "demo",
        "label": "Demo",
        "version": "2.0.0",
        "type": "python",
        "requirements": {"core": ">=1.0.0"},
        "platforms": {"linux": {"arch": ["x86_64"]}},
        "auth": {"roles": ["admin"]},
        "icon": "icon.svg",
        "sidebar_position": "bottom",
        "authenticated_label": "Auth",
        "authenticated_icon": "Lock",
        "description": "desc",
        "priority": "NaN",
        "allowed_imports": ["sdk"],
        "access": [
            {
                "resource_type": "network",
                "operation": "receive",
                "target": "https://one",
            },
            {
                "resource_type": "filesystem",
                "operation": "read",
                "target": "/tmp/a",
            },
        ],
    }
    module = manager_mod.Module("/mod", manifest, is_builtin=False, owner_id="owner-1")
    assert module.name == "ok:demo"
    assert module.icon == "/mod:icon.svg"
    assert module.priority == 0
    targets = [rule.resource.target for rule in module.access]
    assert "https://one" in targets
    assert "/tmp/a" in targets

    calls = []

    def _rec(name, ret=None):
        def _f(*args, **kwargs):
            calls.append((name, args, kwargs))
            return ret if ret is not None else name

        return _f

    async def _rec_async(name):
        calls.append((name, (), {}))
        return name

    monkeypatch.setattr(manager_mod, "module_version_match", lambda current, required: (current, required) == ("1.0.0", ">=1.0"))
    monkeypatch.setattr(manager_mod, "validate_compatibility", _rec("validate_compatibility"))
    monkeypatch.setattr(manager_mod, "load_modules", _rec("load_modules"))
    monkeypatch.setattr(manager_mod, "load_python_modules", _rec("load_python_modules"))
    monkeypatch.setattr(manager_mod, "load_sidebar_entries_from_init", _rec("load_sidebar_entries_from_init"))
    monkeypatch.setattr(manager_mod, "normalize_sidebar_entry", _rec("normalize_sidebar_entry", {"ok": True}))
    monkeypatch.setattr(manager_mod, "start_background_commands", _rec("start_background_commands"))
    monkeypatch.setattr(manager_mod, "state_for", _rec("state_for", "state"))
    monkeypatch.setattr(manager_mod, "refresh_state", _rec("refresh_state", "refresh"))
    monkeypatch.setattr(manager_mod, "invoke_command", lambda self, definition, stop_event=None: _rec_async("invoke_command"))
    monkeypatch.setattr(manager_mod, "track_task", _rec("track_task"))
    monkeypatch.setattr(manager_mod, "start_managed_command", _rec("start_managed_command"))
    monkeypatch.setattr(manager_mod, "start_scheduled_command", _rec("start_scheduled_command"))
    monkeypatch.setattr(manager_mod, "compute_next_run", _rec("compute_next_run", datetime(2026, 1, 1, 10, 0, 0)))
    monkeypatch.setattr(manager_mod, "lease_heartbeat", lambda self, command_name: _rec_async("lease_heartbeat"))
    monkeypatch.setattr(manager_mod, "stop_module", _rec("stop_module"))
    monkeypatch.setattr(manager_mod, "reload_module", _rec("reload_module"))

    assert module._version_match("1.0.0", ">=1.0") is True
    assert module.validate_compatibility() == "validate_compatibility"
    assert module.load_modules() == "load_modules"
    assert module._load_python_modules("modules.demo") == "load_python_modules"
    assert module._load_sidebar_entries_from_init(SimpleNamespace()) == "load_sidebar_entries_from_init"
    assert module._normalize_sidebar_entry({"action": {"name": "go"}}, index=0) == {"ok": True}
    assert asyncio.run(module.start_background_commands()) == "start_background_commands"
    assert module._state_for(SimpleNamespace(name="c")) == "state"
    assert module._refresh_state(SimpleNamespace(name="c")) == "refresh"
    assert asyncio.run(module._invoke_command(SimpleNamespace(name="c"))) == "invoke_command"
    assert asyncio.run(module._lease_heartbeat("c")) == "lease_heartbeat"
    task = object()
    assert module._track_task(task) == "track_task"
    assert module._start_managed_command(SimpleNamespace(name="x"), restart_on_exit=True, run_once_after_completion=False) == "start_managed_command"
    assert module._start_scheduled_command(SimpleNamespace(name="x")) == "start_scheduled_command"
    assert isinstance(module._compute_next_run(SimpleNamespace(name="x"), datetime(2026, 1, 1, 9, 0, 0)), datetime)
    assert module.stop() == "stop_module"
    assert module.reload() == "reload_module"
    assert calls


def test_module_manager_wrappers(monkeypatch):
    manager = manager_mod.ModuleManager()
    manager._modules["m1"] = SimpleNamespace(name="m1")
    assert manager.get_module("m1").name == "m1"
    assert manager.get_all_modules()[0].name == "m1"
    assert manager.get_module("missing") is None

    calls = []

    def _rec(name, ret=None):
        def _f(*args, **kwargs):
            calls.append((name, args, kwargs))
            return ret if ret is not None else name

        return _f

    async def _start_all(self):
        calls.append(("start_all_modules", (self,), {}))
        return "started"

    async def _ensure(self):
        calls.append(("ensure_started", (self,), {}))
        return "ensured"

    monkeypatch.setattr(manager_mod, "configure_trust", _rec("configure_trust"))
    monkeypatch.setattr(manager_mod, "is_trusted", _rec("is_trusted", True))
    monkeypatch.setattr(manager_mod, "discover_modules", _rec("discover_modules", ["x"]))
    monkeypatch.setattr(manager_mod, "try_register_module", _rec("try_register_module"))
    monkeypatch.setattr(manager_mod, "enable_runtime", _rec("enable_runtime"))
    monkeypatch.setattr(manager_mod, "start_all_modules", _start_all)
    monkeypatch.setattr(manager_mod, "ensure_started", _ensure)
    monkeypatch.setattr(manager_mod, "schedule_startup", _rec("schedule_startup"))
    monkeypatch.setattr(manager_mod, "shutdown", _rec("shutdown"))
    monkeypatch.setattr(manager_mod, "reload_all_modules", _rec("reload_all_modules"))

    assert manager.configure_trust(trust_mode="all") == "configure_trust"
    assert manager._is_trusted("m1", is_builtin=True) is True
    assert manager.discover_modules("/mods", is_builtin=True, load_ui=False) == ["x"]
    assert manager._try_register_module("/mods/x", is_builtin=False, load_ui=True) == "try_register_module"
    assert manager.enable_runtime() == "enable_runtime"
    assert asyncio.run(manager.start_all_modules()) == "started"
    assert asyncio.run(manager.ensure_started()) == "ensured"
    assert manager.schedule_startup(loop=None) == "schedule_startup"
    assert manager.shutdown() == "shutdown"
    assert manager.reload_all_modules() == "reload_all_modules"
    assert calls
