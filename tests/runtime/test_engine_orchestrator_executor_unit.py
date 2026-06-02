from __future__ import annotations

import asyncio

import pytest

from democrai.core.application.ai.engine.orchestrator.executor import EngineJobExecutor
from democrai.core.application.ai.engine.orchestrator.executor import (
    resolver_request_from_job,
)
from democrai.core.application.ai.engine.orchestrator.batching import (
    EngineBatchingCoordinator,
)
from democrai.core.application.ai.engine.orchestrator.jobs import EngineJobRegistry
from democrai.core.runtime.foundation.app import app_ctx


@pytest.fixture(autouse=True)
def _app_logger():
    ctx = app_ctx()
    previous = getattr(ctx, "logger", None)
    ctx.logger = type(
        "Logger",
        (),
        {
            "debug": staticmethod(lambda *_args, **_kwargs: None),
            "info": staticmethod(lambda *_args, **_kwargs: None),
            "warning": staticmethod(lambda *_args, **_kwargs: None),
            "error": staticmethod(lambda *_args, **_kwargs: None),
        },
    )()
    try:
        yield
    finally:
        ctx.logger = previous


def _job(**kwargs):
    payload = {
        "request_id": "request-1",
        "pipeline_id": "pipeline-1",
        "selector_type": "model_registry_id",
        "model_registry_id": 7,
        "method": "generate_completion",
        "payload": {"messages": []},
        "request_context": {"user": 1},
        "security_context": {"scope": "unit"},
    }
    payload.update(kwargs)
    return EngineJobRegistry().create_job(**payload)


@pytest.mark.asyncio
async def test_engine_job_executor_invokes_resolved_provider(monkeypatch):
    class Provider:
        async def generate_completion(self, **payload):
            return {"payload": payload}

    async def fake_resolve_provider(request, *, event_hook=None):
        assert request.model_registry_id == 7
        assert request.HasField("prefer_local") is False
        request.confirm_swap = True
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job()
    await job.next_event()
    job.set_status("resolving")
    await asyncio.sleep(0)
    result = await EngineJobExecutor().execute_unary(job)

    assert result == {"payload": {"messages": []}}
    events = [await job.next_event() for _ in range(5)]
    assert [event.kind for event in events] == [
        "job.resolving",
        "job.loading",
        "engine_orchestrator.provider_resolved",
        "job.batching",
        "engine_batching.wait",
    ]
    assert events[2].payload == {"confirm_swap": True}
    assert events[4].payload == {"batch_size": 1, "batched": False}
    assert (await job.next_event()).kind == "engine_batching.dispatch"
    assert (await job.next_event()).kind == "job.invoking"


@pytest.mark.asyncio
async def test_engine_job_executor_uses_provider_batch_size(monkeypatch):
    class Provider:
        _democrai_method_batch_sizes = {"generate_completion": 4}

        async def generate_completion(self, **payload):
            return {"payload": payload}

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job()
    await job.next_event()
    await job.set_status_async("resolving")

    result = await EngineJobExecutor().execute_unary(job)

    assert result == {"payload": {"messages": []}}
    event = await job.next_event()
    while event.kind != "engine_batching.wait":
        event = await job.next_event()
    assert event.payload == {"batch_size": 4, "batched": False}


@pytest.mark.asyncio
async def test_engine_job_executor_batches_compatible_jobs(monkeypatch):
    class Provider:
        _democrai_instance_id = "instance-1"
        _democrai_method_batch_sizes = {"generate_completion": 2}

        async def generate_completion(self, **payload):
            return {"payload": payload}

    provider = Provider()

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return provider

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    executor = EngineJobExecutor(
        batching=EngineBatchingCoordinator(wait_time=0.2)
    )
    first = _job(request_id="request-1", payload={"messages": ["a"]})
    second = _job(request_id="request-2", payload={"messages": ["b"]})
    await first.next_event()
    await second.next_event()
    await first.set_status_async("resolving")
    await second.set_status_async("resolving")

    results = await asyncio.gather(
        executor.execute_unary(first),
        executor.execute_unary(second),
    )

    assert results == [
        {"payload": {"messages": ["a"]}},
        {"payload": {"messages": ["b"]}},
    ]
    dispatches = []
    for job in (first, second):
        event = await job.next_event()
        while event.kind != "engine_batching.dispatch":
            event = await job.next_event()
        dispatches.append(event.payload)
    assert dispatches == [
        {"batch_size": 2, "effective_batch_size": 2, "batched": True},
        {"batch_size": 2, "effective_batch_size": 2, "batched": True},
    ]
    await executor.shutdown()


