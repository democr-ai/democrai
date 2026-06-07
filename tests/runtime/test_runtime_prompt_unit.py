from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import democrai.core.application.runtime_prompt.service as service_mod
from democrai.core.application.runtime_prompt.actions import runtime_prompt_response
from democrai.core.application.runtime_prompt.service import RuntimePromptService
from democrai.core.runtime.foundation.app import (
    RequestContext,
    app_ctx,
    reset_req_ctx,
    set_req_ctx,
)


class _Bus:
    def __init__(self) -> None:
        self.messages = []

    def send(self, client_id, message):
        self.messages.append((client_id, message))


class _Registry:
    def __init__(self, connections=()) -> None:
        self._connections = list(connections)

    def get_connections(self, user_id, organization_id=None):
        return list(self._connections)


def _request_context(**overrides):
    payload = {
        "request_id": "req-1",
        "user": 1,
        "role": "super",
        "organization_id": None,
        "access_level": 1,
        "channel": "bus",
        "session_key": "session-1",
    }
    payload.update(overrides)
    return payload


def test_runtime_prompt_rpc_timeout_exceeds_prompt_timeout():
    from democrai.core.application.runtime_prompt.grpc.config import (
        runtime_prompt_rpc_timeout_seconds,
    )

    config = SimpleNamespace(
        get=lambda key, default=None: {
            "runtime_prompt.timeout_seconds": 10,
        }.get(key, default)
    )

    assert runtime_prompt_rpc_timeout_seconds(config, prompt_timeout_seconds=3) == 10
    assert runtime_prompt_rpc_timeout_seconds(config, prompt_timeout_seconds=20) == 25


@pytest.mark.asyncio
async def test_runtime_prompt_client_ask_uses_rpc_timeout_after_prompt_timeout(monkeypatch):
    from democrai.core.application.runtime_prompt.grpc.client import RuntimePromptClient
    from democrai.core.application.runtime_prompt.grpc.proto import runtime_prompt_pb2

    observed = {}
    monkeypatch.setattr(
        app_ctx(),
        "config",
        SimpleNamespace(get=lambda key, default=None: default),
        raising=False,
    )

    class _Stub:
        async def AskRuntimePrompt(self, request, *, timeout=None, metadata=None):
            observed["timeout"] = timeout
            observed["request_timeout"] = request.timeout_seconds
            return runtime_prompt_pb2.RuntimePromptResponse(
                ok=False,
                prompt_id="prompt-1",
                error="runtime_prompt_timeout",
            )

    client = RuntimePromptClient(target="localhost:1", timeout=10)
    monkeypatch.setattr(client, "_stub", lambda: _Stub())
    monkeypatch.setattr(client, "_auth_metadata", lambda: ())

    decision = await client.ask(
        question="Continue?",
        actions=[{"id": "approve", "label": "Approve"}],
        request_context=_request_context(),
        timeout_seconds=20,
    )

    assert observed["request_timeout"] == 20
    assert observed["timeout"] == 25
    assert decision.error == "runtime_prompt_timeout"


@pytest.mark.asyncio
async def test_runtime_prompt_forbidden_does_not_send_modal(monkeypatch):
    bus = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus, "c1")]),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    service = RuntimePromptService()

    decision = await service.ask(
        question="Continue?",
        actions=[{"id": "approve", "label": "Approve"}],
        required_role="super",
        request_context=_request_context(role="user", access_level=3),
        timeout_seconds=0.01,
    )

    assert decision.ok is False
    assert decision.error == "runtime_prompt_forbidden"
    assert bus.messages == []


@pytest.mark.asyncio
async def test_runtime_prompt_valid_response_resolves_future(monkeypatch):
    bus = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus, "c1")]),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    service = RuntimePromptService()

    task = asyncio.create_task(
        service.ask(
            question="Continue?",
            actions=[
                {"id": "approve", "label": "Approve"},
                {"id": "deny", "label": "Deny"},
            ],
            required_role="super",
            required_access_level=1,
            request_context=_request_context(),
            timeout_seconds=1,
        )
    )
    await asyncio.sleep(0)

    assert bus.messages
    prompt_id = next(iter(service._pending))
    response = await service.respond(
        prompt_id=prompt_id,
        action_id="approve",
        user_id=1,
        session_key="session-1",
    )
    decision = await task

    assert response.ok is True
    assert decision.ok is True
    assert decision.action == "approve"
    assert prompt_id not in service._pending


