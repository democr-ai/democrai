"""Background runtime responsible for draining the knowledge outbox.

The runtime is intentionally small: it polls the outbox, leases jobs, dispatches
them to the service, and records operational errors. All projection semantics
remain in the service layer so the runtime can stay transport-agnostic.
"""

from __future__ import annotations

import asyncio
import threading
from uuid import uuid4

from democrai.core.application.knowledge.ingestion_queue_processor import (
    KnowledgeIngestionQueueProcessor,
)
from democrai.core.runtime.foundation.app import app_ctx


class KnowledgeRuntime:
    """Run vector and KG projection jobs in the background."""
    def __init__(
        self,
        service,
        *,
        poll_interval_seconds: float = 1.0,
        batch_size: int = 16,
        lease_seconds: int = 30,
        max_attempts: int = 8,
    ) -> None:
        self.service = service
        self.poll_interval_seconds = max(0.1, poll_interval_seconds)
        self.batch_size = max(1, batch_size)
        self.lease_seconds = max(1, lease_seconds)
        self.max_attempts = max(1, max_attempts)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._running = False
        self._owner = f"knowledge-runtime:{uuid4()}"
        self._ingestion_processor = KnowledgeIngestionQueueProcessor(
            service=service,
            owner=f"{self._owner}:ingestion",
            max_attempts=self.max_attempts,
            lease_seconds=self.lease_seconds,
        )

    def start(self) -> None:
        """Start the polling coroutine on a dedicated runtime loop."""
        if self._running:
            return
        self._running = True
        self._ready.clear()
        self._thread = threading.Thread(
            target=self._run_thread,
            name="knowledge-runtime",
            daemon=True,
        )
        self._thread.start()
        if not self._ready.wait(timeout=5):
            self._running = False
            raise RuntimeError("knowledge_runtime_thread_start_timeout")

    def stop(self) -> None:
        """Stop the runtime and cancel the active polling task if present."""
        self._running = False
        loop = self._loop
        task = self._task
        if loop is not None and loop.is_running() and task is not None:
            loop.call_soon_threadsafe(task.cancel)
        if self._is_running_on_runtime_loop():
            return
        self._join_thread()

    def _run_thread(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        self._task = loop.create_task(self._runner(), name="knowledge-runtime-runner")
        self._ready.set()
        try:
            loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            pass
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            self._task = None
            self._loop = None

    def _join_thread(self) -> None:
        thread = self._thread
        self._thread = None
        if thread is None or thread is threading.current_thread():
            return
        thread.join(timeout=5)
        if thread.is_alive():
            app_ctx().logger.error(
                "[Knowledge] Background projection runtime thread stop timed out."
            )

    def _is_running_on_runtime_loop(self) -> bool:
        try:
            return asyncio.get_running_loop() is self._loop
        except RuntimeError:
            return False

    async def _runner(self) -> None:
        """Continuously process outbox jobs until the runtime is stopped."""
        logger = app_ctx().logger
        if logger is not None:
            logger.info("[Knowledge] Background projection runtime started.")
        while self._running:
            try:
                ingestion_stats = self._ingestion_processor.process_batch(
                    batch_size=self.batch_size
                )
                processed = await self.service.process_outbox_once(
                    batch_size=self.batch_size,
                    lease_owner=self._owner,
                    lease_seconds=self.lease_seconds,
                    max_attempts=self.max_attempts,
                )
                if processed == 0 and ingestion_stats.claimed == 0:
                    await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if logger is not None:
                    logger.error(f"[Knowledge] Background projection runtime error: {exc}")
                await asyncio.sleep(self.poll_interval_seconds)
