from __future__ import annotations

import asyncio
from contextvars import ContextVar
from types import SimpleNamespace

import pytest

import democrai.core.platform.events as events_mod


class _Logger:
    def __init__(self):
        self.warning_calls = []
        self.error_calls = []

    def warning(self, message, channel=None):
        self.warning_calls.append((message, channel))

    def error(self, message, channel=None):
        self.error_calls.append((message, channel))


def _ctx(logger=None, modules=None):
    return SimpleNamespace(logger=logger, modules=modules or SimpleNamespace(get_module=lambda name: None))


def test_event_warning_and_error_helpers():
    logger = _Logger()
    events_mod.app_ctx().logger = logger
    events_mod._event_warning("warn")
    events_mod._event_error("err")
    assert logger.warning_calls[-1] == ("warn", "event")
    assert logger.error_calls[-1] == ("err", "event")

    events_mod.app_ctx().logger = None
    events_mod._event_warning("no-op")
    events_mod._event_error("no-op")


def test_build_event_sdk_core_module_and_unknown(monkeypatch):
    logger = _Logger()
    modules = SimpleNamespace(
        get_module=lambda name: SimpleNamespace(path="/m", name=name) if name == "mod" else None
    )
    monkeypatch.setattr(events_mod, "app_ctx", lambda: _ctx(logger=logger, modules=modules))

    ctor_calls = []

    class _SDK:
        def __init__(self, module_path, module_name, current_path="", session=None):
            ctor_calls.append((module_path, module_name, current_path, session))
            self.module_name = module_name

    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.client", SimpleNamespace(SDK=_SDK))

    core_sdk = events_mod._build_event_sdk(
        SimpleNamespace(module_name="core", name="e"),
        {"current_path": "/x"},
    )
    assert core_sdk.module_name == "core"

    mod_sdk = events_mod._build_event_sdk(
        SimpleNamespace(module_name="mod", name="e"),
        {"current_path": "/m"},
    )
    assert mod_sdk.module_name == "mod"

    with pytest.raises(RuntimeError):
        events_mod._build_event_sdk(SimpleNamespace(module_name="missing", name="ev"), {})


@pytest.mark.asyncio
async def test_invoke_event_listener_sync_async_and_error(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(events_mod, "app_ctx", lambda: _ctx(logger=logger))
    current_sdk = ContextVar("current_sdk", default=None)
    monkeypatch.setitem(__import__("sys").modules, "democrai.sdk.client", SimpleNamespace(current_sdk=current_sdk))

    captured = {}

    def _sync_listener(payload, session, sdk, event_name, extra="d"):
        captured["sync"] = (payload, session, sdk, event_name, extra)
        return "ok-sync"

    async def _async_listener(module_sdk, foo):
        await asyncio.sleep(0)
        captured["async"] = (module_sdk, foo)
        return "ok-async"

    def _boom_listener(**kwargs):
        raise RuntimeError("boom")

    reg_sync = SimpleNamespace(func=_sync_listener, module_name="m")
    reg_async = SimpleNamespace(func=_async_listener, module_name="m")
    reg_boom = SimpleNamespace(func=_boom_listener, module_name="m")
    sdk = SimpleNamespace(module_name="m")

    out_sync = await events_mod._invoke_event_listener(
        reg_sync,
        event_name="ev",
        payload={"foo": 1},
        session={"s": 1},
        event_sdk=sdk,
    )
    assert out_sync == "ok-sync"
    assert captured["sync"][4] == "d"

    out_async = await events_mod._invoke_event_listener(
        reg_async,
        event_name="ev",
        payload={"foo": 7},
        session={},
        event_sdk=sdk,
    )
    assert out_async == "ok-async"
    assert captured["async"][1] == 7

    out_boom = await events_mod._invoke_event_listener(
        reg_boom,
        event_name="ev",
        payload={},
        session={},
        event_sdk=sdk,
    )
    assert out_boom is None
    assert logger.error_calls


def test_validate_payload_and_missing_listener_logs(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(events_mod, "app_ctx", lambda: _ctx(logger=logger))

    events_mod._validate_event_payload("ev.unknown", {"x": 1}, None)
    assert any("not declared" in msg for msg, _ in logger.warning_calls)

    definition = SimpleNamespace(params=["a", "b"], optional=False)
    events_mod._validate_event_payload("ev.declared", {"a": 1, "c": 2}, definition)
    assert any("without declared params" in msg for msg, _ in logger.warning_calls)
    assert any("undeclared params" in msg for msg, _ in logger.warning_calls)

    events_mod._log_missing_event_listeners("ev.none", None)
    assert any("undeclared key" in msg for msg, _ in logger.warning_calls)

    events_mod._log_missing_event_listeners("ev.required", SimpleNamespace(optional=False))
    assert any("Expected module event listeners" in msg for msg, _ in logger.warning_calls)

    count_before = len(logger.warning_calls)
    events_mod._log_missing_event_listeners("ev.optional", SimpleNamespace(optional=True))
    assert len(logger.warning_calls) == count_before


@pytest.mark.asyncio
async def test_emit_module_event_paths(monkeypatch):
    logger = _Logger()
    modules = SimpleNamespace(get_module=lambda name: SimpleNamespace(path="/mod", name=name) if name == "mod" else None)
    monkeypatch.setattr(events_mod, "app_ctx", lambda: _ctx(logger=logger, modules=modules))

    current_sdk = ContextVar("current_sdk", default=None)

    class _SDK:
        def __init__(self, module_path, module_name, current_path="", session=None):
            self.module_name = module_name
            self.module_path = module_path

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.sdk.client",
        SimpleNamespace(SDK=_SDK, current_sdk=current_sdk),
    )

    async def _listener(payload, event_name):
        await asyncio.sleep(0)
        return {"payload": payload, "event_name": event_name}

    definition = SimpleNamespace(params=["id"], optional=False)
    reg_ok = SimpleNamespace(name="ev.ok", module_name="mod", func=_listener)
    reg_bad = SimpleNamespace(name="ev.bad", module_name="missing", func=_listener)

    monkeypatch.setattr(
        events_mod,
        "module_event_registry",
        SimpleNamespace(
            get_definition=lambda name: definition if name == "ev.ok" else None,
            get=lambda name: [reg_bad, reg_ok] if name == "ev.ok" else [],
        ),
    )

    out = await events_mod.emit_module_event("ev.ok", payload={"id": 1}, session={"current_path": "/x"})
    assert len(out) == 1
    assert out[0]["event_name"] == "ev.ok"
    assert logger.error_calls  # missing module path

    out_none = await events_mod.emit_module_event("ev.none", payload={"x": 1}, session={})
    assert out_none == []
    assert logger.warning_calls
