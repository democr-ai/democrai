from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass, field
from typing import Any

from democrai.core.application.ai.engine.orchestrator.jobs import EngineJob
from democrai.core.application.ai.pipeline_context import ai_pipeline_step
from democrai.core.platform.utils.identity import to_int_or_zero


@dataclass
class EngineBatchTicket:
    job: EngineJob
    provider: Any
    method: str
    payload: dict[str, Any]
    batch_size: int
    dispatch_future: asyncio.Future = field(init=False)
    created_at: float = field(default_factory=time.perf_counter)

    def __post_init__(self) -> None:
        self.dispatch_future = asyncio.get_running_loop().create_future()

    @property
    def cancelled(self) -> bool:
        return bool(self.job.done or self.dispatch_future.cancelled())

    def cancel(self) -> None:
        if not self.dispatch_future.done():
            self.dispatch_future.cancel()

    def fail(self, error: BaseException | str) -> None:
        if not self.dispatch_future.done():
            self.dispatch_future.set_exception(
                error if isinstance(error, BaseException) else RuntimeError(str(error))
            )


class EngineBatchingCoordinator:
    def __init__(
        self,
        *,
        wait_time: float = 0.05,
        queue_size: int = 256,
        invocation_worker_count: int = 1,
    ) -> None:
        self._wait_time = max(0.0, wait_time)
        self._queue_size = max(1, queue_size)
        self._invocation_worker_count = max(1, invocation_worker_count)
        self._invocation_semaphore = asyncio.Semaphore(self._invocation_worker_count)
        self._workers: dict[str, EngineBatchWorker] = {}
        self._lock = asyncio.Lock()
        self._engine_semaphores: dict[str, dict[str, Any]] = {}
        self._sem_lock = asyncio.Lock()

    async def _get_engine_semaphore(self, provider: Any) -> asyncio.Semaphore:
        instance_id = (
            getattr(provider, "_democrai_instance_id", "")
            or getattr(provider, "instance_id", "")
            or id(provider)
        )

        concurrency_enabled = bool(getattr(provider, "_democrai_concurrency_enabled", False))
        concurrency_limit = int(getattr(provider, "_democrai_concurrency_limit", 1))

        limit = concurrency_limit if concurrency_enabled else 1
        if limit < 1:
            limit = 1

        async with self._sem_lock:
            sem_info = self._engine_semaphores.get(instance_id)
            if sem_info is None or sem_info["limit"] != limit:
                sem_info = {
                    "sem": asyncio.Semaphore(limit),
                    "limit": limit
                }
                self._engine_semaphores[instance_id] = sem_info
            return sem_info["sem"]

    async def invoke_unary(
        self,
        *,
        job: EngineJob,
        provider: Any,
        method: str,
        payload: dict[str, Any],
    ) -> Any:
        target = self._target(provider, method)
        ticket = await self._wait_for_batch(job, provider, method, payload)
        engine_sem = await self._get_engine_semaphore(provider)
        async with engine_sem:
            async with self._invocation_semaphore:
                async with ai_pipeline_step(
                    type="engine",
                    name="engine.call",
                    input=_call_input(ticket),
                ) as step:
                    await job.set_status_async("invoking")
                    _require_engine_quota(job=job, provider=provider)
                    result = target(**payload)
                    if inspect.isawaitable(result):
                        result = await result
                    if hasattr(result, "__aiter__"):
                        raise RuntimeError("engine_orchestrator_stream_method_requires_invoke_stream")
                    step["output"] = {"result_type": type(result).__name__}
                    return result

    async def invoke_stream(
        self,
        *,
        job: EngineJob,
        provider: Any,
        method: str,
        payload: dict[str, Any],
    ) -> None:
        target = self._target(provider, method)
        ticket = await self._wait_for_batch(job, provider, method, payload)
        engine_sem = await self._get_engine_semaphore(provider)
        async with engine_sem:
            async with self._invocation_semaphore:
                async with ai_pipeline_step(
                    type="engine",
                    name="engine.call",
                    input=_call_input(ticket),
                ) as step:
                    await job.set_status_async("streaming")
                    _require_engine_quota(job=job, provider=provider)
                    chunks = 0
                    result = target(**payload)
                    if inspect.isawaitable(result):
                        result = await result
                    if hasattr(result, "__aiter__"):
                        async for item in result:
                            chunks += 1
                            await job.publish_async("engine.chunk", {"value": item})
                        step["output"] = {"chunks": chunks}
                        return
                    if result is not None:
                        chunks = 1
                        await job.publish_async("engine.chunk", {"value": result})
                    step["output"] = {"chunks": chunks}

    async def shutdown(self) -> None:
        async with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        await asyncio.gather(
            *(worker.stop() for worker in workers),
            return_exceptions=True,
        )

    async def _wait_for_batch(
        self,
        job: EngineJob,
        provider: Any,
        method: str,
        payload: dict[str, Any],
    ) -> EngineBatchTicket:
        batch_size = self._batch_size(provider, method)
        ticket = EngineBatchTicket(
            job=job,
            provider=provider,
            method=method,
            payload=payload,
            batch_size=batch_size,
        )
        async with ai_pipeline_step(
            type="engine_batching",
            name="engine_batching.wait",
            input={"method": ticket.method, "batch_size": batch_size},
        ) as step:
            await job.set_status_async("batching")
            await job.publish_async(
                "engine_batching.wait",
                {
                    "batch_size": batch_size,
                    "batched": False,
                },
            )
            worker = await self._worker(ticket)
            await worker.submit(ticket)
            try:
                dispatch = await ticket.dispatch_future
            except asyncio.CancelledError:
                ticket.cancel()
                raise
            await job.publish_async("engine_batching.dispatch", dict(dispatch))
            step["output"] = dict(dispatch)
            return ticket

    async def _worker(self, ticket: EngineBatchTicket) -> "EngineBatchWorker":
        key = _batch_key(ticket)
        async with self._lock:
            worker = self._workers.get(key)
            if worker is None or worker.done:
                worker = EngineBatchWorker(
                    key=key,
                    batch_size=ticket.batch_size,
                    wait_time=self._wait_time,
                    queue_size=self._queue_size,
                )
                self._workers[key] = worker
            return worker

    @staticmethod
    def _target(provider: Any, method: str) -> Any:
        if not method:
            raise RuntimeError("engine_orchestrator_method_required")
        target = getattr(provider, method, None)
        if target is None:
            raise RuntimeError(f"engine_orchestrator_method_not_found:{method}")
        return target

    @staticmethod
    def _batch_size(provider: Any, method: str) -> int:
        method_batch_sizes = getattr(provider, "_democrai_method_batch_sizes", None)
        if isinstance(method_batch_sizes, dict):
            return _positive_int(method_batch_sizes.get(method, 1))
        return 1


