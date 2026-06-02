from __future__ import annotations

import importlib
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from democrai.core.infrastructure.sandbox.os.models import NetworkEndpoint


def test_sandbox_state_helpers(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.state")
    ctx = SimpleNamespace(config=None, modules="mods", os_network_allowlist=None)
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    assert mod.get_current_application_network_allowlist() is None
    assert mod.is_application_network_allowlist_enabled() is False
    assert mod.is_application_network_allowlist_enabled(config=SimpleNamespace()) is False
    assert (
        mod.is_application_network_allowlist_enabled(
            config=SimpleNamespace(get=lambda key, default=False: True)
        )
        is True
    )

    allowlist = SimpleNamespace(endpoints=[1, 2])
    assert mod.set_current_application_network_allowlist(allowlist) is allowlist
    assert ctx.os_network_allowlist is allowlist

    assert mod.is_application_network_allowlist_active() is False
    assert mod.set_application_network_allowlist_active(True) is True
    assert mod.is_application_network_allowlist_active() is True

    captured = {}

    def _build(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(endpoints=[SimpleNamespace(host="api.local", port=443)])

    monkeypatch.setattr(mod, "build_application_network_allowlist", _build)
    out = mod.refresh_application_network_allowlist()
    assert out.endpoints and captured["config"] is None and captured["modules"] == "mods"

    out2 = mod.refresh_application_network_allowlist(
        config="cfg",
        modules="mods2",
        engines=["e"],
        extractors=["x"],
    )
    assert out2.endpoints and captured["config"] == "cfg" and captured["modules"] == "mods2"


@pytest.mark.asyncio
async def test_sandbox_events_listener_and_emit(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.events")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_REGISTERED", False)
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(network=None))

    declared = []
    registered = []
    monkeypatch.setattr(
        mod.module_event_registry,
        "declare",
        lambda *a, **k: declared.append((a, k)),
    )
    monkeypatch.setattr(
        mod.module_event_registry,
        "register",
        lambda *a, **k: registered.append((a, k)),
    )

    mod.register_os_sandbox_event_listeners()
    mod.register_os_sandbox_event_listeners()
    assert len(declared) == 1 and len(registered) == 1

    calls = []

    @contextmanager
    def _bypass():
        calls.append("enter")
        try:
            yield
        finally:
            calls.append("exit")

    def _apply(_allowlist):
        calls.append("apply")

    monkeypatch.setattr(
        mod,
        "refresh_application_network_allowlist",
        lambda: SimpleNamespace(endpoints=[1, 2, 3]),
    )
    monkeypatch.setattr(mod, "is_application_network_allowlist_active", lambda: True)
    monkeypatch.setattr(mod, "process_guard_bypass_context", _bypass)
    monkeypatch.setattr(mod, "apply_application_network_allowlist_with_helper", _apply)

    result = await mod._refresh_application_network_allowlist_listener(payload={"reason": "test"})
    assert result["endpoint_count"] == 3 and result["applied"] is True and "apply" in calls

    monkeypatch.setattr(mod, "is_application_network_allowlist_active", lambda: False)
    calls.clear()
    result2 = await mod._refresh_application_network_allowlist_listener(payload=None)
    assert result2 == {"endpoint_count": 3, "applied": False} and calls == []

    emitted = []

    async def _emit(name, payload, session):
        emitted.append((name, payload, session))
        return ["ok"]

    monkeypatch.setattr(mod, "emit_module_event", _emit)
    out = await mod.emit_application_network_allowlist_refresh_event()
    assert out == ["ok"]
    assert emitted[0][0] == mod.APPLICATION_NETWORK_ALLOWLIST_REFRESH_EVENT
    assert emitted[0][1] == {} and emitted[0][2] == {}


@pytest.mark.asyncio
async def test_sandbox_events_emit_publishes_to_stream_when_network_available(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.events")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)

    broadcasts = []

    class _StreamManager:
        async def broadcast(self, channel_id, data):
            broadcasts.append((channel_id, data))

    ctx = SimpleNamespace(
        network=SimpleNamespace(stream_manager=_StreamManager()),
        node_id="node-a",
        config=None,
    )
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)

    out = await mod.emit_application_network_allowlist_refresh_event(
        payload={"reason": "unit"}
    )
    assert out == []
    assert len(broadcasts) == 1
    channel_id, event = broadcasts[0]
    assert channel_id == mod.APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_ID
    assert event["event_name"] == mod.APPLICATION_NETWORK_ALLOWLIST_REFRESH_STREAM_EVENT
    assert event["source_node_id"] == "node-a"
    assert event["payload"] == {"reason": "unit"}
    assert str(event["event_id"]).strip()


@pytest.mark.asyncio
async def test_sandbox_events_process_deduplicates_event_id(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.events")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_PROCESSED_EVENT_IDS", set())
    monkeypatch.setattr(mod, "_PROCESSED_EVENT_IDS_ORDER", [])

    calls = []

    async def _emit(name, payload, session):
        calls.append((name, payload, session))
        return ["ok"]

    monkeypatch.setattr(mod, "emit_module_event", _emit)

    out1 = await mod.process_application_network_allowlist_refresh_event(
        {"event_id": "evt-1", "reason": "first"}
    )
    out2 = await mod.process_application_network_allowlist_refresh_event(
        {"event_id": "evt-1", "reason": "duplicate"}
    )
    assert out1 == ["ok"]
    assert out2 == []
    assert len(calls) == 1
    assert calls[0][1]["reason"] == "first"


def test_sandbox_events_start_consumer_is_idempotent(monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.events")
    monkeypatch.setattr(mod, "debug_os_sandbox_flow", lambda *a, **k: None)
    monkeypatch.setattr(mod, "_CONSUMER_STARTED", False)

    scheduled = []
    monkeypatch.setattr(
        mod.asyncio,
        "run_coroutine_threadsafe",
        lambda coro, loop: (coro.close(), scheduled.append(loop), SimpleNamespace())[2],
    )
    ctx = SimpleNamespace(network=SimpleNamespace(_loop="loop-1"))
    monkeypatch.setattr(mod, "app_ctx", lambda: ctx)

    mod.start_application_network_allowlist_refresh_consumer()
    mod.start_application_network_allowlist_refresh_consumer()

    assert scheduled == ["loop-1"]

def test_sandbox_observed_paths(tmp_path: Path, monkeypatch):
    mod = importlib.import_module("democrai.core.infrastructure.sandbox.os.observed")
    monkeypatch.setattr(mod, "app_ctx", lambda: SimpleNamespace(config=None))
    monkeypatch.setattr(mod, "data_dir", lambda: tmp_path)

    default_path = mod.get_observed_endpoints_file_path()
    assert default_path.endswith("os_sandbox_observed_endpoints.json")

    configured = mod.get_observed_endpoints_file_path(
        config=SimpleNamespace(get=lambda k, d=None: str(tmp_path / "custom.json"))
    )
    assert configured.endswith("custom.json")
    fallback_from_empty_config = mod.get_observed_endpoints_file_path(
        config=SimpleNamespace(get=lambda k, d=None: "   ")
    )
    assert fallback_from_empty_config.endswith("os_sandbox_observed_endpoints.json")

    # missing file / invalid payload shapes
    missing = mod.collect_observed_runtime_endpoints(
        config=SimpleNamespace(get=lambda k, d=None: str(tmp_path / "missing.json"))
    )
    assert missing == []

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid", encoding="utf-8")
    assert mod.collect_observed_runtime_endpoints(
        config=SimpleNamespace(get=lambda k, d=None: str(invalid))
    ) == []

    not_dict = tmp_path / "not_dict.json"
    not_dict.write_text(json.dumps([]), encoding="utf-8")
    assert mod.collect_observed_runtime_endpoints(
        config=SimpleNamespace(get=lambda k, d=None: str(not_dict))
    ) == []

    no_endpoints = tmp_path / "no_endpoints.json"
    no_endpoints.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert mod.collect_observed_runtime_endpoints(
        config=SimpleNamespace(get=lambda k, d=None: str(no_endpoints))
    ) == []

    # valid + invalid items
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "endpoints": [
                    {"host": "api.local", "port": 443, "protocol": "tcp", "source": "s", "purpose": "p"},
                    {"host": "api.local", "port": 443, "protocol": "tcp"},
                    {"host": "", "port": 443},
                    "bad-item",
                ]
            }
        ),
        encoding="utf-8",
    )
    endpoints = mod.collect_observed_runtime_endpoints(
        config=SimpleNamespace(get=lambda k, d=None: str(valid))
    )
    assert endpoints == [
        NetworkEndpoint(
            host="api.local",
            port=443,
            protocol="tcp",
            source="s",
            purpose="p",
        )
    ]

    valid_scheme_host = tmp_path / "valid_scheme_host.json"
    valid_scheme_host.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "host": "https://api2.local",
                        "port": 443,
                        "protocol": "tcp",
                        "source": "s",
                        "purpose": "p",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    endpoints2 = mod.collect_observed_runtime_endpoints(
        config=SimpleNamespace(get=lambda k, d=None: str(valid_scheme_host))
    )
    assert len(endpoints2) == 1 and endpoints2[0].host == "api2.local"

    # record target branches
    target_file = tmp_path / "targets.json"
    cfg = SimpleNamespace(get=lambda k, d=None: str(target_file))
    assert mod.record_observed_runtime_target("", config=cfg) is False
    assert mod.record_observed_runtime_target("*.example.local:443", config=cfg) is False
    assert mod.record_observed_runtime_target("https://api.local:443", config=cfg) is True
    assert mod.record_observed_runtime_target("https://api.local:443", config=cfg) is False
    monkeypatch.setattr(
        mod,
        "_read_observed_endpoints",
        lambda _cfg=None: [
            SimpleNamespace(host="dup.local", port=443, protocol="tcp"),
        ],
    )
    assert mod.record_observed_runtime_target("https://dup.local:443", config=cfg) is False

    payload = json.loads(target_file.read_text(encoding="utf-8"))
    assert payload["version"] == 1 and payload["endpoints"][0]["host"] == "api.local"


