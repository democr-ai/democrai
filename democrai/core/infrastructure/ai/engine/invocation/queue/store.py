from __future__ import annotations

import json
import uuid
from datetime import timedelta
from typing import Any, Callable

from sqlalchemy import or_, text

from democrai.core.infrastructure.ai.engine.invocation.queue.config import (
    ENGINE_INVOCATION_QUEUE_NOTIFY_CHANNEL,
    engine_response_stream_key,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.errors import (
    retry_delay_seconds,
)
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineInvocationQueue
from democrai.core.platform.utils.timezone import utc_now_naive


CLAIMABLE_STATUSES = ("pending", "failed")
TERMINAL_STATUSES = ("completed", "dead_letter", "cancelled")


class EngineInvocationQueueStore:
    """Durable engine invocation queue shared by every node (sync API).

    Claim semantics follow the knowledge extraction queue (SKIP LOCKED +
    lease) with one deliberate difference: ``processing`` rows whose lease
    expired are claimable again, so a crashed claimer never strands a job.
    Every claim consumes one attempt; ``release`` gives it back.
    """

    def __init__(self, session_factory: Callable | None = None) -> None:
        self._session_factory = session_factory or SessionLocal

    @staticmethod
    def _notify(session: Any, payload: dict[str, Any]) -> None:
        if session.get_bind().dialect.name != "postgresql":
            return
        session.execute(
            text("SELECT pg_notify(:channel, :payload)"),
            {
                "channel": ENGINE_INVOCATION_QUEUE_NOTIFY_CHANNEL,
                "payload": json.dumps(payload, ensure_ascii=True),
            },
        )

    @staticmethod
    def _snapshot(row: EngineInvocationQueue) -> dict[str, Any]:
        return {
            "id": row.id,
            "pipeline_id": row.pipeline_id,
            "selector_type": row.selector_type,
            "model_registry_id": row.model_registry_id,
            "objective": row.objective,
            "capabilities_json": row.capabilities_json,
            "prefer_local": row.prefer_local,
            "confirm_swap": bool(row.confirm_swap),
            "method": row.method,
            "response_mode": row.response_mode,
            "payload_json": row.payload_json,
            "request_context_json": row.request_context_json,
            "security_context_json": row.security_context_json,
            "origin_node_id": row.origin_node_id,
            "response_stream_key": row.response_stream_key,
            "requires_origin_hitl": bool(row.requires_origin_hitl),
            "status": row.status,
            "priority": int(row.priority or 0),
            "attempts": int(row.attempts or 0),
            "available_at": row.available_at,
            "lease_owner": row.lease_owner,
            "lease_expires_at": row.lease_expires_at,
            "cancel_requested": bool(row.cancel_requested),
            "first_chunk_at": row.first_chunk_at,
            "last_error": row.last_error,
            "created_at": row.created_at,
        }

    def enqueue(
        self,
        *,
        request_id: str | None = None,
        pipeline_id: str | None = None,
        selector_type: str,
        model_registry_id: int | None = None,
        objective: str | None = None,
        capabilities: list[str] | None = None,
        prefer_local: bool | None = None,
        confirm_swap: bool = False,
        method: str,
        response_mode: str = "unary",
        payload_json: str = "{}",
        request_context_json: str = "{}",
        security_context_json: str = "{}",
        origin_node_id: str,
        priority: int = 0,
    ) -> str:
        resolved_id = request_id or uuid.uuid4().hex
        if not selector_type:
            raise ValueError("engine_invocation_selector_type_required")
        if not method:
            raise ValueError("engine_invocation_method_required")
        if not origin_node_id:
            raise ValueError("engine_invocation_origin_node_id_required")
        now = utc_now_naive()
        with self._session_factory() as session:
            existing = session.get(EngineInvocationQueue, resolved_id)
            if existing is not None:
                return resolved_id
            session.add(
                EngineInvocationQueue(
                    id=resolved_id,
                    pipeline_id=pipeline_id,
                    selector_type=selector_type,
                    model_registry_id=model_registry_id,
                    objective=objective,
                    capabilities_json=json.dumps(
                        capabilities or [], ensure_ascii=True
                    ),
                    prefer_local=prefer_local,
                    confirm_swap=bool(confirm_swap),
                    method=method,
                    response_mode=response_mode or "unary",
                    payload_json=payload_json or "{}",
                    request_context_json=request_context_json or "{}",
                    security_context_json=security_context_json or "{}",
                    origin_node_id=origin_node_id,
                    response_stream_key=engine_response_stream_key(resolved_id),
                    status="pending",
                    priority=int(priority or 0),
                    attempts=0,
                    available_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            self._notify(session, {"kind": "enqueue", "id": resolved_id})
            session.commit()
        return resolved_id

    def _claimable_filter(self, query: Any, now: Any) -> Any:
        return query.filter(
            or_(
                EngineInvocationQueue.status.in_(CLAIMABLE_STATUSES)
                & (EngineInvocationQueue.available_at <= now),
                (EngineInvocationQueue.status == "processing")
                & EngineInvocationQueue.lease_expires_at.isnot(None)
                & (EngineInvocationQueue.lease_expires_at < now),
            )
        )

    def peek_claimable(
        self,
        *,
        limit: int = 16,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        now = utc_now_naive()
        with self._session_factory() as session:
            query = self._claimable_filter(
                session.query(EngineInvocationQueue), now
            ).order_by(
                EngineInvocationQueue.priority.desc(),
                EngineInvocationQueue.created_at.asc(),
            ).offset(max(0, int(offset))).limit(max(1, int(limit)))
            return [self._snapshot(row) for row in query.all()]

    def claim(
        self,
        request_ids: list[str],
        *,
        owner: str,
        lease_seconds: int,
    ) -> list[dict[str, Any]]:
        if not request_ids:
            return []
        now = utc_now_naive()
        lease_until = now + timedelta(seconds=max(1, int(lease_seconds)))
        claimed: list[dict[str, Any]] = []
        with self._session_factory() as session:
            query = self._claimable_filter(
                session.query(EngineInvocationQueue).filter(
                    EngineInvocationQueue.id.in_(request_ids)
                ),
                now,
            ).with_for_update(skip_locked=True)
            for row in query.all():
                row.status = "processing"
                row.lease_owner = owner
                row.lease_expires_at = lease_until
                row.claimed_by_node_id = owner
                row.attempts = int(row.attempts or 0) + 1
                row.started_at = row.started_at or now
                row.updated_at = now
                claimed.append(self._snapshot(row))
            session.commit()
        return claimed

    def renew_lease(
        self, request_id: str, *, owner: str, lease_seconds: int
    ) -> bool:
        renewed, _cancel_requested = self.renew_lease_and_check_cancel(
            request_id, owner=owner, lease_seconds=lease_seconds
        )
        return renewed

    def renew_lease_and_check_cancel(
        self, request_id: str, *, owner: str, lease_seconds: int
    ) -> tuple[bool, bool]:
        """Single round trip for the per-job maintenance loop: renew the
        lease and read the cancel flag. Returns (renewed, cancel_requested).
        """
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None:
                return False, False
            cancel_requested = bool(row.cancel_requested)
            if row.status != "processing" or row.lease_owner != owner:
                return False, cancel_requested
            row.lease_expires_at = now + timedelta(seconds=max(1, int(lease_seconds)))
            row.updated_at = now
            session.commit()
            return True, cancel_requested

    @staticmethod
    def _owned(row: EngineInvocationQueue, owner: str | None) -> bool:
        """Whether ``owner`` may settle this row.

        ``None`` is the administrative caller (maintenance) and always may;
        a worker may only settle rows it still holds the lease on — a zombie
        whose row was reclaimed must not overwrite the new owner's outcome.
        """
        if owner is None:
            return True
        return row.status == "processing" and row.lease_owner == owner

    def complete(
        self,
        request_id: str,
        *,
        owner: str | None = None,
        result_summary: dict[str, Any] | None = None,
    ) -> None:
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None or not self._owned(row, owner):
                return
            row.status = "completed"
            row.lease_owner = None
            row.lease_expires_at = None
            row.completed_at = now
            row.updated_at = now
            if result_summary is not None:
                row.result_summary_json = json.dumps(
                    result_summary, ensure_ascii=True, default=str
                )
            session.commit()

    def fail(
        self,
        request_id: str,
        *,
        error: str,
        retriable: bool,
        max_attempts: int,
        owner: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> str:
        """Record a failure; returns the resulting status ('stale' when the
        caller no longer owns the row)."""
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None:
                return "missing"
            if not self._owned(row, owner):
                return "stale"
            if owner is None and row.status == "processing":
                # Administrative failure (maintenance) must not kill a row a
                # worker claimed between the orphan scan and this write.
                return "stale"
            attempts = int(row.attempts or 0)
            row.last_error = str(error)
            row.lease_owner = None
            row.lease_expires_at = None
            row.updated_at = now
            if not retriable or attempts >= max(1, int(max_attempts)):
                row.status = "dead_letter"
                row.completed_at = now
            else:
                row.status = "failed"
                row.available_at = now + timedelta(
                    seconds=retry_delay_seconds(
                        attempts, retry_after=retry_after_seconds
                    )
                )
                self._notify(session, {"kind": "retry", "id": request_id})
            resulting = row.status
            session.commit()
            return resulting

    def release(
        self,
        request_id: str,
        *,
        defer_seconds: float,
        owner: str | None = None,
        reason: str | None = None,
        requires_origin_hitl: bool | None = None,
    ) -> None:
        """Put a claimed row back without consuming the attempt."""
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None or not self._owned(row, owner) or row.status != "processing":
                return
            row.status = "pending"
            row.lease_owner = None
            row.lease_expires_at = None
            row.attempts = max(0, int(row.attempts or 0) - 1)
            row.available_at = now + timedelta(seconds=max(0.0, float(defer_seconds)))
            if reason:
                row.last_error = str(reason)
            if requires_origin_hitl is not None:
                row.requires_origin_hitl = bool(requires_origin_hitl)
            row.updated_at = now
            self._notify(session, {"kind": "release", "id": request_id})
            session.commit()

    def mark_cancelled(
        self,
        request_id: str,
        *,
        reason: str = "cancelled",
        owner: str | None = None,
    ) -> None:
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None or row.status in TERMINAL_STATUSES:
                return
            if owner is not None and row.status == "processing" and row.lease_owner != owner:
                # A worker may only cancel-settle a row it still holds.
                return
            row.status = "cancelled"
            row.last_error = str(reason)
            row.lease_owner = None
            row.lease_expires_at = None
            row.completed_at = now
            row.updated_at = now
            session.commit()

    def request_cancel(self, request_id: str) -> str:
        """Returns 'cancelled' (was idle, now terminal), 'requested' or 'missing'."""
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None:
                return "missing"
            if row.status in TERMINAL_STATUSES:
                return "cancelled"
            row.cancel_requested = True
            row.updated_at = now
            if row.status in CLAIMABLE_STATUSES:
                row.status = "cancelled"
                row.last_error = "engine_orchestrator_cancelled"
                row.completed_at = now
                session.commit()
                return "cancelled"
            self._notify(session, {"kind": "cancel", "id": request_id})
            session.commit()
            return "requested"

    def cancel_requested(self, request_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            return bool(row is not None and row.cancel_requested)

    def mark_first_chunk(self, request_id: str, *, owner: str | None = None) -> None:
        now = utc_now_naive()
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None or not self._owned(row, owner):
                return
            if row.first_chunk_at is not None:
                return
            row.first_chunk_at = now
            row.updated_at = now
            session.commit()

    def get_status(self, request_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            row = session.get(EngineInvocationQueue, request_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "status": row.status,
                "attempts": int(row.attempts or 0),
                "last_error": row.last_error,
                "cancel_requested": bool(row.cancel_requested),
                "lease_owner": row.lease_owner,
            }

    def purge_terminal(self, *, retention_seconds: int) -> int:
        cutoff = utc_now_naive() - timedelta(
            seconds=max(0, int(retention_seconds))
        )
        with self._session_factory() as session:
            deleted = (
                session.query(EngineInvocationQueue)
                .filter(EngineInvocationQueue.status.in_(TERMINAL_STATUSES))
                .filter(EngineInvocationQueue.updated_at < cutoff)
                .delete(synchronize_session=False)
            )
            session.commit()
            return int(deleted or 0)
