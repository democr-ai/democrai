from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

import democrai.sdk.decorators as decorators_mod
import democrai.sdk.tasks as tasks_mod


@pytest.mark.asyncio
async def test_decorators_wrappers_and_proxy(monkeypatch):
    calls = []

    def _recorder(kind):
        def _inner(ctx, **kwargs):
            calls.append((kind, ctx, kwargs))
            return f"{kind}:{kwargs.get('name') or kwargs.get('id') or ''}"

        return _inner

    monkeypatch.setattr(
        decorators_mod._action_decorators, "action", _recorder("action")
    )
    monkeypatch.setattr(
        decorators_mod._action_decorators, "function", _recorder("function")
    )
    monkeypatch.setattr(
        decorators_mod._action_decorators, "event_listener", _recorder("event_listener")
    )
    monkeypatch.setattr(
        decorators_mod._action_decorators, "event_slot", _recorder("event_slot")
    )

    monkeypatch.setattr(
        decorators_mod._command_decorators,
        "callable_command",
        _recorder("callable_command"),
    )
    monkeypatch.setattr(
        decorators_mod._command_decorators,
        "scheduled_command",
        _recorder("scheduled_command"),
    )
    monkeypatch.setattr(
        decorators_mod._command_decorators,
        "long_run_command",
        _recorder("long_run_command"),
    )
    monkeypatch.setattr(
        decorators_mod._command_decorators,
        "single_run_command",
        _recorder("single_run_command"),
    )

    monkeypatch.setattr(
        decorators_mod._ui_decorators, "ui_template", _recorder("ui_template")
    )
    monkeypatch.setattr(
        decorators_mod._ui_decorators, "render_hook", _recorder("render_hook")
    )
    monkeypatch.setattr(
        decorators_mod._ui_decorators, "render_hook_slot", _recorder("render_hook_slot")
    )

    monkeypatch.setattr(decorators_mod._ai_decorators, "tool", _recorder("tool"))
    monkeypatch.setattr(decorators_mod._ai_decorators, "agent", _recorder("agent"))
    monkeypatch.setattr(
        decorators_mod._ai_decorators, "pipeline", _recorder("pipeline")
    )

    assert decorators_mod.action("a") == "action:a"
    assert decorators_mod.function("f") == "function:f"
    assert decorators_mod.callable_command("c") == "callable_command:c"
    assert (
        decorators_mod.scheduled_command("s", cron="* * * * *") == "scheduled_command:s"
    )
    assert (
        decorators_mod.long_run_command("lr", restart_on_exit=False)
        == "long_run_command:lr"
    )
    assert decorators_mod.single_run_command("sr") == "single_run_command:sr"
    assert decorators_mod.ui_template("tpl", priority=2) == "ui_template:tpl"
    assert decorators_mod.render_hook("hk", priority=1) == "render_hook:hk"
    assert (
        decorators_mod.render_hook_slot("slot", optional=False, description="d")
        == "render_hook_slot:slot"
    )
    assert decorators_mod.event_listener("evt", priority=3) == "event_listener:evt"
    assert (
        decorators_mod.event_slot("slot", params=["x"], optional=True, description="d")
        == "event_slot:slot"
    )

    assert (
        decorators_mod.tool("t", description="d", input_schema={"type": "object"})
        == "tool:t"
    )
    assert (
        decorators_mod.agent("ag", tools=["t"], skills=["s"], max_iterations=4)
        == "agent:ag"
    )
    assert (
        decorators_mod.pipeline("pl", steps=[{"kind": "tool", "target": "x"}])
        == "pipeline:pl"
    )

    assert len(calls) == 14
    assert all(item[1] is decorators_mod._CTX for item in calls)

    class _Logger:
        def __init__(self):
            self.logs = []

        def warning(self, message, category):
            self.logs.append((message, category))

    logger = _Logger()
    monkeypatch.setattr(
        decorators_mod, "app_ctx", lambda: SimpleNamespace(logger=logger)
    )
    decorators_mod._hook_warning("h")
    decorators_mod._event_warning("e")
    assert logger.logs == [("h", "hook"), ("e", "event")]

    monkeypatch.setattr(decorators_mod, "app_ctx", lambda: SimpleNamespace(logger=None))
    decorators_mod._hook_warning("x")
    decorators_mod._event_warning("y")

    def _fn():
        return None

    _fn.__module__ = "modules.demo.actions"
    assert decorators_mod._get_module_prefix(_fn) == "demo"

    class _WeirdModuleName(str):
        def startswith(self, prefix):
            return prefix == "modules."

        def split(self, sep):
            return ["modules_only"]

    def _fn_weird():
        return None

    _fn_weird.__module__ = _WeirdModuleName("modules.")
    assert decorators_mod._get_module_prefix(_fn_weird) == ""
    assert decorators_mod._get_registry_owner("", "demo.action") == "demo"
    assert decorators_mod._get_registry_owner("", "plain") == "core"
    assert decorators_mod._get_registry_owner("mod", "x") == "mod"

    async def _template(v):
        return v + 1

    wrapped = decorators_mod.template("tmpl")(_template)
    assert getattr(wrapped, "_template_name") == "tmpl"
    assert await wrapped(2) == 3

    def _public():
        return None

    assert decorators_mod.public(_public) is _public
    assert getattr(_public, "_is_public") is True

    home_calls = []
    guest_calls = []
    monkeypatch.setattr(
        decorators_mod,
        "home_page_registry",
        SimpleNamespace(
            register=lambda path, priority=0: home_calls.append((path, priority))
        ),
    )
    monkeypatch.setattr(
        decorators_mod,
        "guest_page_registry",
        SimpleNamespace(
            register=lambda path, priority=0: guest_calls.append((path, priority))
        ),
    )

    def _handler():
        return None

    assert decorators_mod.home_page("/home", priority=2)(_handler) is _handler
    assert decorators_mod.guest_page("/guest", priority=1)(_handler) is _handler
    assert home_calls == [("/home", 2)]
    assert guest_calls == [("/guest", 1)]

    assert decorators_mod.get_registry() is decorators_mod.action_registry


