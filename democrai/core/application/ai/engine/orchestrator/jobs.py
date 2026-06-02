from __future__ import annotations

import asyncio
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from democrai.core.platform.utils.timezone import utc_now_naive


logger = logging.getLogger(__name__)


ENGINE_JOB_STATUSES = {
    "queued",
    "resolving",
    "waiting_hitl",
    "unloading",
    "loading",
    "batching",
    "invoking",
    "streaming",
    "done",
    "error",
    "cancelled",
}

ENGINE_JOB_TERMINAL_STATUSES = {"done", "error", "cancelled"}


@dataclass(frozen=True)
class EngineJobEvent:
    request_id: str
    pipeline_id: str
    kind: str
    status: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: Any = field(default_factory=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "pipeline_id": self.pipeline_id,
            "kind": self.kind,
            "status": self.status,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class EngineJob:
    request_id: str
    pipeline_id: str
    selector_type: str
    method: str
    payload: dict[str, Any]
    request_context: dict[str, Any]
    security_context: dict[str, Any]
    response_mode: str = "unary"
    model_registry_id: int | None = None
    objective: str | None = None
    capabilities: tuple[str, ...] = ()
    prefer_local: bool | None = None
    confirm_swap: bool = False
    status: str = "queued"
    created_at: Any = field(default_factory=utc_now_naive)
    started_at: Any | None = None
    finished_at: Any | None = None
    error: str | None = None
    retriable: bool | None = None
    result: Any = None
    max_queue_size: int = 256
    _loop: asyncio.AbstractEventLoop = field(repr=False, compare=False, default=None)
    _events: asyncio.Queue[EngineJobEvent] = field(repr=False, compare=False, default=None)
    _future: asyncio.Future = field(repr=False, compare=False, default=None)
    _tasks: set[asyncio.Task] = field(repr=False, compare=False, default_factory=set)
    _lock: threading.RLock = field(repr=False, compare=False, default_factory=threading.RLock)

    def __post_init__(self) -> None:
        if self.status not in ENGINE_JOB_STATUSES:
            raise ValueError(f"engine_job_status_unknown:{self.status}")
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._events is None:
            self._events = asyncio.Queue(maxsize=max(1, int(self.max_queue_size or 1)))
        if self._future is None:
            self._future = self._loop.create_future()
        self.publish("job.created")

    @property
    def done(self) -> bool:
        with self._lock:
            return self.status in ENGINE_JOB_TERMINAL_STATUSES

    @property
    def result_future(self) -> asyncio.Future:
        return self._future

    def attach_task(self, task: asyncio.Task) -> None:
        with self._lock:
            if self.status in ENGINE_JOB_TERMINAL_STATUSES:
                task.cancel()
                return
            self._tasks.add(task)

    def detach_task(self, task: asyncio.Task) -> None:
        with self._lock:
            self._tasks.discard(task)

    async def next_event(self) -> EngineJobEvent:
        return await self._events.get()

    def next_event_nowait(self) -> EngineJobEvent | None:
        try:
            return self._events.get_nowait()
        except asyncio.QueueEmpty:
            return None

    def publish(self, kind: str, payload: dict[str, Any] | None = None) -> None:
        event = EngineJobEvent(
            request_id=self.request_id,
            pipeline_id=self.pipeline_id,
            kind=kind,
            status=self.status,
            payload=payload or {},
        )
        self._loop.call_soon_threadsafe(_put_event_nowait, self._events, event)

    async def publish_async(
        self,
        kind: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = EngineJobEvent(
            request_id=self.request_id,
            pipeline_id=self.pipeline_id,
            kind=kind,
            status=self.status,
            payload=payload or {},
        )
        await self._events.put(event)

    def set_status(
        self,
        status: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if status not in ENGINE_JOB_STATUSES:
            raise ValueError(f"engine_job_status_unknown:{status}")
        with self._lock:
            if self.status in ENGINE_JOB_TERMINAL_STATUSES:
                raise RuntimeError(f"engine_job_already_finished:{self.status}")
            self.status = status
            if self.started_at is None and status != "queued":
                self.started_at = utc_now_naive()
        self.publish(f"job.{status}", payload)

    async def set_status_async(
        self,
        status: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if status not in ENGINE_JOB_STATUSES:
            raise ValueError(f"engine_job_status_unknown:{status}")
        with self._lock:
            if self.status in ENGINE_JOB_TERMINAL_STATUSES:
                raise RuntimeError(f"engine_job_already_finished:{self.status}")
            self.status = status
            if self.started_at is None and status != "queued":
                self.started_at = utc_now_naive()
        await self.publish_async(f"job.{status}", payload)

    def complete(self, result: Any = None) -> None:
        with self._lock:
            if self.status in ENGINE_JOB_TERMINAL_STATUSES:
                return
            self.status = "done"
            self.result = result
            self.finished_at = utc_now_naive()
        self.publish("job.done")
        self._loop.call_soon_threadsafe(_set_future_result, self._future, result)

    def fail(self, error: BaseException | str, *, retriable: bool | None = None) -> None:
        message = str(error)
        with self._lock:
            if self.status in ENGINE_JOB_TERMINAL_STATUSES:
                return
            self.status = "error"
            self.error = message
            self.retriable = retriable
            self.finished_at = utc_now_naive()
        self.publish("job.error", {"error": message, "retriable": retriable})
        self._loop.call_soon_threadsafe(
            _set_future_exception,
            self._future,
            RuntimeError(message),
        )

    def cancel(self, reason: str = "engine_job_cancelled") -> bool:
        with self._lock:
            if self.status in ENGINE_JOB_TERMINAL_STATUSES:
                return False
            self.status = "cancelled"
            self.error = str(reason or "engine_job_cancelled")
            self.finished_at = utc_now_naive()
            tasks = list(self._tasks)
        self.publish("job.cancelled", {"reason": self.error})
        for task in tasks:
            task.cancel()
        self._loop.call_soon_threadsafe(_cancel_future, self._future)
        return True

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "request_id": self.request_id,
                "pipeline_id": self.pipeline_id,
                "selector_type": self.selector_type,
                "model_registry_id": self.model_registry_id,
                "objective": self.objective,
                "capabilities": list(self.capabilities),
                "prefer_local": self.prefer_local,
                "confirm_swap": self.confirm_swap,
                "method": self.method,
                "response_mode": self.response_mode,
                "status": self.status,
                "created_at": _time_value(self.created_at),
                "started_at": _time_value(self.started_at),
                "finished_at": _time_value(self.finished_at),
                "error": self.error,
                "retriable": self.retriable,
            }


class EngineJobRegistry:
    def __init__(self, *, terminal_ttl_seconds: float = 300.0) -> None:
        self._jobs: dict[str, EngineJob] = {}
        self._terminal_since: dict[str, float] = {}
        self._terminal_ttl_seconds = max(0.0, terminal_ttl_seconds)
        self._lock = threading.RLock()

    def create_job(
        self,
        *,
        request_id: str | None = None,
        pipeline_id: str | None = None,
        selector_type: str,
        method: str,
        response_mode: str = "unary",
        payload: dict[str, Any] | None = None,
        request_context: dict[str, Any] | None = None,
        security_context: dict[str, Any] | None = None,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        max_queue_size: int = 256,
    ) -> EngineJob:
        job, _created = self.get_or_create_job(
            request_id=request_id,
            pipeline_id=pipeline_id,
            selector_type=selector_type,
            method=method,
            response_mode=response_mode,
            payload=payload,
            request_context=request_context,
            security_context=security_context,
            model_registry_id=model_registry_id,
            objective=objective,
            capabilities=capabilities,
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
            max_queue_size=max_queue_size,
        )
        return job

    def get_or_create_job(
        self,
        *,
        request_id: str | None = None,
        pipeline_id: str | None = None,
        selector_type: str,
        method: str,
        response_mode: str = "unary",
        payload: dict[str, Any] | None = None,
        request_context: dict[str, Any] | None = None,
        security_context: dict[str, Any] | None = None,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capabilities: list[str] | tuple[str, ...] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        max_queue_size: int = 256,
    ) -> tuple[EngineJob, bool]:
        resolved_request_id = uuid.uuid4().hex if request_id is None else request_id
        if not resolved_request_id:
            raise ValueError("engine_job_request_id_required")
        resolved_pipeline_id = uuid.uuid4().hex if pipeline_id is None else pipeline_id
        if not resolved_pipeline_id:
            raise ValueError("engine_job_pipeline_id_required")
        if not selector_type:
            raise ValueError("engine_job_selector_type_required")
        if not method:
            raise ValueError("engine_job_method_required")
        with self._lock:
            self._prune_expired_locked()
            existing = self._jobs.get(resolved_request_id)
            if existing is not None:
                return existing, False
        job = EngineJob(
            request_id=resolved_request_id,
            pipeline_id=resolved_pipeline_id,
            selector_type=selector_type,
            method=method,
            response_mode=response_mode or "unary",
            payload=payload or {},
            request_context=request_context or {},
            security_context=security_context or {},
            model_registry_id=model_registry_id,
            objective=objective or None,
            capabilities=tuple(capabilities or ()),
            prefer_local=prefer_local,
            confirm_swap=confirm_swap,
            max_queue_size=max_queue_size,
        )
        with self._lock:
            self._jobs[resolved_request_id] = job
        return job, True

    def get(self, request_id: str) -> EngineJob | None:
        with self._lock:
            return self._jobs.get(request_id)

    def remove(self, request_id: str) -> EngineJob | None:
        with self._lock:
            return self._jobs.pop(request_id, None)

    def cancel(self, request_id: str, reason: str = "engine_job_cancelled") -> bool:
        job = self.get(request_id)
        if job is None:
            return False
        cancelled = job.cancel(reason)
        if cancelled:
            self._mark_terminal(job)
        return cancelled

    def snapshots(self, *, include_terminal: bool = False) -> list[dict[str, Any]]:
        self.prune_expired()
        with self._lock:
            jobs = [
                job
                for job in self._jobs.values()
                if include_terminal or not job.done
            ]
        return [job.snapshot() for job in jobs]

    def mark_terminal(self, job: EngineJob) -> None:
        self._mark_terminal(job)

    def prune_expired(self) -> None:
        with self._lock:
            self._prune_expired_locked()

    def _mark_terminal(self, job: EngineJob) -> None:
        if not job.done:
            return
        with self._lock:
            self._terminal_since[job.request_id] = time.monotonic()

    def _prune_expired_locked(self) -> None:
        if self._terminal_ttl_seconds <= 0:
            expired = list(self._terminal_since.keys())
        else:
            now = time.monotonic()
            expired = [
                request_id
                for request_id, terminal_since in self._terminal_since.items()
                if now - terminal_since >= self._terminal_ttl_seconds
            ]
        for request_id in expired:
            self._terminal_since.pop(request_id, None)
            self._jobs.pop(request_id, None)


def _set_future_result(future: asyncio.Future, result: Any) -> None:
    if not future.done():
        future.set_result(result)


def _set_future_exception(future: asyncio.Future, exc: BaseException) -> None:
    if not future.done():
        future.set_exception(exc)


def _cancel_future(future: asyncio.Future) -> None:
    if not future.done():
        future.cancel()


def _put_event_nowait(
    queue: asyncio.Queue[EngineJobEvent],
    event: EngineJobEvent,
) -> None:
    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        logger.warning(
            "engine_job_event_queue_full request_id=%s kind=%s status=%s",
            event.request_id,
            event.kind,
            event.status,
        )


def _time_value(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