@pytest.mark.asyncio
async def test_engine_batching_skips_cancelled_ticket(monkeypatch):
    class Provider:
        _democrai_instance_id = "instance-1"
        _democrai_method_batch_sizes = {"generate_completion": 2}

        async def generate_completion(self, **payload):
            return {"payload": payload}

    provider = Provider()

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return provider

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    executor = EngineJobExecutor(
        batching=EngineBatchingCoordinator(wait_time=0.2)
    )
    cancelled = _job(request_id="request-1", payload={"messages": ["a"]})
    live = _job(request_id="request-2", payload={"messages": ["b"]})
    await cancelled.next_event()
    await live.next_event()
    await cancelled.set_status_async("resolving")
    await live.set_status_async("resolving")

    first_task = asyncio.create_task(executor.execute_unary(cancelled))
    event = await cancelled.next_event()
    while event.kind != "engine_batching.wait":
        event = await cancelled.next_event()
    cancelled.cancel("unit_cancelled")

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(first_task, timeout=1)

    result = await asyncio.wait_for(executor.execute_unary(live), timeout=1)

    assert result == {"payload": {"messages": ["b"]}}
    event = await live.next_event()
    while event.kind != "engine_batching.dispatch":
        event = await live.next_event()
    assert event.payload == {
        "batch_size": 2,
        "effective_batch_size": 1,
        "batched": False,
    }
    await executor.shutdown()


@pytest.mark.asyncio
async def test_engine_batching_shutdown_fails_waiting_ticket(monkeypatch):
    class Provider:
        _democrai_instance_id = "instance-1"
        _democrai_method_batch_sizes = {"generate_completion": 2}

        async def generate_completion(self, **payload):
            return {"payload": payload}

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    executor = EngineJobExecutor(
        batching=EngineBatchingCoordinator(wait_time=10)
    )
    job = _job(payload={"messages": ["a"]})
    await job.next_event()
    await job.set_status_async("resolving")

    task = asyncio.create_task(executor.execute_unary(job))
    event = await job.next_event()
    while event.kind != "engine_batching.wait":
        event = await job.next_event()

    await executor.shutdown()

    with pytest.raises(RuntimeError, match="engine_batching_worker_stopped"):
        await asyncio.wait_for(task, timeout=1)


@pytest.mark.asyncio
async def test_engine_invocation_pool_serializes_calls(monkeypatch):
    entered = []
    release_first = asyncio.Event()

    class Provider:
        _democrai_instance_id = "instance-1"
        _democrai_method_batch_sizes = {"generate_completion": 1}

        async def generate_completion(self, **payload):
            entered.append(payload["messages"][0])
            if payload["messages"][0] == "a":
                await release_first.wait()
            return {"payload": payload}

    provider = Provider()

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return provider

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    executor = EngineJobExecutor(
        batching=EngineBatchingCoordinator(
            wait_time=0,
            invocation_worker_count=1,
        )
    )
    first = _job(request_id="request-1", payload={"messages": ["a"]})
    second = _job(request_id="request-2", payload={"messages": ["b"]})
    await first.next_event()
    await second.next_event()
    await first.set_status_async("resolving")
    await second.set_status_async("resolving")

    first_task = asyncio.create_task(executor.execute_unary(first))
    while entered != ["a"]:
        await asyncio.sleep(0)

    second_task = asyncio.create_task(executor.execute_unary(second))
    await asyncio.sleep(0.05)
    assert entered == ["a"]

    release_first.set()
    assert await asyncio.wait_for(first_task, timeout=1) == {
        "payload": {"messages": ["a"]}
    }
    assert await asyncio.wait_for(second_task, timeout=1) == {
        "payload": {"messages": ["b"]}
    }
    assert entered == ["a", "b"]
    await executor.shutdown()


