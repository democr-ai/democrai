from __future__ import annotations

import asyncio
import contextlib
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import democrai.core.application.ai.engine.orchestrator.resolver as resolver_mod
import democrai.core.application.ai.engine.orchestrator.server as server_mod
from democrai.core.infrastructure.ai.engine.invocation.transports.grpc import EngineOrchestratorClient
from democrai.core.infrastructure.ai.engine.invocation.proto import engine_orchestrator_pb2
from democrai.core.application.ai.pipeline_context import AiPipelineMessage
from democrai.core.application.runtime_prompt.models import RuntimePromptDecision
from democrai.core.runtime.foundation.app import app_ctx


@pytest.fixture(autouse=True)
def _allow_internal_orchestrator_auth(monkeypatch):
    async def _authorize(_context, *, audience, scopes=None):
        return {"aud": audience, "scopes": list(scopes or [])}

    monkeypatch.setattr(server_mod, "require_internal_service_auth", _authorize)


@pytest.fixture(autouse=True)
def _app_logger():
    ctx = app_ctx()
    previous = getattr(ctx, "logger", None)
    ctx.logger = SimpleNamespace(
        debug=lambda *_args, **_kwargs: None,
        info=lambda *_args, **_kwargs: None,
        warning=lambda *_args, **_kwargs: None,
        error=lambda *_args, **_kwargs: None,
    )
    try:
        yield
    finally:
        ctx.logger = previous


def test_engine_orchestrator_prefer_local_is_tristate():
    request = engine_orchestrator_pb2.EngineInvokeRequest()
    assert not request.HasField("prefer_local")

    request.prefer_local = False
    assert request.HasField("prefer_local")
    assert request.prefer_local is False

    enabled = engine_orchestrator_pb2.EngineInvokeRequest(prefer_local=True)
    assert enabled.HasField("prefer_local")
    assert enabled.prefer_local is True


def test_engine_orchestrator_request_uses_background_context_when_missing(monkeypatch):
    monkeypatch.setattr(
        "democrai.core.infrastructure.ai.engine.invocation.client_helpers.current_request_context_payload",
        lambda _origin: {},
    )
    client = EngineOrchestratorClient(target="localhost:1")

    request = client._request(
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin="unit.origin",
    )

    assert request.request_id
    assert '"channel": "background"' in request.request_context_json
    assert '"action_name": "unit.origin"' in request.request_context_json


def test_engine_orchestrator_process_env_includes_parent_pid():
    from democrai.core.application.ai.engine.orchestrator.config import (
        EngineOrchestratorConfig,
    )

    env = EngineOrchestratorConfig.process_env(parent_pid=123)

    assert env["DEMOCRAI_ENGINE_ORCHESTRATOR"] == "1"
    assert env["DEMOCRAI_ENGINE_ORCHESTRATOR_PARENT_PID"] == "123"


def test_engine_action_request_exists_for_provider_api_discovery():
    request = engine_orchestrator_pb2.EngineActionRequest(
        engine_registry_id=3,
        engine_id="openai_compatible",
        method="list_available_models",
    )

    assert request.engine_registry_id == 3
    assert request.engine_id == "openai_compatible"
    assert request.method == "list_available_models"


def test_loaded_model_unload_action_passes_model_registry_id():
    yaml_text = Path("modules/system/utils/ui/yaml/models/model_list.yaml").read_text()

    assert "name: system.unload_loaded_model" in yaml_text
    assert 'model_registry_id: "$item.model_registry_id"' in yaml_text


@pytest.mark.asyncio
async def test_engine_action_rejects_model_runtime_methods():
    service = server_mod.EngineOrchestratorService()

    response = await service.InvokeEngineAction(
        engine_orchestrator_pb2.EngineActionRequest(
            request_id="request-1",
            engine_registry_id=3,
            engine_id="openai_compatible",
            method="generate_completion",
        ),
        SimpleNamespace(),
    )

    assert response.ok is False
    assert response.error == "engine_action_method_not_allowed:generate_completion"


