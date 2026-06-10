from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import democrai.core.application.models.entities.mcp_server_registry as mcp_model_mod
import democrai.core.platform.mcp.crypto as mcp_crypto_mod
import democrai.core.platform.mcp.runtime as mcp_runtime_mod
from democrai.core.application.models.context import CoreModelContext
from democrai.core.infrastructure.database.models import Base
from democrai.core.infrastructure.database.models import McpServerRegistry
from democrai.core.platform.mcp.client import McpToolSpec
from democrai.core.platform.mcp.registry import McpServerRecord


@pytest.fixture()
def db_session_local(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(mcp_model_mod, "SessionLocal", SessionLocal)
    monkeypatch.setattr(mcp_runtime_mod, "SessionLocal", SessionLocal, raising=False)
    monkeypatch.setattr(mcp_runtime_mod, "req_ctx", lambda: SimpleNamespace(session_key="sess-1"))

    yield SessionLocal

    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def crypto_key(monkeypatch):
    cfg = SimpleNamespace(get=lambda key, default=None: {"app.engine_config_encryption_key": "test-key"}.get(key, default))
    monkeypatch.setattr(mcp_crypto_mod, "app_ctx", lambda: SimpleNamespace(config=cfg))


def _ctx() -> CoreModelContext:
    return CoreModelContext(
        user_id=1,
        organization_id=10,
        access_level=1,
        module_name="system",
        session={"user": {"id": 1, "organization_id": 10}},
        bypass=False,
    )


def test_mcp_core_model_create_update_delete_and_validation(db_session_local, crypto_key, monkeypatch):
    refresh_calls: list[dict] = []
    monkeypatch.setattr(
        mcp_model_mod,
        "_request_os_allowlist_refresh",
        lambda **kwargs: refresh_calls.append(dict(kwargs)),
    )
    monkeypatch.setattr(
        mcp_model_mod,
        "app_ctx",
        lambda: SimpleNamespace(logger=SimpleNamespace(error=lambda *a, **k: None)),
    )

    model = mcp_model_mod.McpServerRegistryCoreModel(_ctx())

    created = model.create(
        {
            "name": "server-1",
            "transport": "http",
            "endpoint_url": "https://mcp.local/rpc",
            "config": {"headers": {"Authorization": "Bearer token"}},
            "enabled": True,
            "timeout_ms": 20000,
        }
    )
    assert created["name"] == "server-1"
    assert created["transport"] == "http"
    assert created["config"]["headers"]["Authorization"] == "Bearer token"
    assert refresh_calls and refresh_calls[-1]["mode"] == "create"

    updated = model.update(
        int(created["id"]),
        {
            "enabled": False,
            "config": {"headers": {"X-Token": "abc"}},
        },
    )
    assert updated is not None
    assert updated["transport"] == "http"
    assert updated["enabled"] is False
    assert updated["config"]["headers"]["X-Token"] == "abc"
    assert refresh_calls[-1]["mode"] == "update"

    assert model.delete(int(created["id"])) is True
    assert refresh_calls[-1]["mode"] == "delete"

    with pytest.raises(ValueError, match="mcp server name is invalid"):
        model.create(
            {
                "name": "bad_name",
                "transport": "http",
                "endpoint_url": "https://mcp.local/rpc",
            }
        )

    with pytest.raises(ValueError, match="transport must be one of"):
        model.create(
            {
                "name": "server-2",
                "transport": "sse",
                "endpoint_url": "https://mcp.local/rpc",
            }
        )


def test_mcp_config_is_encrypted_at_rest(db_session_local, crypto_key, monkeypatch):
    monkeypatch.setattr(mcp_model_mod, "_request_os_allowlist_refresh", lambda **_kwargs: None)
    model = mcp_model_mod.McpServerRegistryCoreModel(_ctx())
    created = model.create(
        {
            "name": "enc-server",
            "transport": "http",
            "endpoint_url": "https://mcp.local/rpc",
            "config": {"headers": {"Authorization": "Bearer secret"}},
        }
    )
    with db_session_local() as session:
        row = session.query(McpServerRegistry).filter(McpServerRegistry.id == int(created["id"])).first()
        assert row is not None
        encrypted = str(row.config_encrypted or "")
        assert "Bearer secret" not in encrypted
        assert encrypted.strip() != ""


def _install_owner_module(monkeypatch, *, module_name="system", access=()):
    from democrai.core.runtime.foundation.app import app_ctx

    class _Modules:
        def get_module(self, name):
            assert name == module_name
            return SimpleNamespace(access=tuple(access))

    monkeypatch.setattr(app_ctx(), "modules", _Modules(), raising=False)


def _owner_module_rule(module_name: str, target: str):
    from democrai.core.application.access_policy import AccessManifestRule
    from democrai.core.application.access_policy import AccessResource
    from democrai.core.application.access_policy import AccessSubject

    return AccessManifestRule(
        subject=AccessSubject.create("module", module_name),
        resource=AccessResource.create(
            resource_type="filesystem",
            operation="read",
            target=target,
        ),
    )


def test_mcp_runtime_invocation_uses_network_only_guard(monkeypatch):
    runtime = mcp_runtime_mod.McpRuntime()
    owner_rule = _owner_module_rule("system", "/srv/system/files")
    _install_owner_module(monkeypatch, access=(owner_rule,))

    monkeypatch.setattr(
        mcp_runtime_mod,
        "get_server_by_name",
        lambda name: McpServerRecord(
            id=1,
            name=name,
            transport="http",
            endpoint_url="https://mcp.local/rpc",
            config={},
            enabled=True,
            timeout_ms=10000,
        ),
    )
    captured_guard = {}

    class _Guard:
        def __init__(self, **kwargs):
            captured_guard.update(kwargs)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(mcp_runtime_mod, "process_guard_context", lambda **kwargs: _Guard(**kwargs))

    class _Client:
        def __init__(self, _server):
            pass

        def call_tool(self, *, tool_name, arguments):
            return {"tool": tool_name, "arguments": arguments}

    monkeypatch.setattr(mcp_runtime_mod, "McpClient", _Client)

    result = runtime.invoke_tool(
        full_name="mcp.server1.lookup",
        arguments={"q": "hello"},
        module_name="system",
    )
    assert result["tool"] == "lookup"
    assert captured_guard["allow_subprocess"] is False
    network_rules = [
        rule
        for rule in captured_guard["access"]
        if rule.resource.resource_type.value == "network"
    ]
    assert {rule.resource.operation.value for rule in network_rules} == {"connect", "send", "receive"}
    assert {rule.resource.target for rule in network_rules} == {"https://mcp.local/rpc"}
    # The owning module's declared access is inherited by the MCP guard.
    assert any(
        rule.resource.target == "/srv/system/files" for rule in captured_guard["access"]
    )
    assert captured_guard["include_runtime_access"] is False
    assert captured_guard["inherit_parent_access"] is False


def _install_list_tools_stubs(monkeypatch, *, servers_by_name, list_tools_counter):
    _install_owner_module(monkeypatch)
    monkeypatch.setattr(
        mcp_runtime_mod,
        "get_server_by_name",
        lambda name: servers_by_name.get(name),
    )
    class _Guard:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(mcp_runtime_mod, "process_guard_context", lambda **_kwargs: _Guard())

    class _Client:
        def __init__(self, server):
            self._server = server

        def list_tools(self):
            list_tools_counter[self._server.name] = list_tools_counter.get(self._server.name, 0) + 1
            return [
                McpToolSpec(
                    name="lookup",
                    description=f"lookup on {self._server.name}",
                    input_schema={"type": "object", "properties": {}},
                ),
            ]

    monkeypatch.setattr(mcp_runtime_mod, "McpClient", _Client)


def test_mcp_runtime_filters_to_declared_servers_only(monkeypatch):
    runtime = mcp_runtime_mod.McpRuntime()
    servers = {
        "weather": McpServerRecord(
            id=1,
            name="weather",
            transport="http",
            endpoint_url="https://weather.local/rpc",
            config={},
            enabled=True,
            timeout_ms=10000,
        ),
        "github": McpServerRecord(
            id=2,
            name="github",
            transport="http",
            endpoint_url="https://github.local/rpc",
            config={},
            enabled=True,
            timeout_ms=10000,
        ),
    }
    counter: dict[str, int] = {}
    _install_list_tools_stubs(monkeypatch, servers_by_name=servers, list_tools_counter=counter)

    defs_empty = runtime.list_agent_tool_definitions(
        module_name="system", server_names=(),
    )
    assert defs_empty == []
    assert counter == {}

    defs = runtime.list_agent_tool_definitions(
        module_name="system", server_names=("weather",),
    )
    assert [d.name for d in defs] == ["mcp.weather.lookup"]
    assert counter == {"weather": 1}


def test_mcp_runtime_skips_unknown_server_with_log(monkeypatch):
    runtime = mcp_runtime_mod.McpRuntime()
    servers = {
        "weather": McpServerRecord(
            id=1,
            name="weather",
            transport="http",
            endpoint_url="https://weather.local/rpc",
            config={},
            enabled=True,
            timeout_ms=10000,
        ),
    }
    counter: dict[str, int] = {}
    _install_list_tools_stubs(monkeypatch, servers_by_name=servers, list_tools_counter=counter)

    logged: list[str] = []
    monkeypatch.setattr(
        mcp_runtime_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            logger=SimpleNamespace(warning=lambda msg, *a, **k: logged.append(msg))
        ),
    )

    defs = runtime.list_agent_tool_definitions(
        module_name="system",
        server_names=("weather", "missing"),
    )
    assert [d.name for d in defs] == ["mcp.weather.lookup"]
    assert any("missing" in msg and "not_found_or_disabled" in msg for msg in logged)


