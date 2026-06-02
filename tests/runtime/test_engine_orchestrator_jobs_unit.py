from __future__ import annotations

import asyncio

import pytest

from democrai.core.application.ai.engine.orchestrator.jobs import EngineJobRegistry


@pytest.mark.asyncio
async def test_engine_job_registry_creates_snapshot_and_initial_event():
    registry = EngineJobRegistry()

    job = registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        model_registry_id=7,
        method="generate_completion",
        payload={"messages": [{"role": "user"}]},
        request_context={"user": 1},
        security_context={"scope": "unit"},
    )

    event = await asyncio.wait_for(job.next_event(), timeout=1)

    assert event.kind == "job.created"
    assert event.request_id == "request-1"
    assert event.pipeline_id == "pipeline-1"
    assert registry.get("request-1") is job
    assert registry.snapshots()[0] == {
        "request_id": "request-1",
        "pipeline_id": "pipeline-1",
        "selector_type": "model_registry_id",
        "model_registry_id": 7,
        "objective": None,
        "capabilities": [],
        "prefer_local": None,
        "confirm_swap": False,
        "method": "generate_completion",
        "response_mode": "unary",
        "status": "queued",
        "created_at": registry.snapshots()[0]["created_at"],
        "started_at": None,
        "finished_at": None,
        "error": None,
        "retriable": None,
    }


@pytest.mark.asyncio
async def test_engine_job_status_complete_and_result_future():
    job = EngineJobRegistry().create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="objective",
        objective="chat",
        capabilities=["text_generation"],
        method="generate_completion",
    )
    await job.next_event()

    job.set_status("loading", payload={"model": "qwen"})
    loading_event = await asyncio.wait_for(job.next_event(), timeout=1)
    job.complete({"content": "ok"})
    done_event = await asyncio.wait_for(job.next_event(), timeout=1)

    assert loading_event.kind == "job.loading"
    assert loading_event.payload == {"model": "qwen"}
    assert done_event.kind == "job.done"
    assert await asyncio.wait_for(job.result_future, timeout=1) == {"content": "ok"}
    assert job.snapshot()["status"] == "done"


@pytest.mark.asyncio
async def test_engine_job_failure_sets_future_exception():
    job = EngineJobRegistry().create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="embed_texts",
    )
    await job.next_event()

    job.fail("engine_failed", retriable=True)
    event = await asyncio.wait_for(job.next_event(), timeout=1)

    assert event.kind == "job.error"
    assert event.payload == {"error": "engine_failed", "retriable": True}
    assert job.snapshot()["retriable"] is True
    with pytest.raises(RuntimeError, match="engine_failed"):
        await asyncio.wait_for(job.result_future, timeout=1)


@pytest.mark.asyncio
async def test_engine_job_registry_cancel_marks_terminal_and_hides_from_active_snapshots():
    registry = EngineJobRegistry()
    job = registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_stream",
    )
    await job.next_event()

    assert registry.cancel("request-1", "user_cancelled") is True
    event = await asyncio.wait_for(job.next_event(), timeout=1)

    assert event.kind == "job.cancelled"
    assert event.payload == {"reason": "user_cancelled"}
    assert job.result_future.cancelled()
    assert registry.get("request-1") is job
    assert registry.snapshots() == []
    assert registry.snapshots(include_terminal=True)[0]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_engine_job_registry_reuses_duplicate_request_id_while_retained():
    registry = EngineJobRegistry()
    first = registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_completion",
    )

    second = registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-2",
        selector_type="model_registry_id",
        method="generate_completion",
    )

    assert second is first


@pytest.mark.asyncio
async def test_engine_job_registry_get_or_create_returns_created_flag():
    registry = EngineJobRegistry()

    first, first_created = registry.get_or_create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_completion",
    )
    second, second_created = registry.get_or_create_job(
        request_id="request-1",
        pipeline_id="pipeline-2",
        selector_type="model_registry_id",
        method="generate_completion",
    )

    assert first_created is True
    assert second_created is False
    assert second is first


@pytest.mark.asyncio
async def test_engine_job_registry_prunes_expired_terminal_jobs():
    registry = EngineJobRegistry(terminal_ttl_seconds=0)
    first = registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_completion",
    )
    await first.next_event()
    first.complete({"ok": True})
    await first.result_future
    registry.mark_terminal(first)

    second = registry.create_job(
        request_id="request-1",
        pipeline_id="pipeline-2",
        selector_type="model_registry_id",
        method="generate_completion",
    )

    assert second is not first
    assert second.pipeline_id == "pipeline-2"


@pytest.mark.asyncio
async def test_engine_job_output_queue_is_bounded():
    job = EngineJobRegistry().create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_stream",
        max_queue_size=1,
    )

    publish_task = asyncio.create_task(job.publish_async("chunk", {"index": 1}))
    await asyncio.sleep(0)

    assert not publish_task.done()
    assert (await job.next_event()).kind == "job.created"
    await asyncio.wait_for(publish_task, timeout=1)
    assert (await job.next_event()).kind == "chunk"


@pytest.mark.asyncio
async def test_engine_job_sync_publish_logs_when_queue_is_full(caplog):
    job = EngineJobRegistry().create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_stream",
        max_queue_size=1,
    )

    job.publish("chunk", {"index": 1})
    await asyncio.sleep(0)

    assert "engine_job_event_queue_full" in caplog.text


@pytest.mark.asyncio
async def test_engine_job_cancel_cancels_attached_task():
    job = EngineJobRegistry().create_job(
        request_id="request-1",
        pipeline_id="pipeline-1",
        selector_type="model_registry_id",
        method="generate_completion",
    )

    task = asyncio.create_task(asyncio.sleep(10))
    job.attach_task(task)

    assert job.cancel("user_cancelled") is True
    await asyncio.sleep(0)

    assert task.cancelled()
