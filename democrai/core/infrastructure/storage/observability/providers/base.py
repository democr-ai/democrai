from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

from democrai.core.infrastructure.storage.observability.models import AuditEventRecord
from democrai.core.infrastructure.storage.observability.models import AIModelPipelineStepRecord
from democrai.core.infrastructure.storage.observability.models import AIModelRuntimeEventRecord
from democrai.core.infrastructure.storage.observability.models import EventRecord
from democrai.core.infrastructure.storage.observability.models import ExportOutboxRecord
from democrai.core.infrastructure.storage.observability.models import TraceArchiveQueueRecord
from democrai.core.infrastructure.storage.observability.models import AIModelUsageEventRecord


class ObsStorageProvider(ABC):
    """Backend contract for observability event storage."""

    @abstractmethod
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
        """Persists an event and returns the normalized stored record."""

    @abstractmethod
    def get_events(
        self,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[EventRecord]:
        """Returns events ordered from newest to oldest."""

    @abstractmethod
    def get_flow(self, correlation_id: str) -> list[EventRecord]:
        """Returns events for a flow ordered from oldest to newest."""

    @abstractmethod
    def record_audit_event(
        self,
        *,
        event_type: str,
        actor_user_id: Optional[int] = None,
        actor_role: Optional[str] = None,
        organization_id: Optional[int] = None,
        session_id: Optional[str] = None,
        node_id: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        channel: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        operation: Optional[str] = None,
        status: Optional[str] = None,
        before: Optional[dict] = None,
        after: Optional[dict] = None,
        metadata: Optional[dict] = None,
    ) -> AuditEventRecord:
        """Persists a structured audit event."""

    @abstractmethod
    def get_audit_events(
        self,
        *,
        actor_user_id: Optional[int] = None,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        """Returns audit events ordered from newest to oldest."""

    @abstractmethod
    def record_ai_model_usage(
        self,
        *,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        session_id: Optional[str] = None,
        node_id: Optional[str] = None,
        request_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        channel: Optional[str] = None,
        objective: Optional[str] = None,
        provider: Optional[str] = None,
        engine: Optional[str] = None,
        model_name: Optional[str] = None,
        deployment_mode: Optional[str] = None,
        request_kind: Optional[str] = None,
        agent_id: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        duration_ms: Optional[float] = None,
        tokens_per_second: Optional[float] = None,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> AIModelUsageEventRecord:
        """Persists a structured AI model usage event."""

    @abstractmethod
    def record_ai_model_runtime(
        self,
        **kwargs,
    ) -> AIModelRuntimeEventRecord:
        """Persists an AI model runtime event."""

    @abstractmethod
    def record_ai_model_pipeline_step(
        self,
        **kwargs,
    ) -> AIModelPipelineStepRecord:
        """Persists an AI model pipeline step."""

    @abstractmethod
    def get_ai_model_usage_events(
        self,
        *,
        user_id: Optional[int] = None,
        objective: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[AIModelUsageEventRecord]:
        """Returns AI model usage events ordered from newest to oldest."""

    @abstractmethod
    def get_ai_model_usage_events_for_pipeline(
        self,
        *,
        pipeline_id: str,
        limit: int = 500,
    ) -> list[AIModelUsageEventRecord]:
        """Returns AI model usage events for one pipeline ordered oldest first."""

    @abstractmethod
    def run_migrations(self) -> None:
        """Creates or updates backend storage structures."""

    @abstractmethod
    def enqueue_export_outbox(
        self,
        *,
        event_kind: str,
        payload: dict,
        correlation_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
    ) -> ExportOutboxRecord:
        """Persists an export payload for reliable distributed delivery."""

    @abstractmethod
    def get_export_outbox_ready(
        self,
        *,
        limit: int = 100,
    ) -> list[ExportOutboxRecord]:
        """Returns pending/failed export rows eligible for retry."""

    @abstractmethod
    def mark_export_outbox_exported(self, outbox_id: str) -> None:
        """Marks an outbox row as exported."""

    @abstractmethod
    def mark_export_outbox_failed(
        self,
        outbox_id: str,
        *,
        error: str,
        retry_at: Optional[datetime] = None,
    ) -> None:
        """Marks an outbox row as failed with retry metadata."""

    @abstractmethod
    def enqueue_trace_archive(
        self,
        *,
        pipeline_step_db_id: Optional[int],
        pipeline_id: str,
        request_id: Optional[str],
        step_id: str,
        payload_kind: str,
        payload: dict,
        payload_hash: Optional[str] = None,
    ) -> TraceArchiveQueueRecord:
        """Persists a complete trace payload for asynchronous media archiving."""

    @abstractmethod
    def get_trace_archive_ready(
        self,
        *,
        limit: int = 100,
        lock_timeout_seconds: int = 300,
    ) -> list[TraceArchiveQueueRecord]:
        """Returns trace archive rows ready for processing."""

    @abstractmethod
    def mark_trace_archive_processing(self, archive_id: str, *, locked_by: str) -> None:
        """Marks a trace archive row as processing."""

    @abstractmethod
    def mark_trace_archive_archived(
        self,
        archive_id: str,
        *,
        archived_media_path: str,
    ) -> None:
        """Marks a trace archive row as archived."""

    @abstractmethod
    def mark_trace_archive_failed(
        self,
        archive_id: str,
        *,
        error: str,
        retry_at: Optional[datetime] = None,
    ) -> None:
        """Marks a trace archive row as failed with retry metadata."""

    @abstractmethod
    def update_ai_model_pipeline_step_archive(
        self,
        *,
        step_db_id: Optional[int],
        step_id: str,
        archive_status: str,
        archive_media_path: Optional[str],
        archive_error: Optional[str],
    ) -> None:
        """Updates archive metadata on a pipeline step row."""

    @abstractmethod
    def cleanup_older_than(
        self,
        *,
        events_before: Optional[datetime] = None,
        audit_events_before: Optional[datetime] = None,
        ai_model_usage_before: Optional[datetime] = None,
        export_outbox_before: Optional[datetime] = None,
        trace_archive_queue_before: Optional[datetime] = None,
    ) -> dict[str, int]:
        """Purges old records and returns deleted rows count by stream."""