def test_engine_orchestrator_wait_ready_uses_health_check(monkeypatch):
    calls = []
    client = EngineOrchestratorClient(target="localhost:1")

    def _health_check(*, timeout=None):
        calls.append(("health", timeout))
        return True

    def _status(*, timeout=None):
        calls.append(("status", timeout))
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(client, "health_check", _health_check)
    monkeypatch.setattr(client, "status", _status)

    assert client.wait_ready(timeout=1).ok is True
    assert calls[0][0] == "health"
    assert calls[1][0] == "status"


def test_engine_orchestrator_service_uses_scheduler_config(monkeypatch):
    class Config:
        values = {
            "ai.engine_orchestrator.job_terminal_ttl_seconds": 12,
            "ai.engine_orchestrator.job_output_queue_size": 13,
            "ai.engine_orchestrator.scheduler_max_queue_depth": 14,
            "ai.engine_orchestrator.scheduler_submit_timeout_seconds": 1.5,
            "ai.engine_orchestrator.scheduler_worker_count": 2,
            "ai.engine_orchestrator.scheduler_graceful_shutdown_seconds": 3.5,
            "ai.engine_orchestrator.batch_wait_seconds": 0.25,
            "ai.engine_orchestrator.batch_queue_size": 15,
            "ai.engine_orchestrator.runtime_transition_worker_count": 3,
            "ai.engine_orchestrator.invocation_worker_count": 4,
        }

        def get(self, key, default=None):
            return self.values.get(key, default)

    monkeypatch.setattr(server_mod, "app_ctx", lambda: SimpleNamespace(config=Config()))

    service = server_mod.EngineOrchestratorService()

    assert service._job_output_queue_size == 13
    assert service._job_registry._terminal_ttl_seconds == 12
    assert service._scheduler._config.max_queue_depth == 14
    assert service._scheduler._config.submit_timeout_seconds == 1.5
    assert service._scheduler._config.worker_count == 4
    assert service._scheduler._config.graceful_shutdown_seconds == 3.5
    assert service._job_executor._batching._wait_time == 0.25
    assert service._job_executor._batching._queue_size == 15
    assert service._job_executor._batching._invocation_worker_count == 4
    assert service._runtime_transition_worker_count == 3


@pytest.mark.asyncio
async def test_engine_orchestrator_status_includes_active_job_snapshots():
    service = server_mod.EngineOrchestratorService()
    service._job_registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_completion",
    )

    response = await service.Status(
        engine_orchestrator_pb2.EngineStatusRequest(),
        SimpleNamespace(),
    )

    jobs = json.loads(response.active_jobs_json)
    assert response.ok is True
    assert jobs[0]["request_id"] == "request-1"
    assert jobs[0]["pipeline_id"] == "pipeline-1"
    assert jobs[0]["status"] == "queued"


@pytest.mark.asyncio
async def test_engine_orchestrator_cancel_marks_job_and_attempts_runtime_cancel(monkeypatch):
    runtime_cancel_calls = []

    def fake_cancel_runtime_request(request_id):
        runtime_cancel_calls.append(request_id)
        return False

    monkeypatch.setattr(server_mod, "cancel_runtime_request", fake_cancel_runtime_request)
    service = server_mod.EngineOrchestratorService()
    job = service._job_registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_completion",
    )

    response = await service.Cancel(
        engine_orchestrator_pb2.EngineCancelRequest(request_id="request-1"),
        SimpleNamespace(),
    )

    assert response.ok is True
    assert response.cancelled is True
    assert runtime_cancel_calls == ["request-1"]
    assert job.snapshot()["status"] == "cancelled"
    assert service._job_registry.snapshots() == []


@pytest.mark.asyncio
async def test_engine_orchestrator_cancel_uses_runtime_when_job_is_unknown(monkeypatch):
    runtime_cancel_calls = []

    def fake_cancel_runtime_request(request_id):
        runtime_cancel_calls.append(request_id)
        return True

    monkeypatch.setattr(server_mod, "cancel_runtime_request", fake_cancel_runtime_request)
    service = server_mod.EngineOrchestratorService()

    response = await service.Cancel(
        engine_orchestrator_pb2.EngineCancelRequest(request_id="request-1"),
        SimpleNamespace(),
    )

    assert response.ok is True
    assert response.cancelled is True
    assert runtime_cancel_calls == ["request-1"]


