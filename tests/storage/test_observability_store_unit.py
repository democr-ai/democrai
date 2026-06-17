from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from democrai.core.infrastructure.storage.errors import ProviderConfigError
from democrai.core.infrastructure.storage.errors import ProviderNotAvailableError
from democrai.core.infrastructure.storage.observability.factory import ObservabilityFactory
from democrai.core.infrastructure.storage.observability.exporters.otlp import OtlpObsExporter
from democrai.core.infrastructure.storage.observability.models import AuditEventRecord
from democrai.core.infrastructure.storage.observability.models import EventRecord
from democrai.core.infrastructure.storage.observability.models import AIModelUsageEventRecord
from democrai.core.infrastructure.storage.observability.models_records import ExportOutboxRecord
from democrai.core.infrastructure.storage.observability.providers.clickhouse import (
    ClickHouseObsStorage,
)
from democrai.core.infrastructure.storage.observability.providers.postgres import PostgresObsStorage
from democrai.core.infrastructure.storage.observability.providers.sqlite import SqliteObsStorage
from democrai.core.infrastructure.storage.observability.store import ObservabilityStore


class _Provider:
    def __init__(self):
        self.calls = []

    def record_event(self, **kwargs):
        self.calls.append(("record_event", kwargs))
        return EventRecord(
            id=1,
            timestamp=datetime(2026, 1, 15, 12, 0, 0),
            level=kwargs["level"],
            category=kwargs["category"],
            user_id=kwargs["user_id"],
            session_id=kwargs["session_id"],
            agent_id=kwargs["agent_id"],
            event_name=kwargs["event_name"],
            payload="{}",
            duration_ms=kwargs["duration_ms"],
            correlation_id=kwargs["correlation_id"],
        )

    def get_events(self, **kwargs):
        self.calls.append(("get_events", kwargs))
        return []

    def get_flow(self, correlation_id):
        self.calls.append(("get_flow", correlation_id))
        return []

    def record_audit_event(self, **kwargs):
        self.calls.append(("record_audit_event", kwargs))
        return AuditEventRecord(
            id=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 1),
            event_type=kwargs["event_type"],
            actor_user_id=kwargs.get("actor_user_id"),
            actor_role=kwargs.get("actor_role"),
            organization_id=kwargs.get("organization_id"),
            session_id=kwargs.get("session_id"),
            node_id=kwargs.get("node_id"),
            request_id=kwargs.get("request_id"),
            correlation_id=kwargs["correlation_id"],
            client_ip=kwargs.get("client_ip"),
            channel=kwargs.get("channel"),
            entity_type=kwargs.get("entity_type"),
            entity_id=kwargs.get("entity_id"),
            operation=kwargs["operation"],
            status=kwargs["status"],
            before_json="{}",
            after_json="{}",
            metadata_json="{}",
        )

    def get_audit_events(self, **kwargs):
        self.calls.append(("get_audit_events", kwargs))
        return []

    def record_ai_model_usage(self, **kwargs):
        self.calls.append(("record_ai_model_usage", kwargs))
        return AIModelUsageEventRecord(
            id=3,
            timestamp=datetime(2026, 1, 15, 12, 0, 2),
            user_id=kwargs.get("user_id"),
            organization_id=kwargs.get("organization_id"),
            session_id=kwargs.get("session_id"),
            node_id=kwargs.get("node_id"),
            request_id=kwargs.get("request_id"),
            correlation_id=kwargs["correlation_id"],
            client_ip=kwargs.get("client_ip"),
            channel=kwargs.get("channel"),
            objective=kwargs.get("objective"),
            provider=kwargs.get("provider"),
            engine=kwargs.get("engine"),
            engine_row_id=kwargs.get("engine_row_id"),
            model_name=kwargs.get("model_name"),
            deployment_mode=kwargs.get("deployment_mode"),
            request_kind=kwargs["request_kind"],
            agent_id=kwargs.get("agent_id"),
            prompt_tokens=kwargs.get("prompt_tokens"),
            completion_tokens=kwargs.get("completion_tokens"),
            total_tokens=kwargs.get("total_tokens"),
            duration_ms=kwargs.get("duration_ms"),
            tokens_per_second=kwargs.get("tokens_per_second"),
            success=kwargs["success"],
            error=kwargs.get("error"),
            metadata_json="{}",
        )

    def get_ai_model_usage_events(self, **kwargs):
        self.calls.append(("get_ai_model_usage_events", kwargs))
        return []

    def run_migrations(self):
        self.calls.append(("run_migrations", None))

    def enqueue_export_outbox(self, **kwargs):
        self.calls.append(("enqueue_export_outbox", kwargs))
        return SimpleNamespace(id="outbox-1", to_dict=lambda: {"payload": kwargs.get("payload", {})})

    def get_export_outbox_ready(self, **kwargs):
        self.calls.append(("get_export_outbox_ready", kwargs))
        return []

    def mark_export_outbox_exported(self, outbox_id):
        self.calls.append(("mark_export_outbox_exported", outbox_id))

    def mark_export_outbox_failed(self, outbox_id, **kwargs):
        self.calls.append(("mark_export_outbox_failed", (outbox_id, kwargs)))

    def cleanup_older_than(self, **kwargs):
        self.calls.append(("cleanup_older_than", kwargs))
        return {"events": 0, "audit_events": 0, "ai_model_usage_events": 0, "obs_export_outbox": 0}


