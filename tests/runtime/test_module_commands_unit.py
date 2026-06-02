from __future__ import annotations

import democrai.sdk.decorators as mod
from democrai.core.runtime.foundation.registry import ModuleCommandRegistry


def test_callable_command_registers_lifecycle(monkeypatch):
    registry = ModuleCommandRegistry()
    command_names = {}

    monkeypatch.setattr(mod, "module_command_registry", registry)
    monkeypatch.setattr(
        mod.action_registry,
        "register_command",
        lambda name, func: command_names.setdefault("name", name),
    )

    @mod.callable_command("demo.run")
    def _sample():
        return "ok"

    entry = registry.get("demo.run")
    assert _sample() == "ok"
    assert command_names["name"] == "demo.run"
    assert entry is not None
    assert entry.lifecycle == "callable"
    assert entry.func is _sample


def test_scheduled_command_registers_cron(monkeypatch):
    registry = ModuleCommandRegistry()
    monkeypatch.setattr(mod, "module_command_registry", registry)

    @mod.scheduled_command("demo.sync", cron="*/5 * * * *")
    def _sample():
        return "ok"

    entry = registry.get("demo.sync")
    assert entry is not None
    assert entry.lifecycle == "schedule"
    assert entry.cron == "*/5 * * * *"


def test_long_run_and_single_run_register_lifecycle(monkeypatch):
    registry = ModuleCommandRegistry()
    monkeypatch.setattr(mod, "module_command_registry", registry)

    @mod.long_run_command("demo.worker", restart_on_exit=False)
    def _worker():
        return "ok"

    @mod.single_run_command("demo.bootstrap")
    def _bootstrap():
        return "ok"

    long_run = registry.get("demo.worker")
    single_run = registry.get("demo.bootstrap")
    assert long_run is not None
    assert long_run.lifecycle == "long_run"
    assert long_run.restart_on_exit is False
    assert single_run is not None
    assert single_run.lifecycle == "single_run"
