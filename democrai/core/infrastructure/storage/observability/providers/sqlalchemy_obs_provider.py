from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import func, or_

from democrai.core.infrastructure.storage.observability.models import Base
from democrai.core.infrastructure.storage.observability.models import AuditEvent
from democrai.core.infrastructure.storage.observability.models import AuditEventRecord
from democrai.core.infrastructure.storage.observability.models import AIModelPipelineStep
from democrai.core.infrastructure.storage.observability.models import AIModelPipelineStepRecord
from democrai.core.infrastructure.storage.observability.models import AIModelRuntimeEvent
from democrai.core.infrastructure.storage.observability.models import AIModelRuntimeEventRecord
from democrai.core.infrastructure.storage.observability.models import Event
from democrai.core.infrastructure.storage.observability.models import EventRecord
from democrai.core.infrastructure.storage.observability.models import ExportOutboxEvent
from democrai.core.infrastructure.storage.observability.models import ExportOutboxRecord
from democrai.core.infrastructure.storage.observability.models import TraceArchiveQueueEvent
from democrai.core.infrastructure.storage.observability.models import TraceArchiveQueueRecord
from democrai.core.infrastructure.storage.observability.models import AIModelUsageEvent
from democrai.core.infrastructure.storage.observability.models import AIModelUsageEventRecord
from democrai.core.platform.utils.timezone import utc_now_naive


