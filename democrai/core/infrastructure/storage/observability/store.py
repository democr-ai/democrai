from __future__ import annotations

from datetime import timedelta
from typing import Optional

from democrai.core.infrastructure.storage.observability.exporters.base import ObsExporter
from democrai.core.infrastructure.storage.observability.models import AuditEventRecord
from democrai.core.infrastructure.storage.observability.models import AIModelPipelineStepRecord
from democrai.core.infrastructure.storage.observability.models import AIModelRuntimeEventRecord
from democrai.core.infrastructure.storage.observability.models import EventRecord
from democrai.core.infrastructure.storage.observability.models import ExportOutboxRecord
from democrai.core.infrastructure.storage.observability.models import AIModelUsageEventRecord
from democrai.core.infrastructure.storage.observability.providers.base import ObsStorageProvider
from democrai.core.infrastructure.storage.observability.providers.postgres import (
    PostgresObsStorage,
)
from democrai.core.infrastructure.storage.observability.providers.sqlite import SqliteObsStorage
from democrai.core.platform.utils.timezone import utc_now_naive


class ObservabilityStore:
    def __init__(
        self,
        db_url: Optional[str] = None,
        *,
        provider: ObsStorageProvider | None = None,
        exporters: list[ObsExporter] | None = None,
    ):
        if provider is None:
            provider = self._provider_from_url(db_url)
        self.provider = provider
        self.exporters = exporters or []

    @staticmethod
    def _provider_from_url(db_url: Optional[str]) -> ObsStorageProvider:
        if db_url is None or db_url.startswith("sqlite:///"):
            db_path = db_url[len("sqlite:///") :] if db_url else None
            return SqliteObsStorage(db_path)
        return PostgresObsStorage(db_url)

    def record_event(
        self,
        event_name: str,
        category: str,
        correlation_id: str,
        level: str = "INFO",
        user_id: Optional[int] = None,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        payload: Optional[dict] = None,
        duration_ms: Optional[float] = None,
    ) -> EventRecord:
        event = self.provider.record_event(
            event_name=event_name,
            category=category,
            correlation_id=correlation_id,
            level=level,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            payload=payload,
            duration_ms=duration_ms,
        )
        self._dispatch_export_payload("event", event.to_dict(), correlation_id=event.correlation_id)
        return event

    def get_events(
        self,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[EventRecord]:
        return self.provider.get_events(
            user_id=user_id,
            category=category,
            correlation_id=correlation_id,
            limit=limit,
        )

    def get_flow(self, correlation_id: str) -> list[EventRecord]:
        return self.provider.get_flow(correlation_id)

    def get_events_serialized(
        self,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        return [
            event.to_dict()
            for event in self.get_events(
                user_id=user_id,
                category=category,
                correlation_id=correlation_id,
                limit=limit,
            )
        ]

    def get_flow_serialized(self, correlation_id: str) -> list[dict]:
        return [event.to_dict() for event in self.get_flow(correlation_id)]

    def record_audit_event(self, **kwargs) -> AuditEventRecord:
        event = self.provider.record_audit_event(**kwargs)
        self._dispatch_export_payload(
            "audit",
            event.to_dict(),
            correlation_id=kwargs.get("correlation_id"),
        )
        return event

    def get_audit_events(
        self,
        *,
        actor_user_id: Optional[int] = None,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        return self.provider.get_audit_events(
            actor_user_id=actor_user_id,
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            limit=limit,
        )

    def get_audit_events_serialized(self, **kwargs) -> list[dict]:
        return [event.to_dict() for event in self.get_audit_events(**kwargs)]

    def record_ai_model_usage(self, **kwargs) -> AIModelUsageEventRecord:
        event = self.provider.record_ai_model_usage(**kwargs)
        self._dispatch_export_payload(
            "ai_model_usage",
            event.to_dict(),
            correlation_id=kwargs.get("correlation_id"),
        )
        return event

    def record_ai_model_runtime(self, **kwargs) -> AIModelRuntimeEventRecord:
        event = self.provider.record_ai_model_runtime(**kwargs)
        self._dispatch_export_payload(
            "ai_model_runtime",
            event.to_dict(),
            correlation_id=kwargs.get("correlation_id"),
        )
        return event

    def record_ai_model_pipeline_step(self, **kwargs) -> AIModelPipelineStepRecord:
        event = self.provider.record_ai_model_pipeline_step(**kwargs)
        self._dispatch_export_payload(
            "ai_model_pipeline_step",
            event.to_dict(),
            correlation_id=kwargs.get("pipeline_id") or kwargs.get("correlation_id"),
        )
        return event

    def enqueue_trace_archive(self, **kwargs):
        return self.provider.enqueue_trace_archive(**kwargs)

    def get_ai_model_usage_events(
        self,
        *,
        user_id: Optional[int] = None,
        objective: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[AIModelUsageEventRecord]:
        return self.provider.get_ai_model_usage_events(
            user_id=user_id,
            objective=objective,
            model_name=model_name,
            limit=limit,
        )

    def get_ai_model_usage_events_serialized(self, **kwargs) -> list[dict]:
        return [event.to_dict() for event in self.get_ai_model_usage_events(**kwargs)]

    def get_ai_model_usage_events_for_pipeline(
        self,
        *,
        pipeline_id: str,
        limit: int = 500,
    ) -> list[AIModelUsageEventRecord]:
        return self.provider.get_ai_model_usage_events_for_pipeline(
            pipeline_id=pipeline_id,
            limit=limit,
        )

    def sum_ai_model_usage_total_tokens(self, **kwargs) -> int:
        return self.provider.sum_ai_model_usage_total_tokens(**kwargs)

    def run_migrations(self) -> None:
        self.provider.run_migrations()

    def flush_export_outbox(self, *, limit: int = 100) -> dict[str, int]:
        if not self.exporters:
            return {"processed": 0, "exported": 0, "failed": 0}
        rows = self.provider.get_export_outbox_ready(limit=limit)
        exported = 0
        failed = 0
        for row in rows:
            payload = row.to_dict().get("payload", {})
            try:
                for exporter in self.exporters:
                    exporter.export(payload)
                self.provider.mark_export_outbox_exported(row.id)
                exported += 1
            except Exception as exc:
                self.provider.mark_export_outbox_failed(
                    row.id,
                    error=str(exc),
                    retry_at=utc_now_naive() + timedelta(seconds=60),
                )
                failed += 1
        return {"processed": len(rows), "exported": exported, "failed": failed}

    def process_trace_archive_queue(
        self,
        *,
        limit: int = 100,
        lock_timeout_seconds: int = 300,
    ) -> dict[str, int]:
        from democrai.core.application.observability.trace_archive import (
            process_trace_archive_queue,
        )

        return process_trace_archive_queue(
            self.provider,
            limit=limit,
            lock_timeout_seconds=lock_timeout_seconds,
        )

    def apply_retention(
        self,
        *,
        events_days: int | None = None,
        audit_days: int | None = None,
        ai_model_usage_days: int | None = None,
        export_outbox_days: int | None = None,
        trace_archive_queue_days: int | None = None,
    ) -> dict[str, int]:
        now = utc_now_naive()
        return self.provider.cleanup_older_than(
            events_before=(now - timedelta(days=events_days)) if events_days else None,
            audit_events_before=(now - timedelta(days=audit_days)) if audit_days else None,
            ai_model_usage_before=(now - timedelta(days=ai_model_usage_days)) if ai_model_usage_days else None,
            export_outbox_before=(
                now - timedelta(days=export_outbox_days) if export_outbox_days else None
            ),
            trace_archive_queue_before=(
                now - timedelta(days=trace_archive_queue_days) if trace_archive_queue_days else None
            ),
        )

    def _dispatch_export_payload(
        self,
        event_kind: str,
        payload: dict,
        *,
        correlation_id: str | None = None,
    ) -> ExportOutboxRecord | None:
        if not self.exporters:
            return None
        outbox = self.provider.enqueue_export_outbox(
            event_kind=event_kind,
            payload=payload,
            correlation_id=correlation_id,
        )
        try:
            for exporter in self.exporters:
                exporter.export(payload)
            self.provider.mark_export_outbox_exported(outbox.id)
        except Exception as exc:
            self.provider.mark_export_outbox_failed(
                outbox.id,
                error=str(exc),
                retry_at=utc_now_naive() + timedelta(seconds=60),
            )
        return outbox