@pytest.mark.asyncio
async def test_engine_job_executor_records_batching_and_engine_call_pipeline_steps(
    monkeypatch,
):
    from democrai.core.application.ai.pipeline_context import (
        ai_pipeline_context,
        create_ai_pipeline_context,
    )
    import democrai.core.application.observability.service as observability_mod

    class Provider:
        _democrai_instance_id = "instance-1"
        _democrai_method_batch_sizes = {"generate_completion": 1}

        async def generate_completion(self, **payload):
            return {"payload": payload}

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    records = []

    monkeypatch.setattr(
        observability_mod,
        "observability_service",
        type(
            "Observability",
            (),
            {
                "record_ai_model_pipeline_step": staticmethod(
                    lambda **kwargs: records.append(kwargs) or object()
                )
            },
        )(),
    )

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job()
    await job.next_event()
    await job.set_status_async("resolving")
    context = create_ai_pipeline_context(
        root_method="generate_completion",
        request_id="request-1",
    )

    with ai_pipeline_context(context):
        result = await EngineJobExecutor().execute_unary(job)

    assert result == {"payload": {"messages": []}}
    assert [(record["type"], record["name"]) for record in records] == [
        ("engine_batching", "engine_batching.wait"),
        ("engine", "engine.call"),
    ]
    assert records[0]["input"] == {
        "method": "generate_completion",
        "batch_size": 1,
    }
    assert records[0]["output"] == {
        "batch_size": 1,
        "effective_batch_size": 1,
        "batched": False,
    }
    assert records[1]["input"] == {
        "method": "generate_completion",
        "payload_keys": ["messages"],
    }
    assert records[1]["output"] == {"result_type": "dict"}


@pytest.mark.asyncio
async def test_engine_job_executor_applies_resolver_hitl_and_unload_events(monkeypatch):
    class Provider:
        async def generate_completion(self, **payload):
            return {"payload": payload}

    async def fake_resolve_provider(_request, *, event_hook=None):
        await event_hook("waiting_hitl", {"model_to_load": "qwen"})
        await event_hook("unloading", {"to_unload": ["old"]})
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job()
    await job.next_event()
    await job.set_status_async("resolving")

    result = await EngineJobExecutor().execute_unary(job)

    assert result == {"payload": {"messages": []}}
    events = [await job.next_event() for _ in range(5)]
    assert [event.kind for event in events] == [
        "job.resolving",
        "job.waiting_hitl",
        "job.unloading",
        "job.loading",
        "engine_orchestrator.provider_resolved",
    ]
    assert events[1].payload == {"model_to_load": "qwen"}
    assert events[2].payload == {"to_unload": ["old"]}


@pytest.mark.asyncio
async def test_engine_job_executor_validates_provider_through_job(monkeypatch):
    calls = []

    async def fake_validate_provider(request):
        calls.append((request.model_registry_id, request.confirm_swap))
        return {"status": "ok", "model_registry_id": request.model_registry_id}

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "validate_provider", fake_validate_provider)

    job = _job(method="__validate_provider__", confirm_swap=True, payload={})
    await job.next_event()
    await job.set_status_async("resolving")

    result = await EngineJobExecutor().execute_unary(job)

    assert result == {"status": "ok", "model_registry_id": 7}
    assert calls == [(7, True)]
    events = [await job.next_event() for _ in range(2)]
    assert [event.kind for event in events] == [
        "job.resolving",
        "engine_orchestrator.provider_validate",
    ]
    assert events[1].payload == {"confirm_swap": True}


@pytest.mark.asyncio
async def test_engine_job_executor_rejects_stream_result(monkeypatch):
    class Provider:
        async def generate_stream(self):
            yield "chunk"

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job(method="generate_stream", payload={})
    await job.next_event()
    job.set_status("resolving")
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="requires_invoke_stream"):
        await EngineJobExecutor().execute_unary(job)


@pytest.mark.asyncio
async def test_engine_job_executor_errors_when_method_missing(monkeypatch):
    class Provider:
        pass

    async def fake_resolve_provider(_request, *, event_hook=None):
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job(method="missing_method", payload={})
    await job.next_event()
    job.set_status("resolving")
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="engine_orchestrator_method_not_found"):
        await EngineJobExecutor().execute_unary(job)