class SQLAlchemyObsProviderMixin:
    """Shared SQLAlchemy implementation for observability event storage."""

    def _session(self):  # pragma: no cover - implemented by concrete classes
        raise NotImplementedError

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
        with self._session() as session:
            event = Event(
                event_name=event_name,
                category=category,
                correlation_id=correlation_id,
                level=level,
                user_id=user_id,
                session_id=session_id,
                agent_id=agent_id,
                payload=json.dumps(payload or {}),
                duration_ms=duration_ms,
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.to_record()

    def get_events(
        self,
        user_id: Optional[int] = None,
        category: Optional[str] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[EventRecord]:
        with self._session() as session:
            query = session.query(Event)
            if user_id is not None:
                query = query.filter(Event.user_id == user_id)
            if category:
                query = query.filter(Event.category == category)
            if correlation_id:
                query = query.filter(Event.correlation_id == correlation_id)
            return [event.to_record() for event in query.order_by(Event.timestamp.desc()).limit(limit).all()]

    def get_flow(self, correlation_id: str) -> list[EventRecord]:
        with self._session() as session:
            query = session.query(Event).filter(Event.correlation_id == correlation_id).order_by(Event.timestamp.asc())
            return [event.to_record() for event in query.all()]

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
        with self._session() as session:
            event = AuditEvent(
                event_type=event_type,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                organization_id=organization_id,
                session_id=session_id,
                node_id=node_id,
                request_id=request_id,
                correlation_id=correlation_id,
                client_ip=client_ip,
                channel=channel,
                entity_type=entity_type,
                entity_id=entity_id,
                operation=operation,
                status=status,
                before_json=json.dumps(before or {}),
                after_json=json.dumps(after or {}),
                metadata_json=json.dumps(metadata or {}),
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.to_record()

    def get_audit_events(
        self,
        *,
        actor_user_id: Optional[int] = None,
        event_type: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditEventRecord]:
        with self._session() as session:
            query = session.query(AuditEvent)
            if actor_user_id is not None:
                query = query.filter(AuditEvent.actor_user_id == actor_user_id)
            if event_type:
                query = query.filter(AuditEvent.event_type == event_type)
            if entity_type:
                query = query.filter(AuditEvent.entity_type == entity_type)
            if entity_id:
                query = query.filter(AuditEvent.entity_id == entity_id)
            return [event.to_record() for event in query.order_by(AuditEvent.timestamp.desc()).limit(limit).all()]

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
        engine_row_id: Optional[int] = None,
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
        with self._session() as session:
            event = AIModelUsageEvent(
                user_id=user_id,
                organization_id=organization_id,
                session_id=session_id,
                node_id=node_id,
                request_id=request_id,
                correlation_id=correlation_id,
                client_ip=client_ip,
                channel=channel,
                objective=objective,
                provider=provider,
                engine=engine,
                engine_row_id=engine_row_id,
                model_name=model_name,
                deployment_mode=deployment_mode,
                request_kind=request_kind,
                agent_id=agent_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                duration_ms=duration_ms,
                tokens_per_second=tokens_per_second,
                success=bool(success),
                error=error,
                metadata_json=json.dumps(metadata or {}),
            )
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.to_record()

    def sum_ai_model_usage_total_tokens(
        self,
        *,
        engine_row_id: int,
        started_at: datetime,
        ended_at: datetime,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> int:
        return self.aggregate_ai_model_usage(
            metric_type="total_tokens",
            engine_row_id=engine_row_id,
            started_at=started_at,
            ended_at=ended_at,
            user_id=user_id,
            organization_id=organization_id,
            session_id=session_id,
        )

    def aggregate_ai_model_usage(
        self,
        *,
        metric_type: str,
        engine_row_id: int,
        started_at: datetime,
        ended_at: datetime,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> int:
        with self._session() as session:
            metric = str(metric_type)
            if metric == "total_tokens":
                query = session.query(
                    func.coalesce(func.sum(func.coalesce(AIModelUsageEvent.total_tokens, 0)), 0)
                )
            elif metric == "requests":
                query = session.query(func.count(AIModelUsageEvent.id))
            else:
                raise ValueError(f"ai_model_usage_metric_unsupported:{metric}")
            query = query.filter(
                AIModelUsageEvent.engine_row_id == int(engine_row_id),
                AIModelUsageEvent.success == True,  # noqa: E712
                AIModelUsageEvent.timestamp >= started_at,
                AIModelUsageEvent.timestamp < ended_at,
            )
            if user_id is not None:
                query = query.filter(AIModelUsageEvent.user_id == int(user_id))
            if organization_id is not None:
                query = query.filter(
                    AIModelUsageEvent.organization_id == int(organization_id)
                )
            if session_id is not None:
                query = query.filter(AIModelUsageEvent.session_id == str(session_id))
            return int(query.scalar() or 0)

    def get_ai_model_usage_events(
        self,
        *,
        user_id: Optional[int] = None,
        objective: Optional[str] = None,
        model_name: Optional[str] = None,
        limit: int = 100,
    ) -> list[AIModelUsageEventRecord]:
        with self._session() as session:
            query = session.query(AIModelUsageEvent)
            if user_id is not None:
                query = query.filter(AIModelUsageEvent.user_id == user_id)
            if objective:
                query = query.filter(AIModelUsageEvent.objective == objective)
            if model_name:
                query = query.filter(AIModelUsageEvent.model_name == model_name)
            return [event.to_record() for event in query.order_by(AIModelUsageEvent.timestamp.desc()).limit(limit).all()]

    def get_ai_model_usage_events_for_pipeline(
        self,
        *,
        pipeline_id: str,
        limit: int = 500,
    ) -> list[AIModelUsageEventRecord]:
        resolved_pipeline_id = pipeline_id.strip()
        if not resolved_pipeline_id:
            return []
        with self._session() as session:
            rows = (
                session.query(AIModelUsageEvent)
                .filter(AIModelUsageEvent.metadata_json.like(f'%"{resolved_pipeline_id}"%'))
                .order_by(AIModelUsageEvent.timestamp.asc(), AIModelUsageEvent.id.asc())
                .limit(max(1, limit))
                .all()
            )
            records: list[AIModelUsageEventRecord] = []
            for row in rows:
                metadata = json.loads(row.metadata_json or "{}")
                if metadata.get("pipeline_id") == resolved_pipeline_id:
                    records.append(row.to_record())
            return records

    def record_ai_model_runtime(self, **kwargs) -> AIModelRuntimeEventRecord:
        payload = dict(kwargs)
        payload["success"] = bool(payload.get("success", True))
        payload["metadata_json"] = json.dumps(payload.pop("metadata", None) or {})
        with self._session() as session:
            event = AIModelRuntimeEvent(**payload)
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.to_record()

    def record_ai_model_pipeline_step(self, **kwargs) -> AIModelPipelineStepRecord:
        payload = dict(kwargs)
        payload["input_json"] = json.dumps(payload.pop("input", None) or {})
        payload["output_json"] = json.dumps(payload.pop("output", None) or {})
        payload["stats_json"] = json.dumps(payload.pop("stats", None) or {})
        payload["metadata_json"] = json.dumps(payload.pop("metadata", None) or {})
        with self._session() as session:
            event = AIModelPipelineStep(**payload)
            session.add(event)
            session.commit()
            session.refresh(event)
            return event.to_record()

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
        with self._session() as session:
            row = TraceArchiveQueueEvent(
                id=str(uuid4()),
                pipeline_step_db_id=pipeline_step_db_id,
                pipeline_id=pipeline_id,
                request_id=request_id,
                step_id=step_id,
                payload_kind=payload_kind,
                status="pending",
                attempts=0,
                next_attempt_at=utc_now_naive(),
                payload_hash=payload_hash,
                payload_json=json.dumps(payload or {}),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_record()

    def get_trace_archive_ready(
        self,
        *,
        limit: int = 100,
        lock_timeout_seconds: int = 300,
    ) -> list[TraceArchiveQueueRecord]:
        now = utc_now_naive()
        stale_processing_before = now - timedelta(seconds=max(1, lock_timeout_seconds))
        with self._session() as session:
            rows = (
                session.query(TraceArchiveQueueEvent)
                .filter(
                    or_(
                        TraceArchiveQueueEvent.status == "pending",
                        TraceArchiveQueueEvent.status == "failed",
                        (
                            (TraceArchiveQueueEvent.status == "processing")
                            & (TraceArchiveQueueEvent.locked_at <= stale_processing_before)
                        ),
                    ),
                    or_(
                        TraceArchiveQueueEvent.next_attempt_at.is_(None),
                        TraceArchiveQueueEvent.next_attempt_at <= now,
                    ),
                )
                .order_by(TraceArchiveQueueEvent.timestamp.asc())
                .limit(max(1, limit))
                .all()
            )
            return [row.to_record() for row in rows]

    def mark_trace_archive_processing(self, archive_id: str, *, locked_by: str) -> None:
        with self._session() as session:
            row = session.get(TraceArchiveQueueEvent, archive_id)
            if row is None:
                return
            row.status = "processing"
            row.locked_by = locked_by
            row.locked_at = utc_now_naive()
            row.last_error = None
            session.commit()

    def mark_trace_archive_archived(
        self,
        archive_id: str,
        *,
        archived_media_path: str,
    ) -> None:
        with self._session() as session:
            row = session.get(TraceArchiveQueueEvent, archive_id)
            if row is None:
                return
            row.status = "archived"
            row.archived_media_path = archived_media_path
            row.next_attempt_at = None
            row.last_error = None
            row.payload_json = "{}"
            session.commit()

    def mark_trace_archive_failed(
        self,
        archive_id: str,
        *,
        error: str,
        retry_at: Optional[datetime] = None,
    ) -> None:
        with self._session() as session:
            row = session.get(TraceArchiveQueueEvent, archive_id)
            if row is None:
                return
            row.status = "failed"
            row.attempts = row.attempts + 1
            row.next_attempt_at = retry_at or (utc_now_naive() + timedelta(seconds=60))
            row.last_error = error[:4000]
            session.commit()

    def update_ai_model_pipeline_step_archive(
        self,
        *,
        step_db_id: Optional[int],
        step_id: str,
        archive_status: str,
        archive_media_path: Optional[str],
        archive_error: Optional[str],
    ) -> None:
        with self._session() as session:
            row = None
            if step_db_id is not None:
                row = session.get(AIModelPipelineStep, step_db_id)
            if row is None:
                row = (
                    session.query(AIModelPipelineStep)
                    .filter(AIModelPipelineStep.step_id == step_id)
                    .order_by(AIModelPipelineStep.timestamp.desc())
                    .first()
                )
            if row is None:
                return
            row.archive_status = archive_status
            row.archive_media_path = archive_media_path
            row.archive_error = archive_error
            session.commit()

    def run_migrations(self) -> None:
        Base.metadata.create_all(bind=self.engine)

    def enqueue_export_outbox(
        self,
        *,
        event_kind: str,
        payload: dict,
        correlation_id: Optional[str] = None,
        source_node_id: Optional[str] = None,
        dedupe_key: Optional[str] = None,
    ) -> ExportOutboxRecord:
        with self._session() as session:
            if dedupe_key:
                existing = session.query(ExportOutboxEvent).filter(ExportOutboxEvent.dedupe_key == dedupe_key).one_or_none()
                if existing is not None:
                    return existing.to_record()
            row = ExportOutboxEvent(
                id=str(uuid4()),
                event_kind=event_kind,
                correlation_id=correlation_id,
                source_node_id=source_node_id,
                dedupe_key=dedupe_key,
                status="pending",
                attempts=0,
                next_attempt_at=utc_now_naive(),
                payload_json=json.dumps(payload or {}),
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return row.to_record()

    def get_export_outbox_ready(self, *, limit: int = 100) -> list[ExportOutboxRecord]:
        now = utc_now_naive()
        with self._session() as session:
            rows = (
                session.query(ExportOutboxEvent)
                .filter(
                    ExportOutboxEvent.status.in_(("pending", "failed")),
                    or_(ExportOutboxEvent.next_attempt_at.is_(None), ExportOutboxEvent.next_attempt_at <= now),
                )
                .order_by(ExportOutboxEvent.timestamp.asc())
                .limit(limit)
                .all()
            )
            return [row.to_record() for row in rows]

    def mark_export_outbox_exported(self, outbox_id: str) -> None:
        with self._session() as session:
            row = session.get(ExportOutboxEvent, outbox_id)
            if row is None:
                return
            row.status = "exported"
            row.exported_at = utc_now_naive()
            row.last_error = None
            row.next_attempt_at = None
            session.commit()

    def mark_export_outbox_failed(
        self,
        outbox_id: str,
        *,
        error: str,
        retry_at: Optional[datetime] = None,
    ) -> None:
        with self._session() as session:
            row = session.get(ExportOutboxEvent, outbox_id)
            if row is None:
                return
            row.status = "failed"
            row.attempts = row.attempts + 1
            row.last_error = error[:2000]
            row.next_attempt_at = retry_at or (utc_now_naive() + timedelta(seconds=60))
            session.commit()

    def cleanup_older_than(
        self,
        *,
        events_before: Optional[datetime] = None,
        audit_events_before: Optional[datetime] = None,
        ai_model_usage_before: Optional[datetime] = None,
        export_outbox_before: Optional[datetime] = None,
        trace_archive_queue_before: Optional[datetime] = None,
    ) -> dict[str, int]:
        deleted = {"events": 0, "audit_events": 0, "ai_model_usage_events": 0, "ai_model_runtime_events": 0, "obs_export_outbox": 0, "obs_trace_archive_queue": 0}
        with self._session() as session:
            if events_before is not None:
                deleted["events"] = session.query(Event).filter(Event.timestamp < events_before).delete()
            if audit_events_before is not None:
                deleted["audit_events"] = session.query(AuditEvent).filter(AuditEvent.timestamp < audit_events_before).delete()
            if ai_model_usage_before is not None:
                deleted["ai_model_usage_events"] = session.query(AIModelUsageEvent).filter(AIModelUsageEvent.timestamp < ai_model_usage_before).delete()
                deleted["ai_model_runtime_events"] = session.query(AIModelRuntimeEvent).filter(AIModelRuntimeEvent.timestamp < ai_model_usage_before).delete()
            if export_outbox_before is not None:
                deleted["obs_export_outbox"] = session.query(ExportOutboxEvent).filter(ExportOutboxEvent.timestamp < export_outbox_before).delete()
            if trace_archive_queue_before is not None:
                deleted["obs_trace_archive_queue"] = (
                    session.query(TraceArchiveQueueEvent)
                    .filter(
                        TraceArchiveQueueEvent.status == "archived",
                        TraceArchiveQueueEvent.timestamp < trace_archive_queue_before,
                    )
                    .delete()
                )
            session.commit()
        return deleted