@pytest.mark.asyncio
async def test_engine_orchestrator_cancel_records_cancelled_pipeline_step(monkeypatch):
    import democrai.core.application.ai.pipeline_context as pipeline_context_mod

    records = []
    entered = asyncio.Event()
    release = asyncio.Event()

    def fake_record_step(_context, **kwargs):
        records.append(kwargs)

    def fake_cancel_runtime_request(_request_id):
        return False

    async def fake_execute(_job):
        entered.set()
        await release.wait()
        return {"content": "late"}

    class Context:
        def cancelled(self):
            return False

        def time_remaining(self):
            return None

    monkeypatch.setattr(pipeline_context_mod, "_record_step", fake_record_step)
    monkeypatch.setattr(server_mod, "cancel_runtime_request", fake_cancel_runtime_request)
    service = server_mod.EngineOrchestratorService()
    service._scheduler = server_mod.EngineScheduler(
        registry=service._job_registry,
        executor=fake_execute,
    )
    request = engine_orchestrator_pb2.EngineInvokeRequest(
        request_id="request-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_completion",
        payload_json=json.dumps({"messages": []}),
        request_context_json=json.dumps({"request_id": "request-1", "module_name": "system"}),
        security_context_json=json.dumps({"scope": "unit"}),
    )

    invoke_task = asyncio.create_task(service._invoke_unary_job(request, Context()))
    await asyncio.wait_for(entered.wait(), timeout=1)
    await service.Cancel(
        engine_orchestrator_pb2.EngineCancelRequest(request_id="request-1"),
        SimpleNamespace(),
    )

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(invoke_task, timeout=1)

    release.set()
    await service.stop()

    request_steps = [
        record
        for record in records
        if record["name"] == "engine_orchestrator.invoke"
    ]
    assert request_steps[-1]["status"] == "cancelled"
    assert request_steps[-1]["error"] == "request_cancelled"


@pytest.mark.asyncio
async def test_engine_orchestrator_invoke_routes_unary_through_scheduler(monkeypatch):
    calls = []

    async def fake_execute(job):
        calls.append(job.snapshot())
        return {"content": "ok"}

    @contextlib.asynccontextmanager
    async def fake_pipeline_step(**_kwargs):
        yield {}

    class Context:
        def cancelled(self):
            return False

        def time_remaining(self):
            return None

        async def abort(self, code, details):
            raise RuntimeError(f"{code}:{details}")

    monkeypatch.setattr(server_mod, "ai_pipeline_step", fake_pipeline_step)
    service = server_mod.EngineOrchestratorService()
    service._scheduler = server_mod.EngineScheduler(
        registry=service._job_registry,
        executor=fake_execute,
    )

    request = engine_orchestrator_pb2.EngineInvokeRequest(
        request_id="request-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="embed_texts",
        payload_json=json.dumps({"texts": ["hello"]}),
        request_context_json=json.dumps({"request_id": "request-1", "module_name": "system"}),
        security_context_json=json.dumps({"scope": "unit"}),
    )
    response = await service.Invoke(request, Context())

    assert response.ok is True
    assert json.loads(response.result_json) == {"content": "ok"}
    assert calls[0]["request_id"] == "request-1"
    assert calls[0]["model_registry_id"] == 7
    assert calls[0]["method"] == "embed_texts"
    await service.stop()