@pytest.mark.asyncio
async def test_resolver_request_from_job_preserves_routing_fields():
    job = _job(
        selector_type="objective",
        objective="chat",
        capabilities=["text_generation"],
        prefer_local=True,
    )

    request = resolver_request_from_job(job)

    assert request.selector_type == "objective"
    assert request.objective == "chat"
    assert request.capability == "chat"
    assert request.capabilities_json == '["text_generation"]'
    assert request.prefer_local is True
    assert request.HasField("prefer_local") is True


@pytest.mark.asyncio
async def test_engine_job_executor_stream_publishes_chunks(monkeypatch):
    class Provider:
        async def generate_stream(self, **payload):
            yield {"chunk": payload["messages"][0]}
            yield {"chunk": "done"}

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "qwen"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job(method="generate_stream", payload={"messages": ["hello"]})
    await job.next_event()
    await job.set_status_async("resolving")

    await EngineJobExecutor().execute_stream(job)

    events = [await job.next_event() for _ in range(5)]
    assert [event.kind for event in events] == [
        "job.resolving",
        "job.loading",
        "engine_orchestrator.provider_resolved",
        "job.batching",
        "engine_batching.wait",
    ]
    assert (await job.next_event()).kind == "engine_batching.dispatch"
    assert (await job.next_event()).kind == "job.streaming"
    assert (await job.next_event()).payload == {"value": {"chunk": "hello"}}
    assert (await job.next_event()).payload == {"value": {"chunk": "done"}}


@pytest.mark.asyncio
async def test_engine_job_executor_does_not_pass_stream_control_fields_to_provider(monkeypatch):
    class Provider:
        async def generate_completion(self, *, messages, options=None, on_message=None):
            if on_message is not None:
                await on_message({"type": "security.filter", "payload": {"ok": True}})
            return {"messages": messages, "options": options}

    async def fake_resolve_provider(_request, *, event_hook=None):
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job(
        method="generate_completion",
        payload={
            "messages": ["hello"],
            "options": {},
            "_stream_pipeline_messages": True,
        },
    )
    await job.next_event()
    await job.set_status_async("resolving")

    result = await EngineJobExecutor().execute_stream(job)

    assert result is None
    pipeline_event = await job.next_event()
    while pipeline_event.kind != "engine.pipeline_message":
        pipeline_event = await job.next_event()
    assert pipeline_event.payload == {
        "message": {"type": "security.filter", "payload": {"ok": True}}
    }
    chunk_event = await job.next_event()
    while chunk_event.kind != "engine.chunk":
        chunk_event = await job.next_event()
    assert chunk_event.payload == {"value": {"messages": ["hello"], "options": {}}}


@pytest.mark.asyncio
async def test_engine_job_executor_stream_publishes_single_result_as_chunk(monkeypatch):
    class Provider:
        async def transcribe(self, **_payload):
            return {"text": "hello"}

    async def fake_resolve_provider(_request, *, event_hook=None):
        assert event_hook is not None
        await event_hook("loading", {"model_to_load": "whisper"})
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job(method="transcribe", payload={"audio_data": b"abc"})
    await job.next_event()
    await job.set_status_async("resolving")

    await EngineJobExecutor().execute_stream(job)

    events = [await job.next_event() for _ in range(8)]
    assert events[-1].kind == "engine.chunk"
    assert events[-1].payload == {"value": {"text": "hello"}}


@pytest.mark.asyncio
async def test_engine_job_executor_stream_errors_when_method_missing(monkeypatch):
    class Provider:
        pass

    async def fake_resolve_provider(_request, *, event_hook=None):
        return Provider()

    import democrai.core.application.ai.engine.orchestrator.executor as executor_mod

    monkeypatch.setattr(executor_mod, "resolve_provider", fake_resolve_provider)

    job = _job(method="missing_stream", payload={})
    await job.next_event()
    await job.set_status_async("resolving")

    with pytest.raises(RuntimeError, match="engine_orchestrator_method_not_found"):
        await EngineJobExecutor().execute_stream(job)