def test_sandbox_runtime_and_proxy_fallback(monkeypatch):
    runtime_mod = importlib.import_module("democrai.core.infrastructure.sandbox.runtime")
    proxy_mod = importlib.import_module("democrai.core.infrastructure.sandbox.proxy_access")

    # proxy fallback branch (no modules/get_module)
    monkeypatch.setattr(proxy_mod, "app_ctx", lambda: SimpleNamespace(modules=None))
    assert proxy_mod.is_module_target_declared(
        "mod",
        "https://example.test",
        operation="receive",
    ) is False
    monkeypatch.setattr(
        proxy_mod,
        "app_ctx",
        lambda: SimpleNamespace(modules=SimpleNamespace(get_module=lambda _name: None)),
    )
    assert proxy_mod.is_module_target_declared(
        "mod",
        "https://example.test",
        operation="receive",
    ) is False

    # runtime wrappers
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.services.external_access",
        SimpleNamespace(check_external_access=lambda **kwargs: {"ok": kwargs}),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.auth.service",
        SimpleNamespace(get_user_permissions=lambda user_id: ["p", str(user_id)]),
    )
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.app",
        SimpleNamespace(req_ctx=lambda: {"req": 1}),
    )
    assert runtime_mod.check_external_access(a=1)["ok"]["a"] == 1
    assert runtime_mod.get_user_permissions(7) == ["p", "7"]
    assert runtime_mod.req_ctx() == {"req": 1}

    # warnings fallback branch
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.runtime.foundation.app",
        SimpleNamespace(app_ctx=lambda: (_ for _ in ()).throw(RuntimeError("boom"))),
    )
    with pytest.warns(UserWarning):
        runtime_mod.log_sandbox_patch_failure("pkg", RuntimeError("x"))

    # import fallback for ExternalAccessApprovalRequired
    monkeypatch.setitem(
        sys.modules,
        "democrai.core.application.services.external_access",
        SimpleNamespace(),
    )
    with pytest.warns(UserWarning):
        reloaded_runtime = importlib.reload(runtime_mod)
    exc = reloaded_runtime.ExternalAccessApprovalRequired(
        resource_type="network",
        operation="receive",
        subject_type="module",
        subject_name="m",
        target="t",
        message="denied",
    )
    assert isinstance(exc, PermissionError) and exc.message == "denied"