@pytest.mark.asyncio
async def test_engine_orchestrator_validate_routes_through_scheduler(monkeypatch):
    calls = []

    async def fake_execute(job):
        calls.append(job.snapshot())
        return {"status": "ok", "model_registry_id": job.model_registry_id}

    @contextlib.asynccontextmanager
    async def fake_pipeline_step(**_kwargs):
        yield {}

    class Context:
        def cancelled(self):
            return False

        def time_remaining(self):
            return None

        async def abort(self, code, details):
            raise RuntimeError(f"{code}:{details}")

    monkeypatch.setattr(server_mod, "ai_pipeline_step", fake_pipeline_step)
    service = server_mod.EngineOrchestratorService()
    service._scheduler = server_mod.EngineScheduler(
        registry=service._job_registry,
        executor=fake_execute,
    )
    request = engine_orchestrator_pb2.EngineInvokeRequest(
        request_id="request-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="__validate_provider__",
        payload_json=json.dumps({}),
        request_context_json=json.dumps({"request_id": "request-1", "module_name": "system"}),
        security_context_json=json.dumps({"scope": "unit"}),
    )

    response = await service.Invoke(request, Context())

    assert response.ok is True
    assert json.loads(response.result_json) == {
        "status": "ok",
        "model_registry_id": 7,
    }
    assert calls[0]["method"] == "__validate_provider__"
    await service.stop()


@pytest.mark.asyncio
async def test_engine_orchestrator_invoke_does_not_resubmit_existing_unary_job(monkeypatch):
    calls = []

    async def fake_execute(job):
        calls.append(job.request_id)
        return {"content": "ok"}

    @contextlib.asynccontextmanager
    async def fake_pipeline_step(**_kwargs):
        yield {}

    class Context:
        def cancelled(self):
            return False

        def time_remaining(self):
            return None

        async def abort(self, code, details):
            raise RuntimeError(f"{code}:{details}")

    monkeypatch.setattr(server_mod, "ai_pipeline_step", fake_pipeline_step)
    service = server_mod.EngineOrchestratorService()
    service._scheduler = server_mod.EngineScheduler(
        registry=service._job_registry,
        executor=fake_execute,
    )
    request = engine_orchestrator_pb2.EngineInvokeRequest(
        request_id="request-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="embed_texts",
        payload_json=json.dumps({"texts": ["hello"]}),
        request_context_json=json.dumps({"request_id": "request-1", "module_name": "system"}),
        security_context_json=json.dumps({"scope": "unit"}),
    )

    first = await service.Invoke(request, Context())
    second = await service.Invoke(request, Context())

    assert json.loads(first.result_json) == {"content": "ok"}
    assert json.loads(second.result_json) == {"content": "ok"}
    assert calls == ["request-1"]
    await service.stop()


@pytest.mark.asyncio
async def test_engine_orchestrator_invoke_stream_routes_through_scheduler(monkeypatch):
    @contextlib.asynccontextmanager
    async def fake_pipeline_step(**_kwargs):
        yield {}

    async def fake_execute(job):
        assert job.response_mode == "stream"
        await job.publish_async("engine.chunk", {"value": {"token": "a"}})
        await job.publish_async("engine.chunk", {"value": {"token": "b"}})

    class Context:
        def cancelled(self):
            return False

        def time_remaining(self):
            return None

        async def abort(self, code, details):
            raise RuntimeError(f"{code}:{details}")

    monkeypatch.setattr(server_mod, "ai_pipeline_step", fake_pipeline_step)
    service = server_mod.EngineOrchestratorService()
    service._scheduler = server_mod.EngineScheduler(
        registry=service._job_registry,
        executor=fake_execute,
    )

    request = engine_orchestrator_pb2.EngineInvokeRequest(
        request_id="request-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_stream",
        payload_json=json.dumps({"messages": []}),
        request_context_json=json.dumps({"request_id": "request-1", "module_name": "system"}),
        security_context_json=json.dumps({"scope": "unit"}),
    )
    chunks = []
    async for chunk in service.InvokeStream(request, Context()):
        chunks.append(chunk)

    assert [chunk.kind for chunk in chunks] == [
        "message",
        "message",
        "chunk",
        "chunk",
        "message",
        "end",
    ]
    messages = [json.loads(chunk.chunk_json) for chunk in chunks if chunk.kind == "message"]
    message_types = [message["type"] for message in messages]
    assert "job.resolving" in message_types
    assert "job.done" in message_types
    assert all(message["request_id"] == "request-1" for message in messages)
    assert [json.loads(chunk.chunk_json) for chunk in chunks if chunk.kind == "chunk"] == [
        {"token": "a"},
        {"token": "b"},
    ]
    await service.stop()


