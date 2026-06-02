from __future__ import annotations

import threading
import time
from typing import Any


class ObservabilityMaintenanceService:
    def __init__(
        self,
        *,
        store: Any,
        logger: Any,
        events_days: int,
        audit_days: int,
        ai_model_usage_days: int,
        export_outbox_days: int,
        trace_archive_queue_days: int,
        cleanup_interval_seconds: int,
        outbox_flush_interval_seconds: int,
        trace_archive_interval_seconds: int = 5,
        trace_archive_batch_size: int = 25,
        trace_archive_lock_timeout_seconds: int = 300,
    ) -> None:
        self.store = store
        self.logger = logger
        self.events_days = events_days
        self.audit_days = audit_days
        self.ai_model_usage_days = ai_model_usage_days
        self.export_outbox_days = export_outbox_days
        self.trace_archive_queue_days = trace_archive_queue_days
        self.cleanup_interval_seconds = cleanup_interval_seconds
        self.outbox_flush_interval_seconds = outbox_flush_interval_seconds
        self.trace_archive_interval_seconds = trace_archive_interval_seconds
        self.trace_archive_batch_size = trace_archive_batch_size
        self.trace_archive_lock_timeout_seconds = trace_archive_lock_timeout_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            name="ObservabilityMaintenance",
            daemon=True,
        )
        self._thread.start()

    def shutdown(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None

    def _run_loop(self) -> None:
        retention_interval = max(1, self.cleanup_interval_seconds)
        outbox_interval = max(1, self.outbox_flush_interval_seconds)
        trace_interval = max(1, self.trace_archive_interval_seconds)
        next_retention_at = 0.0
        next_trace_archive_at = 0.0
        while not self._stop.is_set():
            try:
                self.store.flush_export_outbox(limit=200)
            except Exception as exc:
                if self.logger is not None:
                    self.logger.error(f"[Observability] outbox flush failed: {exc}")

            now = time.monotonic()
            if now >= next_trace_archive_at:
                try:
                    self.store.process_trace_archive_queue(
                        limit=self.trace_archive_batch_size,
                        lock_timeout_seconds=self.trace_archive_lock_timeout_seconds,
                    )
                except Exception as exc:
                    if self.logger is not None:
                        self.logger.error(f"[Observability] trace archive failed: {exc}")
                next_trace_archive_at = now + trace_interval

            if now >= next_retention_at:
                try:
                    self.store.apply_retention(
                        events_days=self.events_days,
                        audit_days=self.audit_days,
                        ai_model_usage_days=self.ai_model_usage_days,
                        export_outbox_days=self.export_outbox_days,
                        trace_archive_queue_days=self.trace_archive_queue_days,
                    )
                except Exception as exc:
                    if self.logger is not None:
                        self.logger.error(f"[Observability] retention cleanup failed: {exc}")
                next_retention_at = now + retention_interval

            self._stop.wait(outbox_interval)