class _Exporter:
    def __init__(self):
        self.payloads = []

    def export(self, event_payload: dict) -> None:
        self.payloads.append(event_payload)


def test_observability_store_exports_after_persist():
    provider = _Provider()
    exporter = _Exporter()
    store = ObservabilityStore(provider=provider, exporters=[exporter])

    store.record_event(
        event_name="tool_call",
        category="agent",
        correlation_id="corr-1",
        level="INFO",
        user_id="u1",
        payload={"tool": "search"},
    )

    assert provider.calls[0][0] == "record_event"
    assert provider.calls[1][0] == "enqueue_export_outbox"
    assert provider.calls[2][0] == "mark_export_outbox_exported"
    assert exporter.payloads[0]["event"] == "tool_call"
    assert exporter.payloads[0]["category"] == "agent"


def test_observability_store_supports_audit_and_ai_model_usage_records():
    provider = _Provider()
    store = ObservabilityStore(provider=provider, exporters=[])

    audit = store.record_audit_event(
        event_type="auth.login.succeeded",
        correlation_id="corr-audit",
        operation="login",
        status="success",
        actor_user_id="u1",
        entity_type="auth_session",
        entity_id="u1",
        before={},
        after={},
        metadata={},
    )
    ai_usage = store.record_ai_model_usage(
        correlation_id="corr-llm",
        request_kind="completion",
        success=True,
        objective="chat",
        provider="openai",
        engine="openai",
        model_name="gpt-test",
        metadata={},
    )

    assert audit.event_type == "auth.login.succeeded"
    assert ai_usage.model_name == "gpt-test"
    assert provider.calls[0][0] == "record_audit_event"
    assert provider.calls[1][0] == "record_ai_model_usage"


def test_observability_store_retention_and_outbox_flush():
    provider = _Provider()
    exporter = _Exporter()
    store = ObservabilityStore(provider=provider, exporters=[exporter])
    provider.get_export_outbox_ready = lambda **kwargs: [
        SimpleNamespace(id="outbox-1", to_dict=lambda: {"payload": {"event": "ok"}})
    ]

    flush = store.flush_export_outbox(limit=5)
    cleanup = store.apply_retention(
        events_days=1,
        audit_days=2,
        ai_model_usage_days=3,
        export_outbox_days=4,
    )

    assert flush == {"processed": 1, "exported": 1, "failed": 0}
    assert cleanup["events"] == 0


def test_observability_store_handles_outbox_failure_and_no_exporters():
    provider = _Provider()

    class _FailExporter:
        def export(self, _payload):
            raise RuntimeError("down")

    store_with_fail = ObservabilityStore(provider=provider, exporters=[_FailExporter()])
    store_no_exporters = ObservabilityStore(provider=provider, exporters=[])

    provider.get_export_outbox_ready = lambda **kwargs: [
        SimpleNamespace(id="outbox-1", to_dict=lambda: {"payload": {"event": "x"}})
    ]
    result = store_with_fail.flush_export_outbox(limit=1)
    assert result == {"processed": 1, "exported": 0, "failed": 1}

    assert store_no_exporters.flush_export_outbox(limit=1) == {
        "processed": 0,
        "exported": 0,
        "failed": 0,
    }
    store_no_exporters.run_migrations()


def test_observability_store_marks_failed_when_direct_export_dispatch_fails():
    provider = _Provider()

    class _FailExporter:
        def export(self, _payload):
            raise RuntimeError("dispatch failed")

    store = ObservabilityStore(provider=provider, exporters=[_FailExporter()])
    store.record_event(
        event_name="evt",
        category="system",
        correlation_id="corr-x",
        payload={"ok": True},
    )

    assert any(call[0] == "mark_export_outbox_failed" for call in provider.calls)


