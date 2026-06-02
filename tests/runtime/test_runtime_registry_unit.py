from __future__ import annotations

from types import SimpleNamespace

import pytest

import democrai.core.runtime.foundation.registry as reg_mod


class _Logger:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, *args, **kwargs):
        self.errors.append(args)

    def warning(self, *args, **kwargs):
        self.warnings.append(args)


def test_action_and_task_registry_and_decorator():
    r = reg_mod.ActionRegistry()

    def _fn():
        return 1

    r.register_action("a", _fn)
    r.register_command("c", _fn)
    r.register_function("f", _fn)
    assert r.get_action("a") is _fn
    assert r.get_command("c") is _fn
    assert r.get_function("f") is _fn
    assert r.get_action("missing") is None

    tr = reg_mod.TaskRegistry()
    tr.register("t", _fn)
    assert tr.get("t") is _fn
    assert tr.get("x") is None
    assert tr.get_all()["t"] is _fn

    @reg_mod.task("decorated.task")
    def _decorated():
        return "ok"

    assert reg_mod.task_registry.get("decorated.task") is _decorated


def test_module_command_registry_filters_and_order():
    reg = reg_mod.ModuleCommandRegistry()

    def _a():
        return None

    def _b():
        return None

    reg.register(
        "m.a",
        _a,
        lifecycle="callable",
        module_name="m",
        cron="  */5 * * * *  ",
        interval_seconds=3,
        restart_on_exit=True,
    )
    reg.register(
        "n.b",
        _b,
        lifecycle="schedule",
        module_name="n",
        cron="",
        interval_seconds=None,
        restart_on_exit=False,
    )

    got = reg.get("m.a")
    assert got is not None
    assert got.cron == "*/5 * * * *"
    assert got.interval_seconds == 3.0
    assert got.restart_on_exit is True

    all_cmds = reg.get_all()
    assert [c.name for c in all_cmds] == ["m.a", "n.b"]
    assert [c.name for c in reg.get_all(module_name="m")] == ["m.a"]
    assert [c.name for c in reg.get_all(lifecycle="schedule")] == ["n.b"]


def test_template_registry_validation_and_priority(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(reg_mod, "app_ctx", lambda: SimpleNamespace(logger=logger))

    registry = reg_mod.TemplateRegistry()

    def _valid(session=None):
        return ([{"id": "host", "component": {"SurfaceHost": {"tag": "@main_content"}}}], "full")

    def _valid_high(session=None):
        return ([{"id": "host2", "component": {"SurfaceHost": {"tag": "@main_content"}}}], "full")

    registry.register("full", _valid, priority=1)
    registry.register("full", _valid_high, priority=2)
    assert registry.get("full") is _valid_high
    reg = registry.get_registration("full")
    assert reg is not None and reg.priority == 2
    assert "full" in registry.get_all_names()

    def _multiple_anchor(session=None):
        return (
            [
                {"id": "a", "component": {"SurfaceHost": {"tag": "@main_content"}}},
                {"id": "b", "component": {"SurfaceHost": {"tag": "@main_content"}}},
            ],
            "full",
        )

    with pytest.raises(RuntimeError, match="multiple @main_content"):
        registry.register("bad.multi", _multiple_anchor)
    assert logger.errors

    def _missing_anchor(session=None):
        return ([{"id": "x", "component": {"Box": {}}}], "full")

    with pytest.raises(RuntimeError, match="missing the required @main_content"):
        registry.register("bad.missing", _missing_anchor)

    # non-structural failure => warning only and still register
    def _raise(session=None):
        raise ValueError("needs session")

    registry.register("warn.template", _raise)
    assert logger.warnings
    assert registry.get("warn.template") is _raise


def test_home_guest_hook_event_registries():
    home = reg_mod.HomePageRegistry()
    home.register("/a", priority=1)
    home.register("/b", priority=2)
    assert home.get() == "/b"
    assert home.get_registration() is not None

    guest = reg_mod.GuestPageRegistry()
    guest.register("/g1", priority=0)
    guest.register("/g2", priority=5)
    assert guest.get() == "/g2"

    hook = reg_mod.RenderHookRegistry()

    def _hook1():
        return None

    def _hook2():
        return None

    hook.register("x.slot", _hook1, priority=1, module_name="m")
    hook.register("x.slot", _hook2, priority=2, module_name="n")
    hook.declare("x.slot", module_name="m", optional=False, description="desc")

    listeners = hook.get("x.slot")
    assert [l.func for l in listeners] == [_hook2, _hook1]
    assert hook.get_definition("x.slot") is not None
    assert len(hook.get_definitions()) == 1
    assert len(hook.get_definitions(module_name="m")) == 1
    assert hook.get_definitions(module_name="z") == []

    events = reg_mod.ModuleEventRegistry()

    def _ev1():
        return None

    def _ev2():
        return None

    events.register("e.x", _ev1, priority=1, module_name="m")
    events.register("e.x", _ev2, priority=2, module_name="n")
    events.declare("e.x", module_name="m", params=("a", "b"), optional=True, description="d")

    registered = events.get("e.x")
    assert [r.func for r in registered] == [_ev2, _ev1]
    assert events.get_definition("e.x") is not None
    assert len(events.get_definitions()) == 1
    assert len(events.get_definitions(module_name="m")) == 1
    assert events.get_definitions(module_name="z") == []


def test_global_registries_exist():
    assert reg_mod.action_registry is not None
    assert reg_mod.task_registry is not None
    assert reg_mod.template_registry is not None
    assert reg_mod.home_page_registry is not None
    assert reg_mod.guest_page_registry is not None
    assert reg_mod.render_hook_registry is not None
    assert reg_mod.module_event_registry is not None
    assert reg_mod.module_command_registry is not None