def test_mcp_runtime_caches_tools_and_invalidates(monkeypatch):
    runtime = mcp_runtime_mod.McpRuntime()
    servers = {
        "weather": McpServerRecord(
            id=1,
            name="weather",
            transport="http",
            endpoint_url="https://weather.local/rpc",
            config={},
            enabled=True,
            timeout_ms=10000,
        ),
    }
    counter: dict[str, int] = {}
    _install_list_tools_stubs(monkeypatch, servers_by_name=servers, list_tools_counter=counter)

    runtime.list_agent_tool_definitions(
        module_name="system", server_names=("weather",),
    )
    runtime.list_agent_tool_definitions(
        module_name="system", server_names=("weather",),
    )
    assert counter["weather"] == 1  # second call served from cache

    runtime.invalidate_tool_cache(server_name="weather")
    runtime.list_agent_tool_definitions(
        module_name="system", server_names=("weather",),
    )
    assert counter["weather"] == 2  # refetched after invalidation


def test_agent_decorator_rejects_mcp_wildcard():
    from types import SimpleNamespace as _NS

    from democrai.core.platform.agents.registry import AgentRegistry
    from democrai.sdk.decorator_helpers.ai import agent as agent_decorator

    mod = _NS(
        agent_registry=AgentRegistry(),
        _get_module_prefix=lambda _func: "testmod",
    )

    decorator = agent_decorator(
        mod,
        name="my_agent",
        mcp_servers=["*"],
    )
    with pytest.raises(ValueError, match="wildcard"):
        decorator(lambda input: None)