def test_observability_store_serializers_and_provider_url_selection(monkeypatch, tmp_path):
    provider = _Provider()
    store = ObservabilityStore(provider=provider, exporters=[])
    provider.get_events = lambda **kwargs: [
        EventRecord(
            id=1,
            timestamp=datetime(2026, 1, 15, 12, 0, 0),
            level="INFO",
            category="system",
            user_id="u1",
            session_id="s1",
            agent_id=None,
            event_name="evt",
            payload="{}",
            duration_ms=None,
            correlation_id="corr-1",
        )
    ]
    provider.get_audit_events = lambda **kwargs: [
        AuditEventRecord(
            id=2,
            timestamp=datetime(2026, 1, 15, 12, 0, 1),
            event_type="db_update",
            actor_user_id="u1",
            actor_role="admin",
            organization_id="org-1",
            session_id="s1",
            node_id="n1",
            request_id="r1",
            correlation_id="corr-2",
            client_ip="127.0.0.1",
            channel="http",
            entity_type="demo",
            entity_id="1",
            operation="update",
            status="success",
            before_json="{}",
            after_json="{}",
            metadata_json="{}",
        )
    ]
    provider.get_ai_model_usage_events = lambda **kwargs: [
        AIModelUsageEventRecord(
            id=3,
            timestamp=datetime(2026, 1, 15, 12, 0, 2),
            user_id="u1",
            organization_id="org-1",
            session_id="s1",
            node_id="n1",
            request_id="r1",
            correlation_id="corr-3",
            client_ip="127.0.0.1",
            channel="http",
            objective="chat",
            provider="openai",
            engine="openai",
            engine_row_id=11,
            model_name="gpt-test",
            deployment_mode="cloud",
            request_kind="completion",
            agent_id=None,
            prompt_tokens=1,
            completion_tokens=2,
            total_tokens=3,
            duration_ms=4.5,
            tokens_per_second=12.5,
            success=True,
            error=None,
            metadata_json="{}",
        )
    ]
    assert store.get_events_serialized()[0]["event"] == "evt"
    assert store.get_flow_serialized("corr-1") == []
    assert store.get_audit_events_serialized()[0]["event_type"] == "db_update"
    assert store.get_ai_model_usage_events_serialized()[0]["model_name"] == "gpt-test"

    sqlite_store = ObservabilityStore(db_url=f"sqlite:///{tmp_path}/obs.db")
    assert isinstance(sqlite_store.provider, SqliteObsStorage)
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.store.PostgresObsStorage",
        lambda url: ("pg", url),
    )
    assert ObservabilityStore._provider_from_url("postgresql://demo") == ("pg", "postgresql://demo")


