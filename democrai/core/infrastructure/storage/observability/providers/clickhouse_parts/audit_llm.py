from __future__ import annotations

import json
from typing import Any, Optional

from democrai.core.infrastructure.storage.observability.models import AuditEventRecord, AIModelPipelineStepRecord, AIModelRuntimeEventRecord, AIModelUsageEventRecord
from democrai.core.platform.utils.timezone import utc_now_naive


class ClickHouseAuditLLMMixin:
    def record_audit_event(self, *, event_type: str, actor_user_id: Optional[int] = None, actor_role: Optional[str] = None, organization_id: Optional[int] = None, session_id: Optional[str] = None, node_id: Optional[str] = None, request_id: Optional[str] = None, correlation_id: Optional[str] = None, client_ip: Optional[str] = None, channel: Optional[str] = None, entity_type: Optional[str] = None, entity_id: Optional[str] = None, operation: Optional[str] = None, status: Optional[str] = None, before: Optional[dict] = None, after: Optional[dict] = None, metadata: Optional[dict] = None) -> AuditEventRecord:
        timestamp = utc_now_naive()
        before_json = json.dumps(before or {})
        after_json = json.dumps(after or {})
        metadata_json = json.dumps(metadata or {})
        self._client.insert(
            "audit_events",
            [[timestamp, event_type, actor_user_id, actor_role, organization_id, session_id, node_id, request_id, correlation_id, client_ip, channel, entity_type, entity_id, operation, status, before_json, after_json, metadata_json]],
            column_names=["timestamp", "event_type", "actor_user_id", "actor_role", "organization_id", "session_id", "node_id", "request_id", "correlation_id", "client_ip", "channel", "entity_type", "entity_id", "operation", "status", "before_json", "after_json", "metadata_json"],
        )
        return AuditEventRecord(
            id=None,
            timestamp=timestamp,
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
            before_json=before_json,
            after_json=after_json,
            metadata_json=metadata_json,
        )

    def get_audit_events(self, *, actor_user_id: Optional[int] = None, event_type: Optional[str] = None, entity_type: Optional[str] = None, entity_id: Optional[str] = None, limit: int = 100) -> list[AuditEventRecord]:
        params: dict[str, Any] = {"limit": limit}
        conditions: list[str] = []
        if actor_user_id is not None:
            conditions.append("actor_user_id = %(actor_user_id)s")
            params["actor_user_id"] = actor_user_id
        if event_type:
            conditions.append("event_type = %(event_type)s")
            params["event_type"] = event_type
        if entity_type:
            conditions.append("entity_type = %(entity_type)s")
            params["entity_type"] = entity_type
        if entity_id:
            conditions.append("entity_id = %(entity_id)s")
            params["entity_id"] = entity_id
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        result = self._client.query(
            f"""
            SELECT timestamp, event_type, actor_user_id, actor_role, organization_id,
                   session_id, node_id, request_id, correlation_id, client_ip, channel,
                   entity_type, entity_id, operation, status, before_json, after_json, metadata_json
            FROM audit_events
            {where}
            ORDER BY timestamp DESC
            LIMIT %(limit)s
            """,
            parameters=params,
        )
        return [
            AuditEventRecord(
                id=None,
                timestamp=row[0],
                event_type=row[1],
                actor_user_id=row[2],
                actor_role=row[3],
                organization_id=row[4],
                session_id=row[5],
                node_id=row[6],
                request_id=row[7],
                correlation_id=row[8],
                client_ip=row[9],
                channel=row[10],
                entity_type=row[11],
                entity_id=row[12],
                operation=row[13],
                status=row[14],
                before_json=row[15],
                after_json=row[16],
                metadata_json=row[17],
            )
            for row in result.result_rows
        ]

    def record_ai_model_usage(self, *, user_id: Optional[int] = None, organization_id: Optional[int] = None, session_id: Optional[str] = None, node_id: Optional[str] = None, request_id: Optional[str] = None, correlation_id: Optional[str] = None, client_ip: Optional[str] = None, channel: Optional[str] = None, objective: Optional[str] = None, provider: Optional[str] = None, engine: Optional[str] = None, engine_row_id: Optional[int] = None, model_name: Optional[str] = None, deployment_mode: Optional[str] = None, request_kind: Optional[str] = None, agent_id: Optional[str] = None, prompt_tokens: Optional[int] = None, completion_tokens: Optional[int] = None, total_tokens: Optional[int] = None, duration_ms: Optional[float] = None, tokens_per_second: Optional[float] = None, success: bool = True, error: Optional[str] = None, metadata: Optional[dict] = None) -> AIModelUsageEventRecord:
        timestamp = utc_now_naive()
        metadata_json = json.dumps(metadata or {})
        self._client.insert(
            "ai_model_usage_events",
            [[timestamp, user_id, organization_id, session_id, node_id, request_id, correlation_id, client_ip, channel, objective, provider, engine, engine_row_id, model_name, deployment_mode, request_kind, agent_id, prompt_tokens, completion_tokens, total_tokens, duration_ms, tokens_per_second, bool(success), error, metadata_json]],
            column_names=["timestamp", "user_id", "organization_id", "session_id", "node_id", "request_id", "correlation_id", "client_ip", "channel", "objective", "provider", "engine", "engine_row_id", "model_name", "deployment_mode", "request_kind", "agent_id", "prompt_tokens", "completion_tokens", "total_tokens", "duration_ms", "tokens_per_second", "success", "error", "metadata_json"],
        )
        return AIModelUsageEventRecord(
            id=None,
            timestamp=timestamp,
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
            metadata_json=metadata_json,
        )

    def get_ai_model_usage_events(self, *, user_id: Optional[int] = None, objective: Optional[str] = None, model_name: Optional[str] = None, limit: int = 100) -> list[AIModelUsageEventRecord]:
        params: dict[str, Any] = {"limit": limit}
        conditions: list[str] = []
        if user_id is not None:
            conditions.append("user_id = %(user_id)s")
            params["user_id"] = user_id
        if objective:
            conditions.append("objective = %(objective)s")
            params["objective"] = objective
        if model_name:
            conditions.append("model_name = %(model_name)s")
            params["model_name"] = model_name
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        result = self._client.query(
            f"""
            SELECT timestamp, user_id, organization_id, session_id, node_id, request_id,
                   correlation_id, client_ip, channel, objective, provider, engine, engine_row_id, model_name, deployment_mode,
                   request_kind, agent_id, prompt_tokens, completion_tokens, total_tokens,
                   duration_ms, tokens_per_second, success, error, metadata_json
            FROM ai_model_usage_events
            {where}
            ORDER BY timestamp DESC
            LIMIT %(limit)s
            """,
            parameters=params,
        )
        return [
            AIModelUsageEventRecord(
                id=None,
                timestamp=row[0],
                user_id=row[1],
                organization_id=row[2],
                session_id=row[3],
                node_id=row[4],
                request_id=row[5],
                correlation_id=row[6],
                client_ip=row[7],
                channel=row[8],
                objective=row[9],
                provider=row[10],
                engine=row[11],
                engine_row_id=row[12],
                model_name=row[13],
                deployment_mode=row[14],
                request_kind=row[15],
                agent_id=row[16],
                prompt_tokens=row[17],
                completion_tokens=row[18],
                total_tokens=row[19],
                duration_ms=row[20],
                tokens_per_second=row[21],
                success=bool(row[22]),
                error=row[23],
                metadata_json=row[24],
            )
            for row in result.result_rows
        ]

    def get_ai_model_usage_events_for_pipeline(self, *, pipeline_id: str, limit: int = 500) -> list[AIModelUsageEventRecord]:
        resolved_pipeline_id = pipeline_id.strip()
        if not resolved_pipeline_id:
            return []
        result = self._client.query(
            """
            SELECT timestamp, user_id, organization_id, session_id, node_id, request_id,
                   correlation_id, client_ip, channel, objective, provider, engine, engine_row_id, model_name, deployment_mode,
                   request_kind, agent_id, prompt_tokens, completion_tokens, total_tokens,
                   duration_ms, tokens_per_second, success, error, metadata_json
            FROM ai_model_usage_events
            WHERE JSONExtractString(metadata_json, 'pipeline_id') = %(pipeline_id)s
            ORDER BY timestamp ASC
            LIMIT %(limit)s
            """,
            parameters={"pipeline_id": resolved_pipeline_id, "limit": max(1, limit)},
        )
        return [
            AIModelUsageEventRecord(
                id=None,
                timestamp=row[0],
                user_id=row[1],
                organization_id=row[2],
                session_id=row[3],
                node_id=row[4],
                request_id=row[5],
                correlation_id=row[6],
                client_ip=row[7],
                channel=row[8],
                objective=row[9],
                provider=row[10],
                engine=row[11],
                engine_row_id=row[12],
                model_name=row[13],
                deployment_mode=row[14],
                request_kind=row[15],
                agent_id=row[16],
                prompt_tokens=row[17],
                completion_tokens=row[18],
                total_tokens=row[19],
                duration_ms=row[20],
                tokens_per_second=row[21],
                success=bool(row[22]),
                error=row[23],
                metadata_json=row[24],
            )
            for row in result.result_rows
        ]

    def sum_ai_model_usage_total_tokens(
        self,
        *,
        engine_row_id: int,
        started_at: Any,
        ended_at: Any,
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
        started_at: Any,
        ended_at: Any,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> int:
        params: dict[str, Any] = {
            "engine_row_id": int(engine_row_id),
            "started_at": started_at,
            "ended_at": ended_at,
        }
        conditions = [
            "engine_row_id = %(engine_row_id)s",
            "success = 1",
            "timestamp >= %(started_at)s",
            "timestamp < %(ended_at)s",
        ]
        if user_id is not None:
            conditions.append("user_id = %(user_id)s")
            params["user_id"] = int(user_id)
        if organization_id is not None:
            conditions.append("organization_id = %(organization_id)s")
            params["organization_id"] = int(organization_id)
        if session_id is not None:
            conditions.append("session_id = %(session_id)s")
            params["session_id"] = str(session_id)
        metric = str(metric_type)
        if metric == "total_tokens":
            expression = "coalesce(sum(coalesce(total_tokens, 0)), 0)"
        elif metric == "requests":
            expression = "count()"
        else:
            raise ValueError(f"ai_model_usage_metric_unsupported:{metric}")
        result = self._client.query(
            f"""
            SELECT {expression}
            FROM ai_model_usage_events
            WHERE {" AND ".join(conditions)}
            """,
            parameters=params,
        )
        if not result.result_rows:
            return 0
        return int(result.result_rows[0][0] or 0)

    def record_ai_model_runtime(self, **kwargs) -> AIModelRuntimeEventRecord:
        timestamp = utc_now_naive()
        metadata_json = json.dumps(kwargs.get("metadata") or {})
        values = [
            timestamp,
            kwargs.get("user_id"),
            kwargs.get("organization_id"),
            kwargs.get("session_id"),
            kwargs.get("request_id"),
            kwargs.get("correlation_id"),
            kwargs.get("client_ip"),
            kwargs.get("channel"),
            kwargs.get("event_type"),
            kwargs.get("provider"),
            kwargs.get("engine"),
            kwargs.get("engine_row_id"),
            kwargs.get("model_registry_id"),
            kwargs.get("model_name"),
            kwargs.get("node_id"),
            kwargs.get("config_signature"),
            kwargs.get("warmup_ms"),
            kwargs.get("model_weight_vram_mb"),
            kwargs.get("vram_before_mb"),
            kwargs.get("vram_after_mb"),
            kwargs.get("vram_delta_mb"),
            kwargs.get("runtime_allocated_vram_mb"),
            kwargs.get("ram_before_mb"),
            kwargs.get("ram_after_mb"),
            bool(kwargs.get("success", True)),
            kwargs.get("error"),
            metadata_json,
        ]
        self._client.insert(
            "ai_model_runtime_events",
            [values],
            column_names=[
                "timestamp", "user_id", "organization_id", "session_id",
                "request_id", "correlation_id", "client_ip", "channel",
                "event_type", "provider", "engine", "engine_row_id",
                "model_registry_id", "model_name", "node_id", "config_signature",
                "warmup_ms", "model_weight_vram_mb", "vram_before_mb",
                "vram_after_mb", "vram_delta_mb", "runtime_allocated_vram_mb",
                "ram_before_mb", "ram_after_mb", "success", "error",
                "metadata_json",
            ],
        )
        return AIModelRuntimeEventRecord(
            id=None,
            timestamp=timestamp,
            user_id=kwargs.get("user_id"),
            organization_id=kwargs.get("organization_id"),
            session_id=kwargs.get("session_id"),
            request_id=kwargs.get("request_id"),
            correlation_id=kwargs.get("correlation_id"),
            client_ip=kwargs.get("client_ip"),
            channel=kwargs.get("channel"),
            event_type=kwargs.get("event_type") or "",
            provider=kwargs.get("provider"),
            engine=kwargs.get("engine"),
            engine_row_id=kwargs.get("engine_row_id"),
            model_registry_id=kwargs.get("model_registry_id"),
            model_name=kwargs.get("model_name"),
            node_id=kwargs.get("node_id"),
            config_signature=kwargs.get("config_signature"),
            warmup_ms=kwargs.get("warmup_ms"),
            model_weight_vram_mb=kwargs.get("model_weight_vram_mb"),
            vram_before_mb=kwargs.get("vram_before_mb"),
            vram_after_mb=kwargs.get("vram_after_mb"),
            vram_delta_mb=kwargs.get("vram_delta_mb"),
            runtime_allocated_vram_mb=kwargs.get("runtime_allocated_vram_mb"),
            ram_before_mb=kwargs.get("ram_before_mb"),
            ram_after_mb=kwargs.get("ram_after_mb"),
            success=bool(kwargs.get("success", True)),
            error=kwargs.get("error"),
            metadata_json=metadata_json,
        )

    def record_ai_model_pipeline_step(self, **kwargs) -> AIModelPipelineStepRecord:
        timestamp = utc_now_naive()
        input_json = json.dumps(kwargs.get("input") or {})
        output_json = json.dumps(kwargs.get("output") or {})
        stats_json = json.dumps(kwargs.get("stats") or {})
        metadata_json = json.dumps(kwargs.get("metadata") or {})
        values = [
            timestamp,
            kwargs.get("pipeline_id"),
            kwargs.get("request_id"),
            kwargs.get("step_id"),
            kwargs.get("parent_step_id"),
            kwargs.get("root_method"),
            kwargs.get("type"),
            kwargs.get("name"),
            kwargs.get("status"),
            kwargs.get("started_at"),
            kwargs.get("duration_ms"),
            kwargs.get("provider"),
            kwargs.get("engine"),
            kwargs.get("engine_row_id"),
            kwargs.get("model_registry_id"),
            kwargs.get("model_name"),
            kwargs.get("user_id"),
            kwargs.get("organization_id"),
            kwargs.get("session_id"),
            kwargs.get("node_id"),
            input_json,
            output_json,
            stats_json,
            kwargs.get("error"),
            metadata_json,
            kwargs.get("input_hash"),
            kwargs.get("output_hash"),
            kwargs.get("input_size_bytes"),
            kwargs.get("output_size_bytes"),
            kwargs.get("archive_status") or "none",
            kwargs.get("archive_media_path"),
            kwargs.get("archive_error"),
        ]
        self._client.insert(
            "ai_model_pipeline_steps",
            [values],
            column_names=[
                "timestamp", "pipeline_id", "request_id", "step_id",
                "parent_step_id", "root_method", "type", "name", "status",
                "started_at", "duration_ms", "provider", "engine",
                "engine_row_id", "model_registry_id", "model_name", "user_id",
                "organization_id", "session_id", "node_id", "input_json",
                "output_json", "stats_json", "error", "metadata_json",
                "input_hash", "output_hash", "input_size_bytes", "output_size_bytes",
                "archive_status", "archive_media_path", "archive_error",
            ],
        )
        return AIModelPipelineStepRecord(
            id=None,
            timestamp=timestamp,
            pipeline_id=str(kwargs.get("pipeline_id") or ""),
            request_id=kwargs.get("request_id"),
            step_id=str(kwargs.get("step_id") or ""),
            parent_step_id=kwargs.get("parent_step_id"),
            root_method=str(kwargs.get("root_method") or ""),
            type=str(kwargs.get("type") or ""),
            name=str(kwargs.get("name") or ""),
            status=str(kwargs.get("status") or ""),
            started_at=kwargs.get("started_at"),
            duration_ms=kwargs.get("duration_ms"),
            provider=kwargs.get("provider"),
            engine=kwargs.get("engine"),
            engine_row_id=kwargs.get("engine_row_id"),
            model_registry_id=kwargs.get("model_registry_id"),
            model_name=kwargs.get("model_name"),
            user_id=kwargs.get("user_id"),
            organization_id=kwargs.get("organization_id"),
            session_id=kwargs.get("session_id"),
            node_id=kwargs.get("node_id"),
            input_json=input_json,
            output_json=output_json,
            stats_json=stats_json,
            error=kwargs.get("error"),
            metadata_json=metadata_json,
            input_hash=kwargs.get("input_hash"),
            output_hash=kwargs.get("output_hash"),
            input_size_bytes=kwargs.get("input_size_bytes"),
            output_size_bytes=kwargs.get("output_size_bytes"),
            archive_status=kwargs.get("archive_status") or "none",
            archive_media_path=kwargs.get("archive_media_path"),
            archive_error=kwargs.get("archive_error"),
        )
