from __future__ import annotations

import asyncio
import contextvars
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from democrai.core.application.ai.engine.orchestrator.jobs import EngineJob
from democrai.core.application.ai.engine.orchestrator.jobs import EngineJobRegistry


class EngineSchedulerQueueFull(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineSchedulerConfig:
    max_queue_depth: int = 100
    submit_timeout_seconds: float = 0.0
    worker_count: int = 1
    graceful_shutdown_seconds: float = 30.0


EngineJobExecutor = Callable[[EngineJob], Awaitable[Any]]


@dataclass(frozen=True)
class _QueuedEngineJob:
    job: EngineJob
    context: contextvars.Context


class EngineScheduler:
    def __init__(
        self,
        *,
        registry: EngineJobRegistry,
        executor: EngineJobExecutor,
        config: EngineSchedulerConfig | None = None,
    ) -> None:
        self._registry = registry
        self._executor = executor
        self._config = config or EngineSchedulerConfig()
        self._queue: asyncio.Queue[_QueuedEngineJob] = asyncio.Queue(
            maxsize=max(1, int(self._config.max_queue_depth or 1))
        )
        self._dispatcher: asyncio.Task | None = None
        self._running: set[asyncio.Task] = set()
        self._slots = asyncio.Semaphore(self.max_concurrent_jobs)
        self._accepting = False

    @property
    def accepting(self) -> bool:
        return self._accepting

    @property
    def queued_count(self) -> int:
        return self._queue.qsize()

    def start(self) -> None:
        if self._accepting:
            return
        self._accepting = True
        self._dispatcher = asyncio.create_task(
            self._dispatcher_loop(),
            name="engine-orchestrator-dispatcher",
        )

    @property
    def running_count(self) -> int:
        return len(self._running)

    @property
    def max_concurrent_jobs(self) -> int:
        return max(1, int(self._config.worker_count or 1))

    async def stop(self) -> None:
        self._accepting = False
        try:
            await asyncio.wait_for(
                self._queue.join(),
                timeout=max(0.1, float(self._config.graceful_shutdown_seconds or 0.1)),
            )
        except asyncio.TimeoutError:
            self._cancel_queued_jobs("engine_orchestrator_scheduler_shutdown")
            for task in list(self._running):
                task.cancel()
        if self._dispatcher is not None:
            self._dispatcher.cancel()
            await asyncio.gather(self._dispatcher, return_exceptions=True)
            self._dispatcher = None
        if self._running:
            await asyncio.gather(*list(self._running), return_exceptions=True)
        self._running.clear()

    async def submit(self, job: EngineJob) -> EngineJob:
        if not self._accepting:
            job.fail("engine_orchestrator_scheduler_not_accepting")
            raise RuntimeError("engine_orchestrator_scheduler_not_accepting")
        try:
            timeout = float(self._config.submit_timeout_seconds or 0.0)
            if timeout > 0:
                await asyncio.wait_for(
                    self._queue.put(
                        _QueuedEngineJob(job=job, context=contextvars.copy_context())
                    ),
                    timeout=timeout,
                )
            else:
                self._queue.put_nowait(
                    _QueuedEngineJob(job=job, context=contextvars.copy_context())
                )
        except (asyncio.QueueFull, asyncio.TimeoutError) as exc:
            job.fail("engine_orchestrator_queue_full")
            raise EngineSchedulerQueueFull("engine_orchestrator_queue_full") from exc
        return job

    async def _dispatcher_loop(self) -> None:
        while True:
            await self._slots.acquire()
            try:
                queued = await self._queue.get()
            except BaseException:
                self._slots.release()
                raise
            task = asyncio.create_task(
                self._run_queued_job(queued),
                context=queued.context,
                name=f"engine-orchestrator-job:{queued.job.request_id}",
            )
            self._running.add(task)

    async def _run_queued_job(self, queued: _QueuedEngineJob) -> None:
        job = queued.job
        task: asyncio.Task | None = None
        try:
            if job.done:
                return
            await job.set_status_async("resolving")
            task = asyncio.current_task()
            job.attach_task(task)
            result = await self._executor(job)
            job.complete(result)
            self._registry.mark_terminal(job)
        except asyncio.CancelledError:
            if job.done:
                self._registry.mark_terminal(job)
                return
            job.cancel("engine_orchestrator_worker_cancelled")
            self._registry.mark_terminal(job)
            raise
        except Exception as exc:
            retriable = job.status not in {
                "invoking",
                "streaming",
            }
            job.fail(exc, retriable=retriable)
            self._registry.mark_terminal(job)
        finally:
            if task is not None:
                job.detach_task(task)
            current_task = asyncio.current_task()
            if current_task is not None:
                self._running.discard(current_task)
            self._slots.release()
            self._queue.task_done()

    def _cancel_queued_jobs(self, reason: str) -> None:
        while True:
            try:
                queued = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                queued.job.cancel(reason)
            finally:
                self._queue.task_done()