def test_clickhouse_provider_builds_expected_queries(monkeypatch: pytest.MonkeyPatch):
    commands = []
    inserts = []
    queries = []

    class _Client:
        def command(self, sql, parameters=None):
            commands.append((sql, parameters))

        def insert(self, table, rows, column_names):
            inserts.append((table, rows, column_names))

        def query(self, sql, parameters=None):
            queries.append((sql, parameters))
            if "FROM obs_export_outbox" in sql and "WHERE dedupe_key" in sql:
                return SimpleNamespace(result_rows=[])
            if "FROM obs_export_outbox" in sql and "WHERE id" in sql:
                return SimpleNamespace(
                    result_rows=[("outbox-1", "event", "corr-1", "node-a", "dedupe-1", 0, "{}")]
                )
            if "FROM obs_export_outbox" in sql:
                return SimpleNamespace(
                    result_rows=[
                        (
                            "outbox-1",
                            datetime(2026, 1, 15, 12, 0, 3),
                            "event",
                            "corr-1",
                            "node-a",
                            "dedupe-1",
                            "pending",
                            0,
                            datetime(2026, 1, 15, 12, 0, 3),
                            None,
                            None,
                            "{}",
                        )
                    ]
                )
            if "FROM audit_events" in sql:
                return SimpleNamespace(
                    result_rows=[
                        (
                            datetime(2026, 1, 15, 12, 0, 1),
                            "db_update",
                            "u1",
                            "admin",
                            "org-1",
                            "s1",
                            "node-a",
                            "r1",
                            "corr-audit",
                            "127.0.0.1",
                            "http",
                            "demo",
                            "1",
                            "update",
                            "success",
                            "{}",
                            "{}",
                            "{}",
                        )
                    ]
                )
            if "FROM ai_model_usage_events" in sql:
                return SimpleNamespace(
                    result_rows=[
                        (
                            datetime(2026, 1, 15, 12, 0, 2),
                            "u1",
                            "org-1",
                            "s1",
                            "node-a",
                            "r1",
                            "corr-llm",
                            "127.0.0.1",
                            "http",
                            "chat",
                            "openai",
                            "openai",
                            None,
                            "gpt-test",
                            "cloud",
                            "completion",
                            None,
                            1,
                            2,
                            3,
                            4.5,
                            25.0,
                            True,
                            None,
                            "{}",
                        )
                    ]
                )
            return SimpleNamespace(
                result_rows=[
                    (
                        datetime(2026, 1, 15, 12, 0, 0),
                        "INFO",
                        "system",
                        "u1",
                        None,
                        None,
                        "tool_call",
                        "{}",
                        12.5,
                        "corr-1",
                    )
                ]
            )

    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.providers.clickhouse.ClickHouseObsStorage._build_client",
        staticmethod(lambda _url: _Client()),
    )

    provider = ClickHouseObsStorage("clickhouse://default:pw@localhost:8123/democrai_obs")
    provider.run_migrations()
    record = provider.record_event(
        event_name="tool_call",
        category="system",
        correlation_id="corr-1",
        user_id="u1",
        payload={"ok": True},
        duration_ms=12.5,
    )
    events = provider.get_events(user_id="u1", limit=5)
    flow = provider.get_flow("corr-1")
    audit = provider.record_audit_event(
        event_type="db_update",
        correlation_id="corr-audit",
        actor_user_id="u1",
        actor_role="admin",
        organization_id="org-1",
        session_id="s1",
        request_id="r1",
        client_ip="127.0.0.1",
        channel="http",
        entity_type="demo",
        entity_id="1",
        operation="update",
        status="success",
        before={},
        after={},
        metadata={},
    )
    audit_events = provider.get_audit_events(
        actor_user_id="u1",
        event_type="db_update",
        entity_type="demo",
        entity_id="1",
        limit=2,
    )
    ai_usage = provider.record_ai_model_usage(
        correlation_id="corr-llm",
        user_id="u1",
        organization_id="org-1",
        session_id="s1",
        request_id="r1",
        client_ip="127.0.0.1",
        channel="http",
        objective="chat",
        provider="openai",
        engine="openai",
        model_name="gpt-test",
        deployment_mode="cloud",
        request_kind="completion",
        prompt_tokens=1,
        completion_tokens=2,
        total_tokens=3,
        duration_ms=4.5,
        success=True,
        metadata={},
    )
    llm_events = provider.get_ai_model_usage_events(
        user_id="u1",
        objective="chat",
        model_name="gpt-test",
        limit=3,
    )
    outbox = provider.enqueue_export_outbox(
        event_kind="event",
        payload={"event": "tool_call"},
        correlation_id="corr-1",
        source_node_id="node-a",
        dedupe_key="dedupe-1",
    )
    ready = provider.get_export_outbox_ready(limit=2)
    provider.mark_export_outbox_failed(outbox.id, error="retry")
    provider.mark_export_outbox_exported(outbox.id)
    cleanup_stats = provider.cleanup_older_than(
        events_before=datetime(2026, 1, 1, 0, 0, 0),
        audit_events_before=datetime(2026, 1, 1, 0, 0, 0),
        ai_model_usage_before=datetime(2026, 1, 1, 0, 0, 0),
        export_outbox_before=datetime(2026, 1, 1, 0, 0, 0),
    )

    assert "CREATE DATABASE IF NOT EXISTS democrai_obs" in commands[0][0]
    assert inserts[0][0] == "events"
    assert inserts[1][0] == "audit_events"
    assert inserts[2][0] == "ai_model_usage_events"
    assert inserts[3][0] == "obs_export_outbox"
    assert record.correlation_id == "corr-1"
    assert events[0].user_id == "u1"
    assert flow[0].event_name == "tool_call"
    assert audit.entity_id == "1"
    assert audit_events[0].event_type == "db_update"
    assert ai_usage.model_name == "gpt-test"
    assert llm_events[0].provider == "openai"
    assert ready[0].id == "outbox-1"
    assert cleanup_stats["events"] == 0
    assert queries[0][1]["limit"] == 5
    assert queries[2][1]["entity_id"] == "1"
    assert queries[3][1]["model_name"] == "gpt-test"


def test_clickhouse_outbox_dedupe_and_missing_rows(monkeypatch: pytest.MonkeyPatch):
    commands = []
    inserts = []

    class _Client:
        def command(self, sql, parameters=None):
            commands.append((sql, parameters))

        def insert(self, table, rows, column_names):
            inserts.append((table, rows, column_names))

        def query(self, sql, parameters=None):
            if "WHERE dedupe_key" in sql:
                return SimpleNamespace(
                    result_rows=[
                        (
                            "outbox-x",
                            datetime(2026, 1, 15, 12, 0, 0),
                            "event",
                            "corr-1",
                            "node-a",
                            "dedupe-1",
                            "pending",
                            0,
                            datetime(2026, 1, 15, 12, 0, 0),
                            None,
                            None,
                            "{}",
                        )
                    ]
                )
            if "WHERE id" in sql:
                return SimpleNamespace(result_rows=[])
            return SimpleNamespace(result_rows=[])

    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.providers.clickhouse.ClickHouseObsStorage._build_client",
        staticmethod(lambda _url: _Client()),
    )
    provider = ClickHouseObsStorage("clickhouse://default:pw@localhost:8123/democrai_obs")

    deduped = provider.enqueue_export_outbox(
        event_kind="event",
        payload={"event": "x"},
        correlation_id="corr-1",
        source_node_id="node-a",
        dedupe_key="dedupe-1",
    )
    assert deduped.id == "outbox-x"
    assert inserts == []

    inserted = provider.enqueue_export_outbox(
        event_kind="event",
        payload={"event": "y"},
        correlation_id="corr-2",
        source_node_id="node-b",
        dedupe_key=None,
    )
    assert inserted.id
    assert inserts and inserts[-1][0] == "obs_export_outbox"

    provider.mark_export_outbox_failed("missing", error="boom")
    provider.mark_export_outbox_exported("missing")
    cleanup = provider.cleanup_older_than()
    assert cleanup["obs_export_outbox"] == 0
    assert commands == []


