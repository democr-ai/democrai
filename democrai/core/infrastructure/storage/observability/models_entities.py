from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase

from democrai.core.infrastructure.storage.observability.models_records import (
    AuditEventRecord,
    AIModelPipelineStepRecord,
    EventRecord,
    ExportOutboxRecord,
    AIModelRuntimeEventRecord,
    AIModelUsageEventRecord,
    TraceArchiveQueueRecord,
)
from democrai.core.platform.utils.timezone import utc_now_naive


class Base(DeclarativeBase):
    pass


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False)
    level = Column(String(20), nullable=False)
    category = Column(String(50), nullable=False)
    user_id = Column(Integer, nullable=True)
    session_id = Column(String(255), nullable=True)
    agent_id = Column(String(255), nullable=True)
    event_name = Column(String(255), nullable=False)
    payload = Column(Text, nullable=False, default="{}")
    duration_ms = Column(Float, nullable=True)
    correlation_id = Column(String(255), nullable=False)

    __table_args__ = (
        Index("idx_events_ts", "timestamp"),
        Index("idx_events_category", "category"),
        Index("idx_events_user", "user_id"),
        Index("idx_events_correlation", "correlation_id"),
        Index("idx_events_composite", "user_id", "timestamp"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> EventRecord:
        return EventRecord(
            id=self.id,
            timestamp=self.timestamp,
            level=self.level,
            category=self.category,
            user_id=self.user_id,
            session_id=self.session_id,
            agent_id=self.agent_id,
            event_name=self.event_name,
            payload=self.payload,
            duration_ms=self.duration_ms,
            correlation_id=self.correlation_id,
        )


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False)
    event_type = Column(String(64), nullable=False, index=True)
    actor_user_id = Column(Integer, nullable=True, index=True)
    actor_role = Column(String(64), nullable=True)
    organization_id = Column(Integer, nullable=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    node_id = Column(String(255), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    correlation_id = Column(String(255), nullable=True, index=True)
    client_ip = Column(String(255), nullable=True, index=True)
    channel = Column(String(32), nullable=True)
    entity_type = Column(String(255), nullable=True, index=True)
    entity_id = Column(String(255), nullable=True, index=True)
    operation = Column(String(64), nullable=True, index=True)
    status = Column(String(32), nullable=True, index=True)
    before_json = Column(Text, nullable=False, default="{}")
    after_json = Column(Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("idx_audit_events_ts", "timestamp"),
        Index("idx_audit_events_actor", "actor_user_id", "timestamp"),
        Index("idx_audit_events_entity", "entity_type", "entity_id"),
        Index("idx_audit_events_corr", "correlation_id"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> AuditEventRecord:
        return AuditEventRecord(
            id=self.id,
            timestamp=self.timestamp,
            event_type=self.event_type,
            actor_user_id=self.actor_user_id,
            actor_role=self.actor_role,
            organization_id=self.organization_id,
            session_id=self.session_id,
            node_id=self.node_id,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            client_ip=self.client_ip,
            channel=self.channel,
            entity_type=self.entity_type,
            entity_id=self.entity_id,
            operation=self.operation,
            status=self.status,
            before_json=self.before_json,
            after_json=self.after_json,
            metadata_json=self.metadata_json,
        )


class AIModelUsageEvent(Base):
    __tablename__ = "ai_model_usage_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False)
    user_id = Column(Integer, nullable=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    node_id = Column(String(255), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    correlation_id = Column(String(255), nullable=True, index=True)
    client_ip = Column(String(255), nullable=True, index=True)
    channel = Column(String(32), nullable=True)
    objective = Column(String(128), nullable=True, index=True)
    provider = Column(String(128), nullable=True, index=True)
    engine = Column(String(128), nullable=True, index=True)
    model_name = Column(String(255), nullable=True, index=True)
    deployment_mode = Column(String(64), nullable=True, index=True)
    request_kind = Column(String(64), nullable=True, index=True)
    agent_id = Column(String(255), nullable=True, index=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Float, nullable=True)
    tokens_per_second = Column(Float, nullable=True)
    success = Column(Boolean, nullable=False, default=True, index=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("idx_ai_model_usage_ts", "timestamp"),
        Index("idx_ai_model_usage_user", "user_id", "timestamp"),
        Index("idx_ai_model_usage_model", "model_name", "timestamp"),
        Index("idx_ai_model_usage_corr", "correlation_id"),
        Index("idx_ai_model_usage_node", "node_id"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> AIModelUsageEventRecord:
        return AIModelUsageEventRecord(
            id=self.id,
            timestamp=self.timestamp,
            user_id=self.user_id,
            organization_id=self.organization_id,
            session_id=self.session_id,
            node_id=self.node_id,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            client_ip=self.client_ip,
            channel=self.channel,
            objective=self.objective,
            provider=self.provider,
            engine=self.engine,
            model_name=self.model_name,
            deployment_mode=self.deployment_mode,
            request_kind=self.request_kind,
            agent_id=self.agent_id,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.total_tokens,
            duration_ms=self.duration_ms,
            tokens_per_second=self.tokens_per_second,
            success=bool(self.success),
            error=self.error,
            metadata_json=self.metadata_json,
        )


class AIModelRuntimeEvent(Base):
    __tablename__ = "ai_model_runtime_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False)
    user_id = Column(Integer, nullable=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    correlation_id = Column(String(255), nullable=True, index=True)
    client_ip = Column(String(255), nullable=True, index=True)
    channel = Column(String(32), nullable=True)
    event_type = Column(String(64), nullable=False, index=True)
    provider = Column(String(128), nullable=True, index=True)
    engine = Column(String(128), nullable=True, index=True)
    engine_row_id = Column(Integer, nullable=True, index=True)
    model_registry_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(255), nullable=True, index=True)
    node_id = Column(String(255), nullable=True, index=True)
    config_signature = Column(Text, nullable=True)
    warmup_ms = Column(Float, nullable=True)
    model_weight_vram_mb = Column(Integer, nullable=True)
    vram_before_mb = Column(Integer, nullable=True)
    vram_after_mb = Column(Integer, nullable=True)
    vram_delta_mb = Column(Integer, nullable=True)
    runtime_allocated_vram_mb = Column(Integer, nullable=True)
    ram_before_mb = Column(Integer, nullable=True)
    ram_after_mb = Column(Integer, nullable=True)
    success = Column(Boolean, nullable=False, default=True, index=True)
    error = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("idx_ai_model_runtime_ts", "timestamp"),
        Index("idx_ai_model_runtime_model", "model_name", "timestamp"),
        Index("idx_ai_model_runtime_engine", "engine_row_id", "timestamp"),
        Index("idx_ai_model_runtime_corr", "correlation_id"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> AIModelRuntimeEventRecord:
        return AIModelRuntimeEventRecord(
            id=self.id,
            timestamp=self.timestamp,
            user_id=self.user_id,
            organization_id=self.organization_id,
            session_id=self.session_id,
            request_id=self.request_id,
            correlation_id=self.correlation_id,
            client_ip=self.client_ip,
            channel=self.channel,
            event_type=self.event_type,
            provider=self.provider,
            engine=self.engine,
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            model_name=self.model_name,
            node_id=self.node_id,
            config_signature=self.config_signature,
            warmup_ms=self.warmup_ms,
            model_weight_vram_mb=self.model_weight_vram_mb,
            vram_before_mb=self.vram_before_mb,
            vram_after_mb=self.vram_after_mb,
            vram_delta_mb=self.vram_delta_mb,
            runtime_allocated_vram_mb=self.runtime_allocated_vram_mb,
            ram_before_mb=self.ram_before_mb,
            ram_after_mb=self.ram_after_mb,
            success=bool(self.success),
            error=self.error,
            metadata_json=self.metadata_json,
        )


class AIModelPipelineStep(Base):
    __tablename__ = "ai_model_pipeline_steps"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False)
    pipeline_id = Column(String(64), nullable=False, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    step_id = Column(String(64), nullable=False, index=True)
    parent_step_id = Column(String(64), nullable=True, index=True)
    root_method = Column(String(64), nullable=False, index=True)
    type = Column(String(64), nullable=False, index=True)
    name = Column(String(128), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    started_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    provider = Column(String(128), nullable=True, index=True)
    engine = Column(String(128), nullable=True, index=True)
    engine_row_id = Column(Integer, nullable=True, index=True)
    model_registry_id = Column(Integer, nullable=True, index=True)
    model_name = Column(String(255), nullable=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    session_id = Column(String(255), nullable=True, index=True)
    node_id = Column(String(255), nullable=True, index=True)
    input_json = Column(Text, nullable=False, default="{}")
    output_json = Column(Text, nullable=False, default="{}")
    stats_json = Column(Text, nullable=False, default="{}")
    error = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    input_hash = Column(String(80), nullable=True)
    output_hash = Column(String(80), nullable=True)
    input_size_bytes = Column(Integer, nullable=True)
    output_size_bytes = Column(Integer, nullable=True)
    archive_status = Column(String(32), nullable=False, default="none", index=True)
    archive_media_path = Column(Text, nullable=True)
    archive_error = Column(Text, nullable=True)

    __table_args__ = (
        Index("idx_ai_model_pipeline_ts", "timestamp"),
        Index("idx_ai_model_pipeline_id_ts", "pipeline_id", "timestamp"),
        Index("idx_ai_model_pipeline_request", "request_id"),
        Index("idx_ai_model_pipeline_step", "step_id"),
        Index("idx_ai_model_pipeline_parent", "parent_step_id"),
        Index("idx_ai_model_pipeline_type", "type"),
        Index("idx_ai_model_pipeline_status", "status"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> AIModelPipelineStepRecord:
        return AIModelPipelineStepRecord(
            id=self.id,
            timestamp=self.timestamp,
            pipeline_id=self.pipeline_id,
            request_id=self.request_id,
            step_id=self.step_id,
            parent_step_id=self.parent_step_id,
            root_method=self.root_method,
            type=self.type,
            name=self.name,
            status=self.status,
            started_at=self.started_at,
            duration_ms=self.duration_ms,
            provider=self.provider,
            engine=self.engine,
            engine_row_id=self.engine_row_id,
            model_registry_id=self.model_registry_id,
            model_name=self.model_name,
            user_id=self.user_id,
            organization_id=self.organization_id,
            session_id=self.session_id,
            node_id=self.node_id,
            input_json=self.input_json,
            output_json=self.output_json,
            stats_json=self.stats_json,
            error=self.error,
            metadata_json=self.metadata_json,
            input_hash=self.input_hash,
            output_hash=self.output_hash,
            input_size_bytes=self.input_size_bytes,
            output_size_bytes=self.output_size_bytes,
            archive_status=self.archive_status,
            archive_media_path=self.archive_media_path,
            archive_error=self.archive_error,
        )


class TraceArchiveQueueEvent(Base):
    __tablename__ = "obs_trace_archive_queue"

    id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    pipeline_step_db_id = Column(Integer, nullable=True, index=True)
    pipeline_id = Column(String(64), nullable=False, index=True)
    request_id = Column(String(255), nullable=True, index=True)
    step_id = Column(String(64), nullable=False, index=True)
    payload_kind = Column(String(64), nullable=False, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    locked_by = Column(String(255), nullable=True, index=True)
    locked_at = Column(DateTime, nullable=True, index=True)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    archived_media_path = Column(Text, nullable=True)
    payload_hash = Column(String(80), nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("idx_obs_trace_archive_status_next", "status", "next_attempt_at"),
        Index("idx_obs_trace_archive_pipeline_step", "pipeline_id", "step_id"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> TraceArchiveQueueRecord:
        return TraceArchiveQueueRecord(
            id=self.id,
            timestamp=self.timestamp,
            pipeline_step_db_id=self.pipeline_step_db_id,
            pipeline_id=self.pipeline_id,
            request_id=self.request_id,
            step_id=self.step_id,
            payload_kind=self.payload_kind,
            status=self.status,
            attempts=self.attempts,
            locked_by=self.locked_by,
            locked_at=self.locked_at,
            next_attempt_at=self.next_attempt_at,
            archived_media_path=self.archived_media_path,
            payload_hash=self.payload_hash,
            last_error=self.last_error,
            payload_json=self.payload_json,
        )


class ExportOutboxEvent(Base):
    __tablename__ = "obs_export_outbox"

    id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    event_kind = Column(String(32), nullable=False, index=True)
    correlation_id = Column(String(255), nullable=True, index=True)
    source_node_id = Column(String(255), nullable=True, index=True)
    dedupe_key = Column(String(255), nullable=True, unique=True, index=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=True, index=True)
    exported_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")

    __table_args__ = (
        Index("idx_obs_export_outbox_status_next", "status", "next_attempt_at"),
        Index("idx_obs_export_outbox_kind_ts", "event_kind", "timestamp"),
    )

    def to_dict(self):
        return self.to_record().to_dict()

    def to_record(self) -> ExportOutboxRecord:
        return ExportOutboxRecord(
            id=self.id,
            timestamp=self.timestamp,
            event_kind=self.event_kind,
            correlation_id=self.correlation_id,
            source_node_id=self.source_node_id,
            dedupe_key=self.dedupe_key,
            status=self.status,
            attempts=self.attempts,
            next_attempt_at=self.next_attempt_at,
            exported_at=self.exported_at,
            last_error=self.last_error,
            payload_json=self.payload_json,
        )
