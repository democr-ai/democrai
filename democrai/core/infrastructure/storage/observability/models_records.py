from __future__ import annotations

import json
from dataclasses import dataclass

from democrai.core.platform.utils.timezone import format_app_datetime
from democrai.core.platform.utils.timezone import serialize_app_datetime


@dataclass(frozen=True)
class EventRecord:
    id: int | None
    timestamp: object
    level: str
    category: str
    user_id: int | None
    session_id: str | None
    agent_id: str | None
    event_name: str
    payload: str
    duration_ms: float | None
    correlation_id: str

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "level": self.level,
            "category": self.category,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "event": self.event_name,
            "payload": json.loads(self.payload),
            "duration_ms": self.duration_ms,
            "correlation_id": self.correlation_id,
        }


@dataclass(frozen=True)
class AuditEventRecord:
    id: int | None
    timestamp: object
    event_type: str
    actor_user_id: int | None
    actor_role: str | None
    organization_id: int | None
    session_id: str | None
    node_id: str | None
    request_id: str | None
    correlation_id: str | None
    client_ip: str | None
    channel: str | None
    entity_type: str | None
    entity_id: str | None
    operation: str | None
    status: str | None
    before_json: str
    after_json: str
    metadata_json: str

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "event_type": self.event_type,
            "actor_user_id": self.actor_user_id,
            "actor_role": self.actor_role,
            "organization_id": self.organization_id,
            "session_id": self.session_id,
            "node_id": self.node_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "client_ip": self.client_ip,
            "channel": self.channel,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "operation": self.operation,
            "status": self.status,
            "before": json.loads(self.before_json or "{}"),
            "after": json.loads(self.after_json or "{}"),
            "metadata": json.loads(self.metadata_json or "{}"),
        }


@dataclass(frozen=True)
class AIModelUsageEventRecord:
    id: int | None
    timestamp: object
    user_id: int | None
    organization_id: int | None
    session_id: str | None
    node_id: str | None
    request_id: str | None
    correlation_id: str | None
    client_ip: str | None
    channel: str | None
    objective: str | None
    provider: str | None
    engine: str | None
    model_name: str | None
    deployment_mode: str | None
    request_kind: str | None
    agent_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    duration_ms: float | None
    tokens_per_second: float | None
    success: bool
    error: str | None
    metadata_json: str

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_id": self.session_id,
            "node_id": self.node_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "client_ip": self.client_ip,
            "channel": self.channel,
            "objective": self.objective,
            "provider": self.provider,
            "engine": self.engine,
            "model_name": self.model_name,
            "deployment_mode": self.deployment_mode,
            "request_kind": self.request_kind,
            "agent_id": self.agent_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "duration_ms": self.duration_ms,
            "tokens_per_second": self.tokens_per_second,
            "success": self.success,
            "error": self.error,
            "metadata": json.loads(self.metadata_json or "{}"),
        }


@dataclass(frozen=True)
class AIModelRuntimeEventRecord:
    id: int | None
    timestamp: object
    user_id: int | None
    organization_id: int | None
    session_id: str | None
    request_id: str | None
    correlation_id: str | None
    client_ip: str | None
    channel: str | None
    event_type: str
    provider: str | None
    engine: str | None
    engine_row_id: int | None
    model_registry_id: int | None
    model_name: str | None
    node_id: str | None
    config_signature: str | None
    warmup_ms: float | None
    model_weight_vram_mb: int | None
    vram_before_mb: int | None
    vram_after_mb: int | None
    vram_delta_mb: int | None
    runtime_allocated_vram_mb: int | None
    ram_before_mb: int | None
    ram_after_mb: int | None
    success: bool
    error: str | None
    metadata_json: str

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "correlation_id": self.correlation_id,
            "client_ip": self.client_ip,
            "channel": self.channel,
            "event_type": self.event_type,
            "provider": self.provider,
            "engine": self.engine,
            "engine_row_id": self.engine_row_id,
            "model_registry_id": self.model_registry_id,
            "model_name": self.model_name,
            "node_id": self.node_id,
            "config_signature": self.config_signature,
            "warmup_ms": self.warmup_ms,
            "model_weight_vram_mb": self.model_weight_vram_mb,
            "vram_before_mb": self.vram_before_mb,
            "vram_after_mb": self.vram_after_mb,
            "vram_delta_mb": self.vram_delta_mb,
            "runtime_allocated_vram_mb": self.runtime_allocated_vram_mb,
            "ram_before_mb": self.ram_before_mb,
            "ram_after_mb": self.ram_after_mb,
            "success": self.success,
            "error": self.error,
            "metadata": json.loads(self.metadata_json or "{}"),
        }