def test_observability_factory_rejects_missing_otlp_endpoint():
    with pytest.raises(ProviderConfigError):
        ObservabilityFactory.get_provider("sqlite", otlp_enabled=True)


def test_sqlite_provider_defaults_data_dir_path(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.providers.sqlite.get_data_dir",
        lambda: str(tmp_path),
    )
    provider = SqliteObsStorage()
    assert provider.db_path.endswith("observability.db")


def test_observability_relational_providers_and_otlp_exporter(monkeypatch: pytest.MonkeyPatch, tmp_path):
    sqlite_provider = SqliteObsStorage(str(tmp_path / "obs.db"))
    sqlite_provider.run_migrations()
    sqlite_provider.record_event(
        event_name="saved",
        category="ui",
        correlation_id="corr-2",
        level="WARN",
        user_id="u2",
        payload={"count": 2},
    )
    assert sqlite_provider.get_events(user_id="u2")[0].event_name == "saved"
    assert sqlite_provider.get_flow("corr-2")[0].correlation_id == "corr-2"
    sqlite_provider.record_audit_event(
        event_type="db_update",
        correlation_id="corr-audit",
        operation="update",
        status="success",
        actor_user_id="u2",
        entity_type="data_entry",
        entity_id="1",
        before={"old": 1},
        after={"new": 2},
        metadata={"source": "test"},
    )
    sqlite_provider.record_ai_model_usage(
        correlation_id="corr-llm",
        request_kind="completion",
        success=True,
        user_id="u2",
        objective="chat",
        provider="openai",
        engine="openai",
        model_name="gpt-test",
        metadata={"source": "test"},
    )
    assert sqlite_provider.get_audit_events(
        actor_user_id="u2",
        event_type="db_update",
        entity_type="data_entry",
        entity_id="1",
    )[0].entity_id == "1"
    assert sqlite_provider.get_ai_model_usage_events(
        user_id="u2",
        objective="chat",
        model_name="gpt-test",
    )[0].provider == "openai"
    sqlite_outbox = sqlite_provider.enqueue_export_outbox(
        event_kind="event",
        payload={"event": "saved"},
        correlation_id="corr-2",
        dedupe_key="dedupe-1",
    )
    assert sqlite_provider.enqueue_export_outbox(
        event_kind="event",
        payload={"event": "saved"},
        correlation_id="corr-2",
        dedupe_key="dedupe-1",
    ).id == sqlite_outbox.id
    assert sqlite_provider.get_export_outbox_ready(limit=10)[0].id == sqlite_outbox.id
    sqlite_provider.mark_export_outbox_failed(sqlite_outbox.id, error="temporary")
    sqlite_provider.mark_export_outbox_exported(sqlite_outbox.id)
    sqlite_provider.mark_export_outbox_exported("missing")
    sqlite_provider.mark_export_outbox_failed("missing", error="missing")
    assert sqlite_provider.cleanup_older_than() == {
            "events": 0,
            "audit_events": 0,
            "ai_model_usage_events": 0,
            "ai_model_runtime_events": 0,
            "obs_export_outbox": 0,
            "obs_trace_archive_queue": 0,
        }
    sqlite_cleanup = sqlite_provider.cleanup_older_than(export_outbox_before=datetime.max)
    assert "obs_export_outbox" in sqlite_cleanup

    engine = create_engine("sqlite:///:memory:")
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.providers.postgres.create_engine",
        lambda url: engine,
    )
    monkeypatch.setattr(
        "democrai.core.infrastructure.storage.observability.providers.postgres.sessionmaker",
        lambda **kwargs: SessionLocal,
    )
    postgres_provider = PostgresObsStorage("postgresql://demo")
    postgres_provider.run_migrations()
    record = postgres_provider.record_event(
        event_name="loaded",
        category="agent",
        correlation_id="corr-3",
        session_id="s1",
        agent_id="a1",
        payload={"ok": True},
        duration_ms=1.5,
    )
    assert record.event_name == "loaded"
    assert postgres_provider.get_events(category="agent", correlation_id="corr-3")[0].agent_id == "a1"
    assert postgres_provider.get_flow("corr-3")[0].session_id == "s1"
    postgres_provider.record_audit_event(
        event_type="db_insert",
        correlation_id="corr-4",
        operation="insert",
        status="success",
        actor_user_id="u3",
        entity_type="knowledge_item",
        entity_id="k1",
        before={},
        after={"id": "k1"},
        metadata={},
    )
    postgres_provider.record_ai_model_usage(
        correlation_id="corr-5",
        request_kind="agent_completion",
        success=False,
        user_id="u3",
        objective="agent",
        provider="ollama",
        engine="ollama",
        model_name="llama",
        error="boom",
        metadata={},
    )
    assert postgres_provider.get_audit_events(
        actor_user_id="u3",
        event_type="db_insert",
        entity_type="knowledge_item",
        entity_id="k1",
    )[0].entity_id == "k1"
    assert postgres_provider.get_ai_model_usage_events(
        user_id="u3",
        objective="agent",
        model_name="llama",
    )[0].error == "boom"
    postgres_outbox = postgres_provider.enqueue_export_outbox(
        event_kind="ai_model_usage",
        payload={"event": "llm"},
        dedupe_key="dedupe-pg",
    )
    assert postgres_provider.get_export_outbox_ready(limit=10)[0].id == postgres_outbox.id
    postgres_provider.mark_export_outbox_failed(postgres_outbox.id, error="retry")
    postgres_provider.mark_export_outbox_exported(postgres_outbox.id)
    postgres_provider.mark_export_outbox_exported("missing")
    postgres_provider.mark_export_outbox_failed("missing", error="missing")
    assert postgres_provider.cleanup_older_than() == {
            "events": 0,
            "audit_events": 0,
            "ai_model_usage_events": 0,
            "ai_model_runtime_events": 0,
            "obs_export_outbox": 0,
            "obs_trace_archive_queue": 0,
        }
    deep_cleanup = postgres_provider.cleanup_older_than(
        events_before=datetime.max,
        audit_events_before=datetime.max,
        ai_model_usage_before=datetime.max,
    )
    assert set(deep_cleanup) == {
        "events",
        "audit_events",
        "ai_model_usage_events",
        "ai_model_runtime_events",
        "obs_export_outbox",
        "obs_trace_archive_queue",
    }
    postgres_cleanup = postgres_provider.cleanup_older_than(export_outbox_before=datetime.max)
    assert "obs_export_outbox" in postgres_cleanup

    sqlite_columns = {
        column["name"]
        for column in inspect(sqlite_provider.engine).get_columns("audit_events")
    }
    assert {"before_json", "after_json", "metadata_json"}.issubset(sqlite_columns)

    llm_columns = {
        column["name"]
        for column in inspect(sqlite_provider.engine).get_columns("ai_model_usage_events")
    }
    assert "metadata_json" in llm_columns
    outbox_columns = {
        column["name"]
        for column in inspect(sqlite_provider.engine).get_columns("obs_export_outbox")
    }
    assert {"status", "attempts", "payload_json"}.issubset(outbox_columns)