@pytest.mark.asyncio
async def test_engine_orchestrator_pipeline_message_event_is_forwarded_raw():
    service = server_mod.EngineOrchestratorService()
    job = service._job_registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_stream",
        response_mode="stream",
    )
    await job.next_event()
    event = SimpleNamespace(
        kind="engine.pipeline_message",
        payload={
            "message": {
                "type": "security.filter",
                "request_id": "request-1",
                "payload": {"ok": True},
            },
        },
    )

    chunk = server_mod._job_event_chunk(job, event)

    assert chunk.kind == "message"
    assert json.loads(chunk.chunk_json) == {
        "type": "security.filter",
        "request_id": "request-1",
        "payload": {"ok": True},
    }


@pytest.mark.asyncio
async def test_engine_orchestrator_invoke_stream_rejects_retained_request_id(monkeypatch):
    @contextlib.asynccontextmanager
    async def fake_pipeline_step(**_kwargs):
        yield {}

    class Context:
        def cancelled(self):
            return False

        def time_remaining(self):
            return None

    monkeypatch.setattr(server_mod, "ai_pipeline_step", fake_pipeline_step)
    service = server_mod.EngineOrchestratorService()
    service._job_registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_stream",
        response_mode="stream",
    )

    request = engine_orchestrator_pb2.EngineInvokeRequest(
        request_id="request-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_stream",
        payload_json=json.dumps({"messages": []}),
        request_context_json=json.dumps({"request_id": "request-1", "module_name": "system"}),
        security_context_json=json.dumps({"scope": "unit"}),
    )

    with pytest.raises(RuntimeError, match="engine_orchestrator_stream_already_attached"):
        async for _chunk in service._invoke_stream_job(request, Context()):
            pass

    await service.stop()


@pytest.mark.asyncio
async def test_engine_orchestrator_pipeline_message_callback_rehydrates_dict():
    seen = []
    payload = {
        "type": "engine.call.started",
        "pipeline_id": "pipeline",
        "current_pipeline_id": "current",
        "parent_pipeline_id": None,
        "request_id": "request",
        "root_method": "generate_stream",
        "payload": {"x": 1},
    }

    await EngineOrchestratorClient._call_callback(seen.append, payload)

    assert isinstance(seen[0], AiPipelineMessage)
    assert seen[0].type == "engine.call.started"


@pytest.mark.asyncio
async def test_engine_orchestrator_resource_swap_prompt_retries_with_confirm(monkeypatch):
    calls = []

    class FakeModelOrchestrator:
        async def _resolve_runtime_provider_by_model_registry_id(
            self,
            model_registry_id,
            *,
            confirm_swap=False,
            event_hook=None,
        ):
            calls.append((model_registry_id, confirm_swap, event_hook is not None))
            if not confirm_swap:
                return {
                    "status": "need_confirmation",
                    "model_to_load": "whisper",
                    "to_unload": ["llm"],
                }
            if event_hook is not None:
                await event_hook("unloading", {"to_unload": ["llm"]})
                await event_hook("loading", {"model_to_load": "whisper"})
            return {"status": "ok", "provider": "provider"}

    import democrai.core.application.ai.orchestrator as ai_orchestrator

    monkeypatch.setattr(ai_orchestrator, "model_orchestrator", FakeModelOrchestrator())

    prompt_calls = []

    async def fake_prompt(*, request, resolved):
        prompt_calls.append((request, resolved))
        return RuntimePromptDecision(
            ok=True,
            prompt_id="prompt-1",
            action="approve",
        )

    monkeypatch.setattr(resolver_mod, "ask_resource_swap_confirmation", fake_prompt)

    request = SimpleNamespace(
        selector_type="model_registry_id",
        model_registry_id=7,
        confirm_swap=False,
        request_context_json="{}",
    )
    resolver_events = []

    async def event_hook(name, payload):
        resolver_events.append((name, payload))

    result = await resolver_mod.resolve_provider_result(
        request,
        allow_prompt=True,
        event_hook=event_hook,
    )

    assert result == {"status": "ok", "provider": "provider"}
    assert calls == [(7, False, True), (7, True, True)]
    assert prompt_calls[0][1]["model_to_load"] == "whisper"
    assert resolver_events == [
        (
            "waiting_hitl",
            {
                "status": "need_confirmation",
                "model_to_load": "whisper",
                "to_unload": ["llm"],
            },
        ),
        ("unloading", {"to_unload": ["llm"]}),
        ("loading", {"model_to_load": "whisper"}),
    ]