@pytest.mark.asyncio
async def test_tasks_runtime_context_and_query_branches(monkeypatch):
    sdk = SimpleNamespace(
        session={"user": {"id": 1}}, module_name="demo", module_path="/tmp/demo"
    )
    tasks = tasks_mod.Tasks(sdk)

    token_log = []
    monkeypatch.setattr(
        tasks_mod,
        "set_req_ctx",
        lambda ctx: token_log.append(("set", ctx)) or "req-token",
    )
    monkeypatch.setattr(
        tasks_mod, "reset_req_ctx", lambda tok: token_log.append(("reset", tok))
    )

    class _CurrentSDK:
        def set(self, _sdk):
            token_log.append(("sdk-set", _sdk.module_name))
            return "sdk-token"

        def reset(self, token):
            token_log.append(("sdk-reset", token))

    original_client_module = sys.modules.get("democrai.sdk.client")
    monkeypatch.setitem(
        sys.modules, "democrai.sdk.client", SimpleNamespace(current_sdk=_CurrentSDK())
    )
    monkeypatch.setattr(
        tasks,
        "_runtime_guard",
        lambda _ctx, allow_subprocess=False: __import__("contextlib").nullcontext(),
    )

    req = tasks._build_request_context(task_id="t")
    with tasks._task_runtime_context(req):
        token_log.append(("inside", True))

    assert ("reset", "req-token") in token_log
    assert ("sdk-reset", "sdk-token") in token_log

    if original_client_module is not None:
        monkeypatch.setitem(sys.modules, "democrai.sdk.client", original_client_module)

    monkeypatch.setitem(
        sys.modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(
            process_guard_context=lambda **_k: __import__("contextlib").nullcontext()
        ),
    )
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(modules=None),
    )
    core_tasks = tasks_mod.Tasks(
        SimpleNamespace(session={"user": {}}, module_name="core", module_path="")
    )
    with core_tasks._runtime_guard(req):
        pass

    manager_none = SimpleNamespace(task_manager=None)
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx", lambda: manager_none
    )
    assert core_tasks.list_user_tasks(1) == []
    assert core_tasks.get_tasks_by_key("k") == []
    assert core_tasks.get_tasks_by_key_prefix("k") == []

    class _Task:
        def __init__(self, id_, created_at):
            self.id = id_
            self.created_at = created_at

        def to_dict(self):
            return {"id": self.id}

    manager = SimpleNamespace(
        task_manager=SimpleNamespace(
            get_user_tasks_serialized=lambda *_a, **_k: "bad",
            get_tasks_by_key=lambda *_a, **_k: [_Task("older", 1), _Task("newer", 2)],
            get_tasks_by_key_prefix=lambda *_a, **_k: [_Task("p1", 3), _Task("p0", 2)],
        )
    )
    monkeypatch.setattr("democrai.core.runtime.foundation.app.app_ctx", lambda: manager)
    assert core_tasks.list_user_tasks(1) == []
    assert core_tasks.get_tasks_by_key("k") == [{"id": "newer"}, {"id": "older"}]
    assert core_tasks.get_tasks_by_key_prefix("p") == [{"id": "p1"}, {"id": "p0"}]

    manager_err = SimpleNamespace(
        task_manager=SimpleNamespace(
            get_user_tasks_serialized=lambda *_a, **_k: (_ for _ in ()).throw(
                RuntimeError("x")
            ),
            get_tasks_by_key=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")),
            get_tasks_by_key_prefix=lambda *_a, **_k: (_ for _ in ()).throw(
                RuntimeError("x")
            ),
        )
    )
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx", lambda: manager_err
    )
    assert core_tasks.list_user_tasks(1) == []
    assert core_tasks.get_tasks_by_key("k") == []
    assert core_tasks.get_tasks_by_key_prefix("p") == []


@pytest.mark.asyncio
async def test_tasks_coroutine_and_background_error_paths(monkeypatch):
    sdk = SimpleNamespace(
        session={"user": {}}, module_name="demo", module_path="/tmp/demo"
    )
    tasks = tasks_mod.Tasks(sdk)

    async def _reg_async(**kwargs):
        return kwargs["x"]

    monkeypatch.setattr(tasks_mod, "task_registry", {"a": _reg_async})
    out = await tasks._coerce_coroutine("a", x=5)
    assert out == 5

    with pytest.raises(ValueError):
        tasks._coerce_coroutine(object())

    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(task_manager=SimpleNamespace()),
    )
    with pytest.raises(ValueError):
        await tasks.run_background(lambda: None)

    sdk2 = SimpleNamespace(
        session={"user": {"id": 1, "organization_id": 2}},
        module_name="demo",
        module_path="/tmp/demo",
    )
    tasks2 = tasks_mod.Tasks(sdk2)
    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(task_manager=None),
    )
    with pytest.raises(RuntimeError):
        await tasks2.run_background(lambda: None)

    called = []

    async def _update(*args):
        called.append(args)

    monkeypatch.setattr(
        "democrai.core.runtime.foundation.app.app_ctx",
        lambda: SimpleNamespace(task_manager=SimpleNamespace(update_progress=_update)),
    )
    await tasks2.update_progress("t", 0.1, {"x": 1}, "lbl")
    assert called