def test_export_outbox_record_to_dict_payload_fallback(monkeypatch: pytest.MonkeyPatch):
    record = ExportOutboxRecord(
        id="o1",
        timestamp=datetime(2026, 1, 15, 12, 0, 0),
        event_kind="event",
        correlation_id="c1",
        source_node_id="n1",
        dedupe_key="d1",
        status="pending",
        attempts=1,
        next_attempt_at=None,
        exported_at=None,
        last_error=None,
        payload_json="",
    )
    payload = record.to_dict()
    assert payload["id"] == "o1"
    assert payload["payload"] == {}

    real_import = __import__

    def _raising_import(name, *args, **kwargs):
        if name.startswith("opentelemetry"):
            raise ImportError("missing opentelemetry")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _raising_import)
    with pytest.raises(ProviderNotAvailableError):
        OtlpObsExporter._build_exporter(endpoint="http://collector", insecure=True, service_name="demo")

    span_attrs = {}

    class _Span:
        def set_attribute(self, key, value):
            span_attrs[key] = value

    class _Ctx:
        def __enter__(self):
            return _Span()

        def __exit__(self, exc_type, exc, tb):
            return False

    exporter = OtlpObsExporter.__new__(OtlpObsExporter)
    exporter._span_context_manager = lambda name: _Ctx()
    exporter.export(
        {
            "category": "agent",
            "event": "tool_call",
            "level": "INFO",
            "correlation_id": "corr-9",
            "user_id": "u9",
            "payload": {"ok": True, "count": 3, "ignored": {"nested": True}},
        }
    )