@pytest.mark.asyncio
async def test_engine_orchestrator_resource_swap_prompt_records_pipeline_step(monkeypatch):
    steps = []

    @contextlib.asynccontextmanager
    async def fake_pipeline_step(**kwargs):
        step = {"output": {}}
        steps.append((kwargs, step))
        yield step

    class Client:
        async def ask(self, **_kwargs):
            return RuntimePromptDecision(
                ok=True,
                prompt_id="prompt-1",
                action="approve",
            )

        async def close(self):
            return None

    import democrai.core.application.runtime_prompt.grpc.client as prompt_client_mod

    monkeypatch.setattr(resolver_mod, "ai_pipeline_step", fake_pipeline_step)
    monkeypatch.setattr(prompt_client_mod, "RuntimePromptClient", Client)

    request = SimpleNamespace(
        request_context_json='{"user": 1, "session_key": "session"}',
    )
    decision = await resolver_mod.ask_resource_swap_confirmation(
        request=request,
        resolved={
            "model_to_load": "qwen",
            "to_unload": ["gpt-oss"],
        },
    )

    assert decision.action == "approve"
    assert steps[0][0]["type"] == "runtime_prompt"
    assert steps[0][0]["name"] == "engine_resource_swap"
    assert steps[0][1]["output"] == {
        "ok": True,
        "action": "approve",
        "error": None,
        "prompt_id": "prompt-1",
    }


@pytest.mark.asyncio
async def test_engine_orchestrator_runtime_transition_records_pipeline_step(monkeypatch):
    import democrai.core.application.ai.orchestrator as ai_orchestrator
    import democrai.core.application.observability.service as observability_mod
    from democrai.core.application.ai.pipeline_context import (
        ai_pipeline_context,
        create_ai_pipeline_context,
    )

    records = []
    emitted_events = []

    monkeypatch.setattr(
        observability_mod,
        "observability_service",
        SimpleNamespace(
            record_ai_model_pipeline_step=lambda **kwargs: records.append(kwargs) or object()
        ),
    )

    async def event_hook(name, payload):
        emitted_events.append((name, payload))

    async def operation():
        return "runtime-ok"

    context = create_ai_pipeline_context(
        root_method="generate_completion",
        request_id="request-1",
    )
    with ai_pipeline_context(context):
        result = await ai_orchestrator._record_runtime_transition(
            step_name="engine_runtime.load",
            input={"model_registry_id": 7},
            event_hook=event_hook,
            event_name="loading",
            event_payload={"model_registry_id": 7},
            operation=operation,
        )

    assert result == "runtime-ok"
    assert emitted_events == [("loading", {"model_registry_id": 7})]
    assert records[0]["type"] == "engine_runtime"
    assert records[0]["name"] == "engine_runtime.load"
    assert records[0]["status"] == "ok"
    assert records[0]["input"] == {"model_registry_id": 7}
    assert records[0]["output"] == {"ok": True}


