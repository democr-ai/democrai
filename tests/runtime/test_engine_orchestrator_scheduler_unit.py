from __future__ import annotations

import asyncio

import pytest

from democrai.core.application.ai.engine.orchestrator.batching import (
    EngineBatchingCoordinator,
)
from democrai.core.application.ai.engine.orchestrator.jobs import EngineJobRegistry
from democrai.core.application.ai.engine.orchestrator.scheduler import (
    EngineScheduler,
    EngineSchedulerConfig,
    EngineSchedulerQueueFull,
)


def _job(registry: EngineJobRegistry, request_id: str, payload: dict | None = None):
    return registry.create_job(
        request_id=request_id,
        pipeline_id=f"pipeline-{request_id}",
        selector_type="model_registry_id",
        method="generate_completion",
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_engine_scheduler_executes_submitted_job():
    registry = EngineJobRegistry()
    seen = []

    async def executor(job):
        seen.append(job.request_id)
        return {"ok": True}

    scheduler = EngineScheduler(
        registry=registry,
        executor=executor,
        config=EngineSchedulerConfig(worker_count=1),
    )
    scheduler.start()
    job = _job(registry, "request-1")

    await scheduler.submit(job)

    assert await asyncio.wait_for(job.result_future, timeout=1) == {"ok": True}
    assert seen == ["request-1"]
    assert job.snapshot()["status"] == "done"
    await scheduler.stop()


@pytest.mark.asyncio
async def test_engine_scheduler_rejects_when_queue_full():
    registry = EngineJobRegistry()
    gate = asyncio.Event()

    async def executor(_job):
        await gate.wait()

    scheduler = EngineScheduler(
        registry=registry,
        executor=executor,
        config=EngineSchedulerConfig(max_queue_depth=1, worker_count=1),
    )
    scheduler.start()
    running = _job(registry, "request-1")
    queued = _job(registry, "request-2")
    rejected = _job(registry, "request-3")

    await scheduler.submit(running)
    await asyncio.sleep(0)
    await scheduler.submit(queued)

    with pytest.raises(EngineSchedulerQueueFull):
        await scheduler.submit(rejected)

    assert rejected.snapshot()["status"] == "error"
    assert rejected.snapshot()["error"] == "engine_orchestrator_queue_full"
    with pytest.raises(RuntimeError, match="engine_orchestrator_queue_full"):
        await rejected.result_future
    gate.set()
    await asyncio.wait_for(running.result_future, timeout=1)
    await asyncio.wait_for(queued.result_future, timeout=1)
    await scheduler.stop()


@pytest.mark.asyncio
async def test_engine_scheduler_fails_job_when_executor_fails():
    registry = EngineJobRegistry()

    async def executor(_job):
        raise RuntimeError("executor_failed")

    scheduler = EngineScheduler(registry=registry, executor=executor)
    scheduler.start()
    job = _job(registry, "request-1")

    await scheduler.submit(job)

    with pytest.raises(RuntimeError, match="executor_failed"):
        await asyncio.wait_for(job.result_future, timeout=1)
    assert job.snapshot()["status"] == "error"
    assert job.snapshot()["retriable"] is True
    await scheduler.stop()


@pytest.mark.asyncio
async def test_engine_scheduler_cancelled_job_does_not_stop_worker():
    registry = EngineJobRegistry()
    gate = asyncio.Event()

    async def executor(job):
        if job.request_id == "request-1":
            await gate.wait()
        return {"ok": job.request_id}

    scheduler = EngineScheduler(registry=registry, executor=executor)
    scheduler.start()
    first = _job(registry, "request-1")
    second = _job(registry, "request-2")

    await scheduler.submit(first)
    await asyncio.sleep(0)
    assert registry.cancel("request-1", "user_cancelled") is True
    await scheduler.submit(second)

    assert await asyncio.wait_for(second.result_future, timeout=1) == {
        "ok": "request-2"
    }
    await scheduler.stop()


@pytest.mark.asyncio
async def test_engine_scheduler_stop_cancels_queued_jobs_after_drain_timeout():
    registry = EngineJobRegistry()
    gate = asyncio.Event()

    async def executor(_job):
        await gate.wait()

    scheduler = EngineScheduler(
        registry=registry,
        executor=executor,
        config=EngineSchedulerConfig(
            max_queue_depth=2,
            worker_count=1,
            graceful_shutdown_seconds=0.01,
        ),
    )
    scheduler.start()
    running = _job(registry, "request-1")
    queued = _job(registry, "request-2")

    await scheduler.submit(running)
    await scheduler.submit(queued)
    await scheduler.stop()

    assert running.snapshot()["status"] == "cancelled"
    assert queued.snapshot()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_engine_scheduler_does_not_let_one_engine_capacity_block_another():
    class Provider:
        def __init__(self, instance_id: str):
            self._democrai_instance_id = instance_id
            self._democrai_concurrency_enabled = False
            self._democrai_concurrency_limit = 1
            self._democrai_method_batch_sizes = {}

        async def generate_completion(self, **payload):
            await asyncio.sleep(float(payload["delay"]))
            return payload["label"]

    registry = EngineJobRegistry()
    batching = EngineBatchingCoordinator(
        wait_time=0,
        queue_size=32,
        invocation_worker_count=16,
    )
    providers = {
        "a": Provider("engine-a"),
        "b": Provider("engine-b"),
    }

    async def executor(job):
        provider = providers[str(job.payload["provider"])]
        return await batching.invoke_unary(
            job=job,
            provider=provider,
            method=job.method,
            payload={
                "delay": job.payload["delay"],
                "label": job.payload["label"],
            },
        )

    scheduler = EngineScheduler(
        registry=registry,
        executor=executor,
        config=EngineSchedulerConfig(worker_count=1, max_queue_depth=32),
    )
    scheduler.start()
    blocked_jobs = [
        _job(
            registry,
            f"blocked-{index}",
            payload={"provider": "a", "delay": 0.3, "label": f"a-{index}"},
        )
        for index in range(8)
    ]
    fast_job = _job(
        registry,
        "fast",
        payload={"provider": "b", "delay": 0.01, "label": "b"},
    )

    for job in blocked_jobs:
        await scheduler.submit(job)
    await scheduler.submit(fast_job)

    assert await asyncio.wait_for(fast_job.result_future, timeout=0.2) == "b"

    for job in blocked_jobs:
        job.cancel("test cleanup")
    await batching.shutdown()
    await scheduler.stop()