@dataclass(frozen=True)
class AIModelPipelineStepRecord:
    id: int | None
    timestamp: object
    pipeline_id: str
    request_id: str | None
    step_id: str
    parent_step_id: str | None
    root_method: str
    type: str
    name: str
    status: str
    started_at: object | None
    duration_ms: float | None
    provider: str | None
    engine: str | None
    engine_row_id: int | None
    model_registry_id: int | None
    model_name: str | None
    user_id: int | None
    organization_id: int | None
    session_id: str | None
    node_id: str | None
    input_json: str
    output_json: str
    stats_json: str
    error: str | None
    metadata_json: str
    input_hash: str | None = None
    output_hash: str | None = None
    input_size_bytes: int | None = None
    output_size_bytes: int | None = None
    archive_status: str | None = None
    archive_media_path: str | None = None
    archive_error: str | None = None

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "pipeline_id": self.pipeline_id,
            "request_id": self.request_id,
            "step_id": self.step_id,
            "parent_step_id": self.parent_step_id,
            "root_method": self.root_method,
            "type": self.type,
            "name": self.name,
            "status": self.status,
            "started_at": (
                serialize_app_datetime(self.started_at)
                if self.started_at is not None
                else None
            ),
            "duration_ms": self.duration_ms,
            "provider": self.provider,
            "engine": self.engine,
            "engine_row_id": self.engine_row_id,
            "model_registry_id": self.model_registry_id,
            "model_name": self.model_name,
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_id": self.session_id,
            "node_id": self.node_id,
            "input": json.loads(self.input_json or "{}"),
            "output": json.loads(self.output_json or "{}"),
            "stats": json.loads(self.stats_json or "{}"),
            "error": self.error,
            "metadata": json.loads(self.metadata_json or "{}"),
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "input_size_bytes": self.input_size_bytes,
            "output_size_bytes": self.output_size_bytes,
            "archive_status": self.archive_status,
            "archive_media_path": self.archive_media_path,
            "archive_error": self.archive_error,
        }


@dataclass(frozen=True)
class TraceArchiveQueueRecord:
    id: str
    timestamp: object
    pipeline_step_db_id: int | None
    pipeline_id: str
    request_id: str | None
    step_id: str
    payload_kind: str
    status: str
    attempts: int
    locked_by: str | None
    locked_at: object | None
    next_attempt_at: object | None
    archived_media_path: str | None
    payload_hash: str | None
    last_error: str | None
    payload_json: str

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "pipeline_step_db_id": self.pipeline_step_db_id,
            "pipeline_id": self.pipeline_id,
            "request_id": self.request_id,
            "step_id": self.step_id,
            "payload_kind": self.payload_kind,
            "status": self.status,
            "attempts": self.attempts,
            "locked_by": self.locked_by,
            "locked_at": serialize_app_datetime(self.locked_at) if self.locked_at is not None else None,
            "locked_at_label": format_app_datetime(self.locked_at) if self.locked_at is not None else None,
            "next_attempt_at": serialize_app_datetime(self.next_attempt_at) if self.next_attempt_at is not None else None,
            "next_attempt_at_label": format_app_datetime(self.next_attempt_at) if self.next_attempt_at is not None else None,
            "archived_media_path": self.archived_media_path,
            "payload_hash": self.payload_hash,
            "last_error": self.last_error,
            "payload": json.loads(self.payload_json or "{}"),
        }


@dataclass(frozen=True)
class ExportOutboxRecord:
    id: str
    timestamp: object
    event_kind: str
    correlation_id: str | None
    source_node_id: str | None
    dedupe_key: str | None
    status: str
    attempts: int
    next_attempt_at: object | None
    exported_at: object | None
    last_error: str | None
    payload_json: str

    def to_dict(self):
        return {
            "id": self.id,
            "timestamp": serialize_app_datetime(self.timestamp),
            "timestamp_label": format_app_datetime(self.timestamp),
            "event_kind": self.event_kind,
            "correlation_id": self.correlation_id,
            "source_node_id": self.source_node_id,
            "dedupe_key": self.dedupe_key,
            "status": self.status,
            "attempts": self.attempts,
            "next_attempt_at": serialize_app_datetime(self.next_attempt_at) if self.next_attempt_at is not None else None,
            "next_attempt_at_label": format_app_datetime(self.next_attempt_at) if self.next_attempt_at is not None else None,
            "exported_at": serialize_app_datetime(self.exported_at) if self.exported_at is not None else None,
            "exported_at_label": format_app_datetime(self.exported_at) if self.exported_at is not None else None,
            "last_error": self.last_error,
            "payload": json.loads(self.payload_json or "{}"),
        }