@pytest.mark.asyncio
async def test_runtime_prompt_sends_only_to_matching_session(monkeypatch):
    bus_a = _Bus()
    bus_b = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus_a, "a"), (bus_b, "b")]),
        raising=False,
    )
    monkeypatch.setattr(
        app_ctx(),
        "network",
        SimpleNamespace(
            _client_session_keys={
                (id(bus_a), "a"): "session-1",
                (id(bus_b), "b"): "session-2",
            }
        ),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    service = RuntimePromptService()

    task = asyncio.create_task(
        service.ask(
            question="Continue?",
            actions=[{"id": "approve", "label": "Approve"}],
            request_context=_request_context(),
            timeout_seconds=1,
        )
    )
    await asyncio.sleep(0)

    prompt_id = next(iter(service._pending))
    assert bus_a.messages
    assert bus_b.messages == []

    await service.respond(
        prompt_id=prompt_id,
        action_id="approve",
        user_id=1,
        session_key="session-1",
    )
    await task


@pytest.mark.asyncio
async def test_runtime_prompt_wrong_session_is_rejected(monkeypatch):
    bus = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus, "c1")]),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    service = RuntimePromptService()

    task = asyncio.create_task(
        service.ask(
            question="Continue?",
            actions=[{"id": "approve", "label": "Approve"}],
            request_context=_request_context(),
            timeout_seconds=1,
        )
    )
    await asyncio.sleep(0)

    prompt_id = next(iter(service._pending))
    response = await service.respond(
        prompt_id=prompt_id,
        action_id="approve",
        user_id=1,
        session_key="other-session",
    )

    assert response.ok is False
    assert response.error == "runtime_prompt_session_mismatch"

    await service.respond(
        prompt_id=prompt_id,
        action_id="approve",
        user_id=1,
        session_key="session-1",
    )
    await task


@pytest.mark.asyncio
async def test_runtime_prompt_timeout_cleans_pending(monkeypatch):
    bus = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus, "c1")]),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    service = RuntimePromptService()

    decision = await service.ask(
        question="Continue?",
        actions=[{"id": "approve", "label": "Approve"}],
        request_context=_request_context(),
        timeout_seconds=0.01,
    )

    assert decision.ok is False
    assert decision.error == "runtime_prompt_timeout"
    assert service._pending == {}


@pytest.mark.asyncio
async def test_runtime_prompt_action_permission_is_revalidated(monkeypatch):
    bus = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus, "c1")]),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    service = RuntimePromptService()

    task = asyncio.create_task(
        service.ask(
            question="Continue?",
            actions=[
                {
                    "id": "approve",
                    "label": "Approve",
                    "required_permissions": ["system.engine.model.manage"],
                },
                {"id": "deny", "label": "Deny"},
            ],
            request_context=_request_context(),
            timeout_seconds=1,
        )
    )
    await asyncio.sleep(0)

    prompt_id = next(iter(service._pending))
    denied = await service.respond(
        prompt_id=prompt_id,
        action_id="approve",
        user_id=1,
        session_key="session-1",
    )
    allowed = await service.respond(
        prompt_id=prompt_id,
        action_id="deny",
        user_id=1,
        session_key="session-1",
    )
    decision = await task

    assert denied.ok is False
    assert denied.error == "runtime_prompt_action_forbidden"
    assert allowed.ok is True
    assert decision.action == "deny"


@pytest.mark.asyncio
async def test_runtime_prompt_response_action_closes_modal(monkeypatch):
    service = RuntimePromptService()
    monkeypatch.setattr(
        "democrai.core.application.runtime_prompt.actions.get_runtime_prompt_service",
        lambda: service,
    )

    bus = _Bus()
    monkeypatch.setattr(
        app_ctx(),
        "connection_registry",
        _Registry([(bus, "c1")]),
        raising=False,
    )
    monkeypatch.setattr(service_mod, "get_user_permissions", lambda _user_id: [])
    task = asyncio.create_task(
        service.ask(
            question="Continue?",
            actions=[{"id": "approve", "label": "Approve"}],
            request_context=_request_context(),
            timeout_seconds=1,
        )
    )
    await asyncio.sleep(0)
    prompt_id = next(iter(service._pending))

    token = set_req_ctx(
        RequestContext(
            app=app_ctx(),
            request_id="req-2",
            user=1,
            role="super",
            organization_id=None,
            access_level=1,
            channel="bus",
            session_key="session-1",
            action_name="runtime_prompt_response",
        )
    )
    try:
        sdk = SimpleNamespace(
            effects=SimpleNamespace(
                ui_messages=lambda messages: {
                    "type": "ui_messages",
                    "messages": messages,
                },
                respond=lambda *effects: {"effects": list(effects)},
            )
        )
        result = await runtime_prompt_response(
            {"prompt_id": prompt_id, "action": "approve"},
            {"user": {"id": 1}},
            sdk,
        )
    finally:
        reset_req_ctx(token)

    decision = await task
    assert decision.ok is True
    assert result["effects"][0]["messages"] == [
        {"deleteSurface": {"surfaceId": "drawer"}},
        {"deleteSurface": {"surfaceId": "modal"}}
    ]