@pytest.mark.asyncio
async def test_engine_orchestrator_runtime_transition_pool_serializes(monkeypatch):
    import democrai.core.application.ai.orchestrator as ai_orchestrator
    import democrai.core.application.observability.service as observability_mod
    from democrai.core.application.ai.pipeline_context import (
        ai_pipeline_context,
        create_ai_pipeline_context,
    )

    entered = []
    release_first = asyncio.Event()

    monkeypatch.setattr(
        ai_orchestrator,
        "app_ctx",
        lambda: SimpleNamespace(
            config=SimpleNamespace(
                get=lambda key, default=None: (
                    1
                    if key == "ai.engine_orchestrator.runtime_transition_worker_count"
                    else default
                )
            )
        ),
    )
    monkeypatch.setattr(
        observability_mod,
        "observability_service",
        SimpleNamespace(record_ai_model_pipeline_step=lambda **_kwargs: object()),
    )

    async def operation(name):
        entered.append(name)
        if name == "first":
            await release_first.wait()
        return name

    async def run_transition(name):
        context = create_ai_pipeline_context(
            root_method="generate_completion",
            request_id=f"request-{name}",
        )
        with ai_pipeline_context(context):
            return await ai_orchestrator._record_runtime_transition(
                step_name="engine_runtime.load",
                input={"name": name},
                event_hook=None,
                event_name="loading",
                event_payload={"name": name},
                operation=lambda: operation(name),
            )

    first = asyncio.create_task(run_transition("first"))
    while entered != ["first"]:
        await asyncio.sleep(0)
    second = asyncio.create_task(run_transition("second"))
    await asyncio.sleep(0.05)

    assert entered == ["first"]
    release_first.set()
    assert await asyncio.wait_for(first, timeout=1) == "first"
    assert await asyncio.wait_for(second, timeout=1) == "second"
    assert entered == ["first", "second"]


@pytest.mark.asyncio
async def test_engine_orchestrator_validate_does_not_prompt(monkeypatch):
    class FakeModelOrchestrator:
        async def _resolve_runtime_provider_by_model_registry_id(
            self,
            model_registry_id,
            *,
            confirm_swap=False,
            event_hook=None,
        ):
            return {
                "status": "need_confirmation",
                "model_to_load": "whisper",
                "to_unload": ["llm"],
            }

    import democrai.core.application.ai.orchestrator as ai_orchestrator

    monkeypatch.setattr(ai_orchestrator, "model_orchestrator", FakeModelOrchestrator())

    async def forbidden_prompt(*, request, resolved):
        raise AssertionError("validate path must not ask runtime prompt")

    monkeypatch.setattr(resolver_mod, "ask_resource_swap_confirmation", forbidden_prompt)

    request = SimpleNamespace(
        selector_type="model_registry_id",
        model_registry_id=7,
        confirm_swap=False,
        request_context_json="{}",
    )
    result = await resolver_mod.resolve_provider_result(
        request,
        allow_prompt=False,
    )

    assert result["status"] == "need_confirmation"


@pytest.mark.asyncio
async def test_sdk_ai_returns_provider_when_validate_needs_confirmation(monkeypatch):
    import democrai.core.application.ai.orchestrator as ai_orchestrator
    import democrai.sdk.ai as sdk_ai_mod

    class RemoteProvider:
        pass

    async def get_provider_for_objective(*_args, **_kwargs):
        return {
            "status": "ok",
            "provider": RemoteProvider(),
            "validation": {
                "status": "need_confirmation",
                "model_to_load": "next",
                "to_unload": ["old"],
            },
        }

    monkeypatch.setattr(
        ai_orchestrator.model_orchestrator,
        "get_provider_for_objective",
        get_provider_for_objective,
    )

    result = await sdk_ai_mod.AI(SimpleNamespace()).get_provider_for_objective("chat")

    assert result["status"] == "ok"
    assert isinstance(result["provider"], RemoteProvider)
    assert result["validation"]["status"] == "need_confirmation"
    assert result["validation"]["to_unload"] == ["old"]


@pytest.mark.asyncio
async def test_model_orchestrator_public_provider_uses_invocation_factory(monkeypatch):
    import democrai.core.application.ai.orchestrator as ai_orchestrator
    import democrai.core.infrastructure.ai.engine.invocation.factory as invocation_factory_mod

    calls = []

    class Provider:
        async def validate(self):
            return {"status": "ok"}

    class Factory:
        def provider_for_objective(self, **kwargs):
            calls.append(kwargs)
            return Provider()

    monkeypatch.setattr(
        invocation_factory_mod, "EngineInvocationProviderFactory", Factory
    )

    result = await ai_orchestrator.model_orchestrator.get_provider_for_objective(
        "chat",
        required_capabilities=["chat"],
        prefer_local=True,
    )

    assert result["status"] == "ok"
    assert isinstance(result["provider"], Provider)
    assert calls == [
        {
            "objective": "chat",
            "capabilities": ["chat"],
            "prefer_local": True,
            "confirm_swap": False,
        }
    ]