def test_clickhouse_audit_llm_mixin_filter_branches():
    from democrai.core.infrastructure.storage.observability.providers.clickhouse_parts.audit_llm import (
        ClickHouseAuditLLMMixin,
    )

    queries = []

    class _Client:
        def query(self, sql, parameters=None):
            queries.append((sql, parameters))
            if "FROM audit_events" in sql:
                return SimpleNamespace(
                    result_rows=[
                        (
                            datetime(2026, 1, 1, 0, 0, 0),
                            "audit",
                            1,
                                "admin",
                                10,
                                "s1",
                                "node-a",
                                "r1",
                                "c1",
                            "127.0.0.1",
                            "ipc",
                            "entity",
                            "e1",
                            "update",
                            "ok",
                            "{}",
                            "{}",
                            "{}",
                        )
                    ]
                )
            return SimpleNamespace(
                result_rows=[
                    (
                        datetime(2026, 1, 1, 0, 0, 0),
                        1,
                            10,
                            "s1",
                            "node-a",
                            "r1",
                            "c1",
                        "127.0.0.1",
                        "ipc",
                        "chat",
                        "openai",
                        "openai",
                        None,
                        "gpt",
                        "cloud",
                        "completion",
                        "ag1",
                        10,
                        20,
                        30,
                        1.2,
                        25.0,
                        True,
                        None,
                        "{}",
                    )
                ]
            )

    class _Provider(ClickHouseAuditLLMMixin):
        def __init__(self):
            self._client = _Client()

    provider = _Provider()
    audit = provider.get_audit_events(
        actor_user_id=1, event_type="audit", entity_type="entity", entity_id="e1", limit=1
    )
    ai_usage = provider.get_ai_model_usage_events(
        user_id=1, objective="chat", model_name="gpt", limit=1
    )
    audit_no_filters = provider.get_audit_events(limit=1)
    ai_usage_no_filters = provider.get_ai_model_usage_events(limit=1)

    assert audit and audit[0].event_type == "audit"
    assert ai_usage and ai_usage[0].model_name == "gpt"
    assert audit_no_filters and ai_usage_no_filters
    assert "actor_user_id = %(actor_user_id)s" in queries[0][0]
    assert "event_type = %(event_type)s" in queries[0][0]
    assert "entity_type = %(entity_type)s" in queries[0][0]
    assert "entity_id = %(entity_id)s" in queries[0][0]
    assert "user_id = %(user_id)s" in queries[1][0]
    assert "objective = %(objective)s" in queries[1][0]
    assert "model_name = %(model_name)s" in queries[1][0]


def test_clickhouse_helpers_cover_url_parsing_and_where_clauses(monkeypatch: pytest.MonkeyPatch):
    fake_client = object()
    fake_clickhouse = SimpleNamespace(get_client=lambda **kwargs: kwargs)
    monkeypatch.setitem(__import__("sys").modules, "clickhouse_connect", fake_clickhouse)

    secure_client = ClickHouseObsStorage._build_client("clickhouses://user:pw@example.com/analytics")
    plain_client = ClickHouseObsStorage._build_client("clickhouse://example.com/default?interface=native")
    assert secure_client["secure"] is True
    assert secure_client["port"] == 8443
    assert plain_client["interface"] == "native"
    assert plain_client["port"] == 8123
    assert ClickHouseObsStorage._resolve_database("clickhouse://host") == "default"
    assert ClickHouseObsStorage._where_clause(user_id=None, category=None, correlation_id=None) == ("", {})
    where, params = ClickHouseObsStorage._where_clause(user_id="u1", category="agent", correlation_id="c1")
    assert "user_id" in where and "category" in where and "correlation_id" in where
    assert params == {"user_id": "u1", "category": "agent", "correlation_id": "c1"}


def test_clickhouse_common_import_and_scheme_errors(monkeypatch: pytest.MonkeyPatch):
    real_import = __import__

    def _raising_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        if name == "clickhouse_connect":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", _raising_import)
    with pytest.raises(ProviderNotAvailableError):
        ClickHouseObsStorage._build_client("clickhouse://localhost/default")

    monkeypatch.setattr(
        "builtins.__import__",
        lambda name, globals=None, locals=None, fromlist=(), level=0: (
            SimpleNamespace(get_client=lambda **kwargs: kwargs)
            if name == "clickhouse_connect"
            else real_import(name, globals, locals, fromlist, level)
        ),
    )
    with pytest.raises(ProviderConfigError):
        ClickHouseObsStorage._build_client("http://localhost/default")


def test_clickhouse_provider_rejects_empty_url():
    with pytest.raises(ProviderConfigError, match="requires connection_url"):
        ClickHouseObsStorage("")