class EngineBatchWorker:
    def __init__(
        self,
        *,
        key: str,
        batch_size: int,
        wait_time: float,
        queue_size: int,
    ) -> None:
        self.key = key
        self.batch_size = max(1, batch_size)
        self.wait_time = max(0.0, wait_time)
        self._queue: asyncio.Queue[EngineBatchTicket | None] = asyncio.Queue(
            maxsize=max(1, queue_size)
        )
        self._pending: list[EngineBatchTicket] = []
        self._task = asyncio.create_task(
            self._run(),
            name=f"engine-batch-worker:{key}",
        )

    @property
    def done(self) -> bool:
        return self._task.done()

    async def submit(self, ticket: EngineBatchTicket) -> None:
        self._pending.append(ticket)
        await self._queue.put(ticket)

    async def stop(self) -> None:
        self._fail_pending(RuntimeError("engine_batching_worker_stopped"))
        await self._queue.put(None)
        await asyncio.gather(self._task, return_exceptions=True)
        self._fail_pending(RuntimeError("engine_batching_worker_stopped"))

    async def _run(self) -> None:
        try:
            while True:
                ticket = await self._queue.get()
                if ticket is None:
                    self._queue.task_done()
                    return
                if ticket.cancelled:
                    ticket.cancel()
                    self._discard_pending(ticket)
                    self._queue.task_done()
                    continue
                batch = [ticket]
                started = time.perf_counter()
                stop_after_batch = False
                while len(batch) < self.batch_size:
                    remaining = self.wait_time - (time.perf_counter() - started)
                    if remaining <= 0:
                        break
                    try:
                        next_ticket = await asyncio.wait_for(
                            self._queue.get(),
                            timeout=remaining,
                        )
                    except asyncio.TimeoutError:
                        break
                    if next_ticket is None:
                        self._queue.task_done()
                        stop_after_batch = True
                        break
                    if next_ticket.cancelled:
                        next_ticket.cancel()
                        self._discard_pending(next_ticket)
                        self._queue.task_done()
                        continue
                    batch.append(next_ticket)
                payload = {
                    "batch_size": self.batch_size,
                    "effective_batch_size": len(batch),
                    "batched": len(batch) > 1,
                }
                for item in batch:
                    self._discard_pending(item)
                    if not item.dispatch_future.done():
                        item.dispatch_future.set_result(payload)
                    self._queue.task_done()
                if stop_after_batch:
                    return
        except BaseException as exc:
            self._fail_pending(exc)
            raise

    def _fail_pending(self, error: BaseException) -> None:
        pending = list(self._pending)
        self._pending = []
        for ticket in pending:
            ticket.fail(error)

    def _discard_pending(self, ticket: EngineBatchTicket) -> None:
        self._pending = [item for item in self._pending if item is not ticket]


def _batch_key(ticket: EngineBatchTicket) -> str:
    instance_id = (
        getattr(ticket.provider, "_democrai_instance_id", "")
        or getattr(ticket.provider, "instance_id", "")
        or id(ticket.provider)
    )
    return f"{instance_id}:{ticket.method}"


def _call_input(ticket: EngineBatchTicket) -> dict[str, Any]:
    return {
        "method": ticket.method,
        "payload_keys": sorted(str(key) for key in ticket.payload.keys()),
    }


def _require_engine_quota(*, job: EngineJob, provider: Any) -> None:
    engine_row_id = to_int_or_zero(getattr(provider, "engine_row_id", None))
    if engine_row_id <= 0:
        return
    from democrai.core.application.ai.engine.quotas import require_engine_quota

    request_context = job.request_context if isinstance(job.request_context, dict) else {}
    if not request_context:
        return
    require_engine_quota(
        engine_registry_id=engine_row_id,
        user_id=to_int_or_zero(request_context.get("user")) or None,
        request_context=request_context,
    )


def _positive_int(value: Any) -> int:
    resolved = int(value)
    return resolved if resolved > 0 else 1
