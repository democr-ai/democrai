from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from democrai.core.infrastructure.storage.errors import ProviderConfigError, ProviderNotAvailableError


class ClickHouseCommonMixin:
    @staticmethod
    def _build_client(connection_url: str) -> Any:
        try:
            import clickhouse_connect
        except ImportError as exc:
            raise ProviderNotAvailableError(
                "ClickHouse observability provider requires clickhouse-connect"
            ) from exc

        parsed = urlparse(connection_url)
        if parsed.scheme not in {"clickhouse", "clickhouses"}:
            raise ProviderConfigError("ClickHouse connection_url must use clickhouse:// or clickhouses://")
        query = parse_qs(parsed.query)
        port = parsed.port if parsed.port is not None else (8443 if parsed.scheme == "clickhouses" else 8123)
        return clickhouse_connect.get_client(
            host=parsed.hostname or "localhost",
            port=port,
            username=parsed.username or "default",
            password=parsed.password or "",
            database=(parsed.path or "/default").lstrip("/") or "default",
            secure=parsed.scheme == "clickhouses",
            interface=query.get("interface", ["http"])[0],
        )

    @staticmethod
    def _resolve_database(connection_url: str) -> str:
        parsed = urlparse(connection_url)
        return (parsed.path or "/default").lstrip("/") or "default"

    def run_migrations(self) -> None:
        self._client.command(f"CREATE DATABASE IF NOT EXISTS {self.database}")
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS events (
                id UUID DEFAULT generateUUIDv4(),
                timestamp DateTime64(3) DEFAULT now64(3),
                level String,
                category String,
                user_id Nullable(Int64),
                session_id Nullable(String),
                agent_id Nullable(String),
                event_name String,
                payload String,
                duration_ms Nullable(Float64),
                correlation_id String
            )
            ENGINE = MergeTree
            ORDER BY (timestamp, correlation_id)
            """
        )
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id UUID DEFAULT generateUUIDv4(),
                timestamp DateTime64(3) DEFAULT now64(3),
                event_type String,
                actor_user_id Nullable(Int64),
                actor_role Nullable(String),
                organization_id Nullable(Int64),
                session_id Nullable(String),
                node_id Nullable(String),
                request_id Nullable(String),
                correlation_id Nullable(String),
                client_ip Nullable(String),
                channel Nullable(String),
                entity_type Nullable(String),
                entity_id Nullable(String),
                operation Nullable(String),
                status Nullable(String),
                before_json String,
                after_json String,
                metadata_json String
            )
            ENGINE = MergeTree
            ORDER BY (timestamp, event_type, correlation_id)
            """
        )
        self._client.command(
            "ALTER TABLE audit_events ADD COLUMN IF NOT EXISTS node_id Nullable(String) AFTER session_id"
        )
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS ai_model_usage_events (
                id UUID DEFAULT generateUUIDv4(),
                timestamp DateTime64(3) DEFAULT now64(3),
                user_id Nullable(Int64),
                organization_id Nullable(Int64),
                session_id Nullable(String),
                request_id Nullable(String),
                correlation_id Nullable(String),
                client_ip Nullable(String),
                channel Nullable(String),
                objective Nullable(String),
                provider Nullable(String),
                engine Nullable(String),
                engine_row_id Nullable(Int64),
                model_name Nullable(String),
                deployment_mode Nullable(String),
                request_kind Nullable(String),
                agent_id Nullable(String),
                prompt_tokens Nullable(Int32),
                completion_tokens Nullable(Int32),
                total_tokens Nullable(Int32),
                duration_ms Nullable(Float64),
                tokens_per_second Nullable(Float64),
                success Bool,
                error Nullable(String),
                metadata_json String
            )
            ENGINE = MergeTree
            ORDER BY (timestamp, model_name, correlation_id)
            """
        )
        self._client.command(
            "ALTER TABLE ai_model_usage_events ADD COLUMN IF NOT EXISTS node_id Nullable(String) AFTER session_id"
        )
        self._client.command(
            "ALTER TABLE ai_model_usage_events ADD COLUMN IF NOT EXISTS engine_row_id Nullable(Int64) AFTER engine"
        )
        self._client.command(
            "ALTER TABLE ai_model_usage_events ADD COLUMN IF NOT EXISTS tokens_per_second Nullable(Float64) AFTER duration_ms"
        )
        self._client.command(
            "ALTER TABLE ai_model_usage_events MODIFY COLUMN IF EXISTS success Bool"
        )
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS ai_model_runtime_events (
                id UUID DEFAULT generateUUIDv4(),
                timestamp DateTime64(3) DEFAULT now64(3),
                user_id Nullable(Int64),
                organization_id Nullable(Int64),
                session_id Nullable(String),
                request_id Nullable(String),
                correlation_id Nullable(String),
                client_ip Nullable(String),
                channel Nullable(String),
                event_type String,
                provider Nullable(String),
                engine Nullable(String),
                engine_row_id Nullable(Int64),
                model_registry_id Nullable(Int64),
                model_name Nullable(String),
                node_id Nullable(String),
                config_signature Nullable(String),
                warmup_ms Nullable(Float64),
                model_weight_vram_mb Nullable(Int32),
                vram_before_mb Nullable(Int32),
                vram_after_mb Nullable(Int32),
                vram_delta_mb Nullable(Int32),
                runtime_allocated_vram_mb Nullable(Int32),
                ram_before_mb Nullable(Int32),
                ram_after_mb Nullable(Int32),
                success Bool,
                error Nullable(String),
                metadata_json String
            )
            ENGINE = MergeTree
            ORDER BY (timestamp, model_name, correlation_id)
            """
        )
        self._client.command(
            "ALTER TABLE ai_model_runtime_events MODIFY COLUMN IF EXISTS success Bool"
        )
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS ai_model_pipeline_steps (
                id UUID DEFAULT generateUUIDv4(),
                timestamp DateTime64(3) DEFAULT now64(3),
                pipeline_id String,
                request_id Nullable(String),
                step_id String,
                parent_step_id Nullable(String),
                root_method String,
                type String,
                name String,
                status String,
                started_at Nullable(DateTime64(3)),
                duration_ms Nullable(Float64),
                provider Nullable(String),
                engine Nullable(String),
                engine_row_id Nullable(Int64),
                model_registry_id Nullable(Int64),
                model_name Nullable(String),
                user_id Nullable(Int64),
                organization_id Nullable(Int64),
                session_id Nullable(String),
                node_id Nullable(String),
                input_json String,
                output_json String,
                stats_json String,
                error Nullable(String),
                metadata_json String,
                input_hash Nullable(String),
                output_hash Nullable(String),
                input_size_bytes Nullable(Int64),
                output_size_bytes Nullable(Int64),
                archive_status String DEFAULT 'none',
                archive_media_path Nullable(String),
                archive_error Nullable(String)
            )
            ENGINE = MergeTree
            ORDER BY (timestamp, pipeline_id, step_id)
            """
        )
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS input_hash Nullable(String)")
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS output_hash Nullable(String)")
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS input_size_bytes Nullable(Int64)")
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS output_size_bytes Nullable(Int64)")
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS archive_status String DEFAULT 'none'")
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS archive_media_path Nullable(String)")
        self._client.command("ALTER TABLE ai_model_pipeline_steps ADD COLUMN IF NOT EXISTS archive_error Nullable(String)")
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS obs_trace_archive_queue (
                id String,
                timestamp DateTime64(3) DEFAULT now64(3),
                pipeline_step_db_id Nullable(Int64),
                pipeline_id String,
                request_id Nullable(String),
                step_id String,
                payload_kind String,
                status String,
                attempts Int32,
                locked_by Nullable(String),
                locked_at Nullable(DateTime64(3)),
                next_attempt_at Nullable(DateTime64(3)),
                archived_media_path Nullable(String),
                payload_hash Nullable(String),
                last_error Nullable(String),
                payload_json String
            )
            ENGINE = ReplacingMergeTree
            ORDER BY (id, timestamp)
            """
        )
        self._client.command(
            """
            CREATE TABLE IF NOT EXISTS obs_export_outbox (
                id String,
                timestamp DateTime64(3) DEFAULT now64(3),
                event_kind String,
                correlation_id Nullable(String),
                source_node_id Nullable(String),
                dedupe_key Nullable(String),
                status String,
                attempts Int32,
                next_attempt_at Nullable(DateTime64(3)),
                exported_at Nullable(DateTime64(3)),
                last_error Nullable(String),
                payload_json String
            )
            ENGINE = ReplacingMergeTree
            ORDER BY (id, timestamp)
            """
        )