def test_otlp_exporter_constructor_with_fake_opentelemetry(monkeypatch: pytest.MonkeyPatch):
    calls = {}
    real_import = __import__

    class _Trace:
        @staticmethod
        def set_tracer_provider(provider):
            calls["provider"] = provider

        @staticmethod
        def get_tracer(name):
            return SimpleNamespace(start_as_current_span=lambda span_name: ("ctx", span_name))

    class _OTLPSpanExporter:
        def __init__(self, endpoint, insecure):
            calls["exporter"] = {"endpoint": endpoint, "insecure": insecure}

    class _Resource:
        @staticmethod
        def create(payload):
            calls["resource"] = payload
            return payload

    class _TracerProvider:
        def __init__(self, resource):
            self.resource = resource
            calls["tracer_provider"] = resource

        def add_span_processor(self, processor):
            calls["processor"] = processor

        def get_tracer(self, name):
            return SimpleNamespace(start_as_current_span=lambda span_name: ("ctx", span_name))

    class _BatchSpanProcessor:
        def __init__(self, exporter):
            self.exporter = exporter

    monkeypatch.setattr(
        "builtins.__import__",
        lambda name, globals=None, locals=None, fromlist=(), level=0: {
            "opentelemetry": SimpleNamespace(trace=_Trace),
            "opentelemetry.exporter.otlp.proto.grpc.trace_exporter": SimpleNamespace(OTLPSpanExporter=_OTLPSpanExporter),
            "opentelemetry.sdk.resources": SimpleNamespace(Resource=_Resource),
            "opentelemetry.sdk.trace": SimpleNamespace(TracerProvider=_TracerProvider),
            "opentelemetry.sdk.trace.export": SimpleNamespace(BatchSpanProcessor=_BatchSpanProcessor),
        }[name]
        if name.startswith("opentelemetry")
        else real_import(name, globals, locals, fromlist, level),
    )

    exporter = OtlpObsExporter("grpc://collector", insecure=True, service_name="demo")
    assert exporter._span_context_manager("span") == ("ctx", "span")
    assert calls["resource"] == {"service.name": "demo"}
    assert calls["exporter"] == {"endpoint": "grpc://collector", "insecure": True}

    with pytest.raises(ValueError, match="requires endpoint"):
        OtlpObsExporter("")


def test_sqlalchemy_obs_provider_filter_and_dedupe_branches(tmp_path):
    provider = SqliteObsStorage(str(tmp_path / "obs-branches.db"))
    provider.run_migrations()

    provider.record_audit_event(
        event_type="audit.branch",
        actor_user_id=7,
        entity_type="demo",
        entity_id="1",
        operation="update",
        status="ok",
    )
    provider.record_ai_model_usage(
        user_id=7,
        objective="chat",
        model_name="gpt-branch",
        request_kind="completion",
        success=True,
    )

    audit_filtered = provider.get_audit_events(
        actor_user_id=7,
        event_type="audit.branch",
        entity_type="demo",
        entity_id="1",
        limit=10,
    )
    llm_filtered = provider.get_ai_model_usage_events(
        user_id=7,
        objective="chat",
        model_name="gpt-branch",
        limit=10,
    )
    assert provider.get_audit_events(limit=10)
    assert provider.get_ai_model_usage_events(limit=10)
    assert audit_filtered and audit_filtered[0].event_type == "audit.branch"
    assert llm_filtered and llm_filtered[0].model_name == "gpt-branch"

    outbox = provider.enqueue_export_outbox(
        event_kind="branch",
        payload={"x": 1},
        dedupe_key="branch-key",
    )
    assert outbox.id
    outbox2 = provider.enqueue_export_outbox(
        event_kind="branch",
        payload={"x": 2},
        dedupe_key=None,
    )
    assert outbox2.id


def test_sqlalchemy_obs_provider_sums_ai_usage_tokens_by_engine_scope(tmp_path):
    provider = SqliteObsStorage(str(tmp_path / "obs-usage-sum.db"))
    provider.run_migrations()

    common = {
        "objective": "chat",
        "provider": "openai",
        "engine": "openai",
        "model_name": "gpt-test",
        "deployment_mode": "runtime",
        "request_kind": "completion",
    }
    provider.record_ai_model_usage(
        **common,
        engine_row_id=11,
        user_id=1,
        organization_id=10,
        session_id="s1",
        total_tokens=7,
        success=True,
    )
    provider.record_ai_model_usage(
        **common,
        engine_row_id=11,
        user_id=1,
        organization_id=10,
        session_id="s1",
        total_tokens=None,
        success=True,
    )
    provider.record_ai_model_usage(
        **common,
        engine_row_id=11,
        user_id=1,
        organization_id=10,
        session_id="s1",
        total_tokens=99,
        success=False,
    )
    provider.record_ai_model_usage(
        **common,
        engine_row_id=12,
        user_id=1,
        organization_id=10,
        session_id="s1",
        total_tokens=40,
        success=True,
    )

    used = provider.sum_ai_model_usage_total_tokens(
        engine_row_id=11,
        user_id=1,
        started_at=datetime(2026, 1, 1),
        ended_at=datetime(2027, 1, 1),
    )

    assert used == 7
