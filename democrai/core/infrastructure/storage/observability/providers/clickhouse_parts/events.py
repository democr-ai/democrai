from __future__ import annotations

import json
from typing import Any, Optional

from democrai.core.infrastructure.storage.observability.models import EventRecord
from democrai.core.platform.utils.timezone import utc_now_naive


class ClickHouseEventsMixin:
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
        timestamp = utc_now_naive()
        payload_json = json.dumps(payload or {})
        self._client.insert(
            "events",
            [[timestamp, level, category, user_id, session_id, agent_id, event_name, payload_json, duration_ms, correlation_id]],
            column_names=["timestamp", "level", "category", "user_id", "session_id", "agent_id", "event_name", "payload", "duration_ms", "correlation_id"],
        )
        return EventRecord(
            id=None,
            timestamp=timestamp,
            level=level,
            category=category,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            event_name=event_name,
            payload=payload_json,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
        )

    def get_events(self, user_id: Optional[int] = None, category: Optional[str] = None, correlation_id: Optional[str] = None, limit: int = 100) -> list[EventRecord]:
        where, params = self._where_clause(user_id=user_id, category=category, correlation_id=correlation_id)
        query = f"""
            SELECT timestamp, level, category, user_id, session_id, agent_id,
                   event_name, payload, duration_ms, correlation_id
            FROM events
            {where}
            ORDER BY timestamp DESC
            LIMIT %(limit)s
        """
        params["limit"] = limit
        result = self._client.query(query, parameters=params)
        return [self._to_record(row) for row in result.result_rows]

    def get_flow(self, correlation_id: str) -> list[EventRecord]:
        result = self._client.query(
            """
            SELECT timestamp, level, category, user_id, session_id, agent_id,
                   event_name, payload, duration_ms, correlation_id
            FROM events
            WHERE correlation_id = %(correlation_id)s
            ORDER BY timestamp ASC
            """,
            parameters={"correlation_id": correlation_id},
        )
        return [self._to_record(row) for row in result.result_rows]

    @staticmethod
    def _where_clause(*, user_id: Optional[int], category: Optional[str], correlation_id: Optional[str]) -> tuple[str, dict[str, Any]]:
        params: dict[str, Any] = {}
        conditions: list[str] = []
        if user_id is not None:
            conditions.append("user_id = %(user_id)s")
            params["user_id"] = user_id
        if category:
            conditions.append("category = %(category)s")
            params["category"] = category
        if correlation_id:
            conditions.append("correlation_id = %(correlation_id)s")
            params["correlation_id"] = correlation_id
        if not conditions:
            return "", params
        return f"WHERE {' AND '.join(conditions)}", params

    @staticmethod
    def _to_record(row: tuple[Any, ...]) -> EventRecord:
        (timestamp, level, category, user_id, session_id, agent_id, event_name, payload, duration_ms, correlation_id) = row
        return EventRecord(
            id=None,
            timestamp=timestamp,
            level=level,
            category=category,
            user_id=user_id,
            session_id=session_id,
            agent_id=agent_id,
            event_name=event_name,
            payload=payload,
            duration_ms=duration_ms,
            correlation_id=correlation_id,
        )
