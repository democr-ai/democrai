from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import uuid4

from democrai.core.infrastructure.storage.observability.models import ExportOutboxRecord
from democrai.core.infrastructure.storage.observability.models import TraceArchiveQueueRecord
from democrai.core.platform.utils.timezone import utc_now_naive


class ClickHouseOutboxMixin:
    def enqueue_trace_archive(self, *, pipeline_step_db_id: Optional[int], pipeline_id: str, request_id: Optional[str], step_id: str, payload_kind: str, payload: dict, payload_hash: Optional[str] = None) -> TraceArchiveQueueRecord:
        timestamp = utc_now_naive()
        payload_json = json.dumps(payload or {})
        archive_id = str(uuid4())
        self._client.insert(
            "obs_trace_archive_queue",
            [[archive_id, timestamp, pipeline_step_db_id, pipeline_id, request_id, step_id, payload_kind, "pending", 0, None, None, timestamp, None, payload_hash, None, payload_json]],
            column_names=["id", "timestamp", "pipeline_step_db_id", "pipeline_id", "request_id", "step_id", "payload_kind", "status", "attempts", "locked_by", "locked_at", "next_attempt_at", "archived_media_path", "payload_hash", "last_error", "payload_json"],
        )
        return TraceArchiveQueueRecord(id=archive_id, timestamp=timestamp, pipeline_step_db_id=pipeline_step_db_id, pipeline_id=pipeline_id, request_id=request_id, step_id=step_id, payload_kind=payload_kind, status="pending", attempts=0, locked_by=None, locked_at=None, next_attempt_at=timestamp, archived_media_path=None, payload_hash=payload_hash, last_error=None, payload_json=payload_json)

    def get_trace_archive_ready(self, *, limit: int = 100, lock_timeout_seconds: int = 300) -> list[TraceArchiveQueueRecord]:
        rows = self._client.query(
            """
            SELECT id, timestamp, pipeline_step_db_id, pipeline_id, request_id, step_id,
                   payload_kind, status, attempts, locked_by, locked_at, next_attempt_at,
                   archived_media_path, payload_hash, last_error, payload_json
            FROM obs_trace_archive_queue FINAL
            WHERE (
                status IN ('pending', 'failed')
                OR (status = 'processing' AND locked_at <= now64(3) - toIntervalSecond(%(lock_timeout_seconds)s))
            )
              AND (next_attempt_at IS NULL OR next_attempt_at <= now64(3))
            ORDER BY timestamp ASC
            LIMIT %(limit)s
            """,
            parameters={"limit": max(1, limit), "lock_timeout_seconds": max(1, lock_timeout_seconds)},
        ).result_rows
        return [self._to_trace_archive_record(row) for row in rows]

    def mark_trace_archive_processing(self, archive_id: str, *, locked_by: str) -> None:
        current = self._latest_trace_archive_row(archive_id)
        if current is None:
            return
        now = utc_now_naive()
        self._insert_trace_archive_row(current, status="processing", locked_by=locked_by, locked_at=now, last_error=None, timestamp=now)

    def mark_trace_archive_archived(self, archive_id: str, *, archived_media_path: str) -> None:
        current = self._latest_trace_archive_row(archive_id)
        if current is None:
            return
        now = utc_now_naive()
        self._insert_trace_archive_row(current, status="archived", archived_media_path=archived_media_path, next_attempt_at=None, last_error=None, payload_json="{}", timestamp=now)

    def mark_trace_archive_failed(self, archive_id: str, *, error: str, retry_at: Optional[datetime] = None) -> None:
        current = self._latest_trace_archive_row(archive_id)
        if current is None:
            return
        now = utc_now_naive()
        self._insert_trace_archive_row(current, status="failed", attempts=current.attempts + 1, next_attempt_at=retry_at or (now + timedelta(seconds=60)), last_error=error[:4000], timestamp=now)

    def update_ai_model_pipeline_step_archive(self, *, step_db_id: Optional[int], step_id: str, archive_status: str, archive_media_path: Optional[str], archive_error: Optional[str]) -> None:
        self._client.command(
            """
            ALTER TABLE ai_model_pipeline_steps
            UPDATE
                archive_status = %(archive_status)s,
                archive_media_path = %(archive_media_path)s,
                archive_error = %(archive_error)s
            WHERE step_id = %(step_id)s
            """,
            parameters={
                "archive_status": archive_status,
                "archive_media_path": archive_media_path,
                "archive_error": archive_error,
                "step_id": step_id,
            },
        )

    def enqueue_export_outbox(self, *, event_kind: str, payload: dict, correlation_id: Optional[str] = None, source_node_id: Optional[str] = None, dedupe_key: Optional[str] = None) -> ExportOutboxRecord:
        timestamp = utc_now_naive()
        payload_json = json.dumps(payload or {})
        outbox_id = str(uuid4())
        if dedupe_key:
            existing = self._client.query(
                """
                SELECT id, timestamp, event_kind, correlation_id, source_node_id, dedupe_key,
                       status, attempts, next_attempt_at, exported_at, last_error, payload_json
                FROM obs_export_outbox
                WHERE dedupe_key = %(dedupe_key)s
                ORDER BY timestamp DESC
                LIMIT 1
                """,
                parameters={"dedupe_key": dedupe_key},
            ).result_rows
            if existing:
                return self._to_outbox_record(existing[0])
        self._client.insert(
            "obs_export_outbox",
            [[outbox_id, timestamp, event_kind, correlation_id, source_node_id, dedupe_key, "pending", 0, timestamp, None, None, payload_json]],
            column_names=["id", "timestamp", "event_kind", "correlation_id", "source_node_id", "dedupe_key", "status", "attempts", "next_attempt_at", "exported_at", "last_error", "payload_json"],
        )
        return ExportOutboxRecord(id=outbox_id, timestamp=timestamp, event_kind=event_kind, correlation_id=correlation_id, source_node_id=source_node_id, dedupe_key=dedupe_key, status="pending", attempts=0, next_attempt_at=timestamp, exported_at=None, last_error=None, payload_json=payload_json)

    def get_export_outbox_ready(self, *, limit: int = 100) -> list[ExportOutboxRecord]:
        rows = self._client.query(
            """
            SELECT id, timestamp, event_kind, correlation_id, source_node_id, dedupe_key,
                   status, attempts, next_attempt_at, exported_at, last_error, payload_json
            FROM obs_export_outbox
            WHERE status IN ('pending', 'failed')
              AND (next_attempt_at IS NULL OR next_attempt_at <= now64(3))
            ORDER BY timestamp ASC
            LIMIT %(limit)s
            """,
            parameters={"limit": limit},
        ).result_rows
        return [self._to_outbox_record(row) for row in rows]

    def mark_export_outbox_exported(self, outbox_id: str) -> None:
        row = self._client.query(
            """
            SELECT id, event_kind, correlation_id, source_node_id, dedupe_key, attempts, payload_json
            FROM obs_export_outbox
            WHERE id = %(id)s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            parameters={"id": outbox_id},
        ).result_rows
        if not row:
            return
        current = row[0]
        now = utc_now_naive()
        self._client.insert(
            "obs_export_outbox",
            [[current[0], now, current[1], current[2], current[3], current[4], "exported", int(current[5]), None, now, None, current[6]]],
            column_names=["id", "timestamp", "event_kind", "correlation_id", "source_node_id", "dedupe_key", "status", "attempts", "next_attempt_at", "exported_at", "last_error", "payload_json"],
        )

    def mark_export_outbox_failed(self, outbox_id: str, *, error: str, retry_at: Optional[datetime] = None) -> None:
        row = self._client.query(
            """
            SELECT id, event_kind, correlation_id, source_node_id, dedupe_key, attempts, payload_json
            FROM obs_export_outbox
            WHERE id = %(id)s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            parameters={"id": outbox_id},
        ).result_rows
        if not row:
            return
        current = row[0]
        now = utc_now_naive()
        next_attempt_at = retry_at or (now + timedelta(seconds=60))
        self._client.insert(
            "obs_export_outbox",
            [[current[0], now, current[1], current[2], current[3], current[4], "failed", int(current[5]) + 1, next_attempt_at, None, error[:2000], current[6]]],
            column_names=["id", "timestamp", "event_kind", "correlation_id", "source_node_id", "dedupe_key", "status", "attempts", "next_attempt_at", "exported_at", "last_error", "payload_json"],
        )

    def cleanup_older_than(self, *, events_before: Optional[datetime] = None, audit_events_before: Optional[datetime] = None, ai_model_usage_before: Optional[datetime] = None, export_outbox_before: Optional[datetime] = None, trace_archive_queue_before: Optional[datetime] = None) -> dict[str, int]:
        if events_before is not None:
            self._client.command("ALTER TABLE events DELETE WHERE timestamp < toDateTime64(%(ts)s, 3)", parameters={"ts": events_before.strftime("%Y-%m-%d %H:%M:%S.%f")})
        if audit_events_before is not None:
            self._client.command("ALTER TABLE audit_events DELETE WHERE timestamp < toDateTime64(%(ts)s, 3)", parameters={"ts": audit_events_before.strftime("%Y-%m-%d %H:%M:%S.%f")})
        if ai_model_usage_before is not None:
            self._client.command("ALTER TABLE ai_model_usage_events DELETE WHERE timestamp < toDateTime64(%(ts)s, 3)", parameters={"ts": ai_model_usage_before.strftime("%Y-%m-%d %H:%M:%S.%f")})
            self._client.command("ALTER TABLE ai_model_runtime_events DELETE WHERE timestamp < toDateTime64(%(ts)s, 3)", parameters={"ts": ai_model_usage_before.strftime("%Y-%m-%d %H:%M:%S.%f")})
        if export_outbox_before is not None:
            self._client.command("ALTER TABLE obs_export_outbox DELETE WHERE timestamp < toDateTime64(%(ts)s, 3)", parameters={"ts": export_outbox_before.strftime("%Y-%m-%d %H:%M:%S.%f")})
        if trace_archive_queue_before is not None:
            self._client.command(
                "ALTER TABLE obs_trace_archive_queue DELETE WHERE status = 'archived' AND timestamp < toDateTime64(%(ts)s, 3)",
                parameters={"ts": trace_archive_queue_before.strftime("%Y-%m-%d %H:%M:%S.%f")},
            )
        return {"events": 0, "audit_events": 0, "ai_model_usage_events": 0, "ai_model_runtime_events": 0, "obs_export_outbox": 0, "obs_trace_archive_queue": 0}

    def _latest_trace_archive_row(self, archive_id: str) -> TraceArchiveQueueRecord | None:
        rows = self._client.query(
            """
            SELECT id, timestamp, pipeline_step_db_id, pipeline_id, request_id, step_id,
                   payload_kind, status, attempts, locked_by, locked_at, next_attempt_at,
                   archived_media_path, payload_hash, last_error, payload_json
            FROM obs_trace_archive_queue FINAL
            WHERE id = %(id)s
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            parameters={"id": archive_id},
        ).result_rows
        if not rows:
            return None
        return self._to_trace_archive_record(rows[0])

    def _insert_trace_archive_row(self, row: TraceArchiveQueueRecord, **overrides: Any) -> None:
        self._client.insert(
            "obs_trace_archive_queue",
            [[
                row.id,
                overrides.get("timestamp", utc_now_naive()),
                row.pipeline_step_db_id,
                row.pipeline_id,
                row.request_id,
                row.step_id,
                row.payload_kind,
                overrides.get("status", row.status),
                overrides.get("attempts", row.attempts),
                overrides.get("locked_by", row.locked_by),
                overrides.get("locked_at", row.locked_at),
                overrides.get("next_attempt_at", row.next_attempt_at),
                overrides.get("archived_media_path", row.archived_media_path),
                row.payload_hash,
                overrides.get("last_error", row.last_error),
                overrides.get("payload_json", row.payload_json),
            ]],
            column_names=["id", "timestamp", "pipeline_step_db_id", "pipeline_id", "request_id", "step_id", "payload_kind", "status", "attempts", "locked_by", "locked_at", "next_attempt_at", "archived_media_path", "payload_hash", "last_error", "payload_json"],
        )

    @staticmethod
    def _to_trace_archive_record(row: tuple[Any, ...]) -> TraceArchiveQueueRecord:
        return TraceArchiveQueueRecord(
            id=row[0],
            timestamp=row[1],
            pipeline_step_db_id=row[2],
            pipeline_id=row[3],
            request_id=row[4],
            step_id=row[5],
            payload_kind=row[6],
            status=row[7],
            attempts=row[8],
            locked_by=row[9],
            locked_at=row[10],
            next_attempt_at=row[11],
            archived_media_path=row[12],
            payload_hash=row[13],
            last_error=row[14],
            payload_json=row[15],
        )

    @staticmethod
    def _to_outbox_record(row: tuple[Any, ...]) -> ExportOutboxRecord:
        return ExportOutboxRecord(
            id=row[0],
            timestamp=row[1],
            event_kind=row[2],
            correlation_id=row[3],
            source_node_id=row[4],
            dedupe_key=row[5],
            status=row[6],
            attempts=row[7],
            next_attempt_at=row[8],
            exported_at=row[9],
            last_error=row[10],
            payload_json=row[11],
        )
