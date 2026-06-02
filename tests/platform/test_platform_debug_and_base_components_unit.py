from __future__ import annotations

from types import SimpleNamespace

import pytest

import democrai.sdk.components.base as base_mod
import democrai.core.platform.utils.debug as debug_mod


class _DemoComponent(base_mod.Component):
    type = "Demo"

    def _default_capabilities(self) -> set[str]:
        return {"text.set", "*.append"}


class _WithToDict:
    def to_dict(self):
        return {"wrapped": 1}


def test_bound_helpers_and_value_wrappers():
    assert base_mod.bound("/x") == {
        "type": "store",
        "path": "/x",
        "scope": "auto",
        "default": None,
    }
    assert base_mod.bound.literal(5) == {"type": "literal", "value": 5}
    assert base_mod.bound.store("/p", scope="page", default=1)["scope"] == "page"
    assert base_mod.bound.action("demo.run", args={"a": 1}) == {
        "type": "action",
        "name": "demo.run",
        "args": {"a": 1},
        "default": None,
        "cache_scope": "page",
    }
    assert base_mod.LiteralValue("x") == {"type": "literal", "value": "x"}
    assert base_mod.ActionBoundValue("demo.a", cache_scope="global")["cache_scope"] == "global"


def test_component_serialization_and_mutators():
    parent = _DemoComponent("p1", permissions=["demo.view"])
    child = base_mod.Component("c1")
    parent.children = [child, "c2"]

    parent.set_property("a", 1)
    parent.set_action("go")
    parent.set_on_change_action("chg", {"id": 1}, mode="remote")
    parent.collect_input_ids("x", "", "y")
    parent.track_loading("", "job.run")
    parent.set_error("oops")
    parent.set_required_permissions(("perm.one",))
    parent.set_show_if({"eq": [1, 1]})
    parent.set_hide_if({"eq": [1, 2]})
    parent.set_animation({"kind": "fade"})
    parent.set_auto_refresh(10, on_refresh="refresh.now")

    nested = {
        "list": [1, (2, 3), _WithToDict()],
        "child": child,
    }
    parent.set_prop("nested", nested)

    data = parent.to_dict()
    props = data["component"]["Demo"]

    assert props["action"]["name"] == "go"
    assert props["onChangeMode"] == "remote"
    assert props["collect_input_ids"] == ["x", "y"]
    assert props["track_loading"] == "job.run"
    assert props["error"] == "oops"
    assert props["required_permissions"] == ["perm.one"]
    assert props["show_if"]["eq"] == [1, 1]
    assert props["hide_if"]["eq"] == [1, 2]
    assert props["animation"]["kind"] == "fade"
    assert props["auto_refresh"] == 10
    assert props["on_refresh"] == {"name": "refresh.now", "context": {}}
    assert props["nested"]["list"][2] == {"wrapped": 1}
    assert props["nested"]["child"]["id"] == "c1"
    assert data["children"]["explicitList"][0]["id"] == "c1"
    assert data["children"]["explicitList"][1] == "c2"
    assert data["permissions"] == ["demo.view"]


def test_component_capabilities_and_auto_refresh_variants():
    comp = _DemoComponent("c1")

    assert comp.get_capabilities() == ["*.append", "text.set"]
    assert comp.is_capability_allowed("text", "set") is True
    assert comp.is_capability_allowed("text", "append") is True
    assert comp.is_capability_allowed("", "set") is False

    comp.allow("value.set", ["value.append", "  "], None)
    comp.deny("value.append")
    assert comp.is_capability_allowed("value", "set") is True
    assert comp.is_capability_allowed("value", "append") is False

    comp.mutable_text().mutable_value().mutable_collection("items").interactive()
    assert comp.is_capability_allowed("items", "replace") is True
    assert comp.is_capability_allowed("enabled", "set") is True

    comp.readonly()
    assert comp.get_capabilities() == []
    assert comp.is_capability_allowed("text", "set") is False

    comp.set_auto_refresh(5, on_refresh={"name": "demo.reload", "context": {"x": 1}})
    comp.set_auto_refresh(0, on_refresh="ignored")
    assert comp.props["on_refresh"]["name"] == "demo.reload"

    assert base_mod.Component.capability_key("", "") == "*.set"
    assert base_mod.Component._normalize_capabilities(["a.set", ("b.set", [None, " "])]) == {
        "a.set",
        "b.set",
    }


def test_debug_emit_and_wrappers(monkeypatch, capsys):
    class _Frame:
        filename = "mod.py"
        function = "fn"
        lineno = 12
        frame = object()

    monkeypatch.setattr(debug_mod.os, "getenv", lambda *_a, **_k: "true")
    monkeypatch.setattr(debug_mod.inspect, "stack", lambda context=0: [None, None, _Frame()])
    monkeypatch.setattr(debug_mod.inspect, "getmodule", lambda _f: SimpleNamespace(__name__="external.mod"))

    debug_mod._emit_debug(env_name="X", tag="TAG", event="evt", x=1)
    out = capsys.readouterr().out
    assert "[TAG] evt" in out
    assert "caller_function='fn'" in out

    monkeypatch.setattr(debug_mod.os, "getenv", lambda *_a, **_k: "")
    debug_mod._emit_debug(env_name="X", tag="TAG", event="evt", current_path="/nope")
    assert capsys.readouterr().out == ""

    debug_mod.debug_ui_trace("setup", current_path="/system/setup")
    assert "UI_TRACE" in capsys.readouterr().out

    calls = []

    def _fake_emit(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(debug_mod, "_emit_debug", _fake_emit)
    wrappers = [
        debug_mod.debug_media_flow,
        debug_mod.debug_auth_flow,
        debug_mod.debug_desktop_trace,
        debug_mod.debug_image_switch,
        debug_mod.debug_property_trace,
        debug_mod.debug_surface_trace,
        debug_mod.debug_renderer_trace,
        debug_mod.debug_session_trace,
        debug_mod.debug_ui_trace,
        debug_mod.debug_ipc_trace,
        debug_mod.debug_token_store,
        debug_mod.debug_runtime_shutdown,
        debug_mod.debug_attachment_preview,
        debug_mod.debug_os_sandbox_flow,
    ]
    for fn in wrappers:
        fn("ev", a=1)

    assert len(calls) == len(wrappers)
    assert {call["tag"] for call in calls} >= {"MEDIA_FLOW", "UI_TRACE", "OS_SANDBOX_FLOW"}


def test_debug_caller_fields_empty_when_internal(monkeypatch):
    class _Frame:
        filename = "same.py"
        function = "same"
        lineno = 1
        frame = object()

    monkeypatch.setattr(debug_mod.inspect, "stack", lambda context=0: [None, None, _Frame()])
    monkeypatch.setattr(
        debug_mod.inspect,
        "getmodule",
        lambda _f: SimpleNamespace(__name__=debug_mod.__name__),
    )

    fields = debug_mod._caller_fields()
    assert fields == {"caller_file": "", "caller_function": "", "caller_line": 0}

    for value in ("1", "TRUE", "yes", "on", "0"):
        monkeypatch.setattr(debug_mod.os, "getenv", lambda *_a, v=value, **_k: v)
        enabled = debug_mod._env_enabled("X")
        assert enabled is (value.lower() in {"1", "true", "yes", "on"})