@pytest.mark.asyncio
async def test_orchestrator_resolver_uses_runtime_resolver(monkeypatch):
    import democrai.core.application.ai.engine.orchestrator.resolver as resolver_mod
    import democrai.core.application.ai.orchestrator as ai_orchestrator

    provider = object()

    async def public_provider(*_args, **_kwargs):
        raise AssertionError("public invocation path must not be used by resolver")

    async def runtime_provider(*_args, **_kwargs):
        return {"status": "ok", "provider": provider}

    monkeypatch.setattr(
        ai_orchestrator.model_orchestrator,
        "get_provider_for_objective",
        public_provider,
    )
    monkeypatch.setattr(
        ai_orchestrator.model_orchestrator,
        "_resolve_runtime_provider_for_objective",
        runtime_provider,
    )

    request = SimpleNamespace(
        selector_type="objective",
        model_registry_id=0,
        objective="chat",
        capability="",
        capabilities_json="[]",
        prefer_local=None,
        confirm_swap=True,
        HasField=lambda field: False if field == "prefer_local" else (_ for _ in ()).throw(ValueError(field)),
    )

    result = await resolver_mod.resolve_provider_result(request, allow_prompt=False)

    assert result == {"status": "ok", "provider": provider}


@pytest.mark.asyncio
async def test_sdk_engines_loaded_models_use_remote_orchestrator(monkeypatch):
    import democrai.core.application.ai.orchestrator as ai_orchestrator
    import democrai.core.infrastructure.ai.engine.invocation.orchestrator as provider_mod
    import democrai.sdk.engines as sdk_engines_mod

    class Client:
        def status(self, *, timeout=None):
            return SimpleNamespace(
                active_instances_json='[{"engine_row_id": 9, "model_registry_id": 12}]',
                active_jobs_json='[{"request_id": "request-1", "status": "loading"}]',
            )

        def list_active_jobs(self, *, offset=0, limit=100):
            assert offset == 0
            assert limit == 100
            return [{"request_id": "request-1", "status": "loading"}]

        def unload_model(self, *, engine_registry_id, model_registry_id):
            return int(engine_registry_id) == 9 and int(model_registry_id) == 12

        def sync_active_engines(self):
            return True

    monkeypatch.delenv("DEMOCRAI_ENGINE_ORCHESTRATOR", raising=False)
    monkeypatch.setattr(
        provider_mod.EngineOrchestratorProviderResolver,
        "provider",
        lambda _self: Client(),
    )
    monkeypatch.setattr(
        ai_orchestrator.model_orchestrator,
        "get_model_by_registry_id",
        lambda _model_registry_id: None,
    )

    engines = sdk_engines_mod.Engines(SimpleNamespace())
    rows = await engines.list_loaded_models()
    jobs = await engines.list_active_jobs()
    unload = await engines.unload_loaded_model(engine_registry_id=9, model_registry_id=12)
    await engines.sync_runtime()

    assert rows[0]["engine_row_id"] == 9
    assert rows[0]["model_registry_id"] == 12
    assert jobs == [{"request_id": "request-1", "status": "loading"}]
    assert unload == {"status": "ok", "unloaded": True}


@pytest.mark.asyncio
async def test_sdk_engines_sync_runtime_runs_provider_call_off_event_loop(monkeypatch):
    import democrai.core.infrastructure.ai.engine.invocation.orchestrator as provider_mod
    import democrai.sdk.engines as sdk_engines_mod

    loop_thread_id = threading.get_ident()
    call_thread_ids: list[int] = []

    class Client:
        def sync_active_engines(self):
            call_thread_ids.append(threading.get_ident())
            return True

    monkeypatch.setattr(
        provider_mod.EngineOrchestratorProviderResolver,
        "provider",
        lambda _self: Client(),
    )

    engines = sdk_engines_mod.Engines(SimpleNamespace())
    await engines.sync_runtime()

    assert call_thread_ids
    assert call_thread_ids[0] != loop_thread_id
