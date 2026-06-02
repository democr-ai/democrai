from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import Column, Integer, JSON, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import democrai.core.application.observability.service as obs_service_mod
import democrai.core.application.observability.sqlalchemy_audit as audit_mod
from democrai.core.application.observability.service import ObservabilityService
from democrai.core.application.observability.service import _normalize_json
from democrai.core.application.observability.service import attach_session_audit_actor
from democrai.core.application.observability.service import resolve_entity_identity
from democrai.core.application.observability.service import snapshot_model
from democrai.core.application.observability.service import snapshot_model_before_update


Base = declarative_base()


class DemoRow(Base):
    __tablename__ = "demo_rows"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    secret_token = Column(String, nullable=True)


class CompactAuditRow(Base):
    __tablename__ = "compact_audit_rows"
    __audit_compact_fields__ = {"content"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(JSON, nullable=False)
    label = Column(String, nullable=False)


@dataclass
class _Payload:
    username: str
    password: str


class _BrokenIso:
    def isoformat(self):
        raise RuntimeError("boom")

    def __str__(self):
        return "broken-iso"


class _NoSetattr:
    __slots__ = ()


def _make_service_env(monkeypatch, request_ctx=None, store=None, logger=None):
    monkeypatch.setattr(
        obs_service_mod,
        "app_ctx",
        lambda: SimpleNamespace(
            obs_store=store,
            logger=logger or SimpleNamespace(error=lambda *args, **kwargs: None),
        ),
    )
    monkeypatch.setattr(obs_service_mod, "_safe_req_ctx", lambda: request_ctx)


def test_normalize_json_and_snapshot_helpers_cover_redaction_and_fallbacks():
    payload = _normalize_json(
        {
            "user": _Payload(username="fabio", password="secret"),
            "items": [1, datetime(2026, 3, 4, 12, 0, 0)],
            "api_key": "abc",
            "nested_secret": "hidden",
            "broken": _BrokenIso(),
        }
    )
    assert payload["user"]["password"] == "<redacted>"
    assert payload["api_key"] == "<redacted>"
    assert payload["nested_secret"] == "<redacted>"
    assert payload["broken"] == "broken-iso"

    assert snapshot_model(object()) == {}
    assert resolve_entity_identity(object())[1] is None


def test_snapshot_before_update_and_identity_cover_sqlalchemy_objects():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    with SessionLocal() as session:
        row = DemoRow(name="before", secret_token="tok-1")
        session.add(row)
        session.commit()
        session.refresh(row)
        assert snapshot_model(row)["secret_token"] == "tok-1"
        entity_type, entity_id = resolve_entity_identity(row)
        assert entity_type == "demo_rows"
        assert entity_id == str(row.id)

        row.name = "after"
        before = snapshot_model_before_update(row)
        assert before["name"] == "before"


def test_snapshot_helpers_cover_attribute_error_branches(monkeypatch):
    fake_mapper = SimpleNamespace(
        column_attrs=[SimpleNamespace(key="bad_attr")],
        primary_key=[SimpleNamespace(key="bad_pk")],
    )
    fake_state = SimpleNamespace(
        mapper=fake_mapper,
        attrs={"bad_attr": SimpleNamespace(history=SimpleNamespace(has_changes=lambda: False, deleted=[]))},
    )

    class _Broken:
        __tablename__ = "broken_rows"

        def __getattr__(self, name):
            raise RuntimeError(name)

    broken = _Broken()
    monkeypatch.setattr(obs_service_mod, "sa_inspect", lambda obj: fake_state)

    assert snapshot_model(broken) == {}
    assert snapshot_model_before_update(broken) == {}
    assert resolve_entity_identity(broken) == ("broken_rows", None)


def test_snapshot_before_update_returns_current_snapshot_when_inspection_fails(monkeypatch):
    monkeypatch.setattr(obs_service_mod, "snapshot_model", lambda obj: {"id": 1})
    monkeypatch.setattr(
        obs_service_mod,
        "sa_inspect",
        lambda obj: (_ for _ in ()).throw(RuntimeError("inspect boom")),
    )
    assert snapshot_model_before_update(object()) == {"id": 1}


def test_attach_session_audit_actor_handles_existing_missing_and_immutable_sessions():
    session = SimpleNamespace(info={})
    attach_session_audit_actor(
        session,
        actor_user_id=1,
        actor_role="admin",
        organization_id=1,
        session_id="sess-1",
        request_id="req-1",
        correlation_id="corr-1",
        client_ip="127.0.0.1",
        channel="http",
    )
    actor = session.info["observability_actor"]
    assert actor["actor_user_id"] == 1
    assert actor["client_ip"] == "127.0.0.1"

    session2 = SimpleNamespace()
    attach_session_audit_actor(session2, actor_user_id=2)
    assert session2.info["observability_actor"]["actor_user_id"] == 2

    attach_session_audit_actor(_NoSetattr(), actor_user_id=3)


def test_observability_service_emits_app_auth_db_and_ai_model_usage_events(monkeypatch):
    calls = []
    request_ctx = SimpleNamespace(
        user=1,
        role="admin",
        organization_id=1,
        session_key="sess-1",
        request_id="req-1",
        client_ip="10.0.0.1",
        channel="http",
    )
    store = SimpleNamespace(
        record_event=lambda **kwargs: calls.append(("event", kwargs)) or kwargs,
        record_audit_event=lambda **kwargs: calls.append(("audit", kwargs)) or kwargs,
        record_ai_model_usage=lambda **kwargs: calls.append(("ai_model_usage", kwargs)) or kwargs,
    )
    _make_service_env(monkeypatch, request_ctx=request_ctx, store=store)

    service = ObservabilityService()
    service.record_app_event(event_name="ui.click", category="ui", payload={"jwt": "secret"})
    service.record_auth_event(event_type="auth.login.succeeded", subject_user_id=1, success=True)
    service.record_db_mutation(
        operation="update",
        entity_type="demo_rows",
        entity_id="1",
        before={"token": "old"},
        after={"token": "new"},
        metadata={"refresh_token": "x"},
        actor={"actor_user_id": 9},
    )
    service.record_ai_model_usage(
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
        metadata={"api_key": "x"},
    )

    assert calls[0][0] == "event"
    assert calls[0][1]["payload"]["jwt"] == "<redacted>"
    assert calls[1][1]["actor_user_id"] == 1
    assert calls[2][1]["actor_user_id"] == 9
    assert calls[2][1]["metadata"]["refresh_token"] == "<redacted>"
    assert calls[3][1]["user_id"] == 1
    assert calls[3][1]["metadata"]["api_key"] == "<redacted>"


def test_observability_service_compacts_model_declared_audit_fields(monkeypatch):
    calls = []
    store = SimpleNamespace(
        record_audit_event=lambda **kwargs: calls.append(("audit", kwargs)) or kwargs,
    )
    _make_service_env(monkeypatch, request_ctx=None, store=store)

    service = ObservabilityService()
    service.record_db_mutation(
        operation="update",
        entity_type="compact_audit_rows",
        entity_id="1",
        before={"content": {"text": "before"}, "label": "visible"},
        after={"content": {"text": "after"}, "label": "visible"},
        metadata={},
        actor={},
        compact_fields={"content"},
    )

    audit = calls[0][1]
    assert audit["before"]["content"]["redacted"] == "observability_compacted"
    assert audit["after"]["content"]["redacted"] == "observability_compacted"
    assert audit["after"]["label"] == "visible"


def test_observability_service_handles_missing_store_and_logging_failure(monkeypatch):
    errors = []
    logger = SimpleNamespace(error=lambda message: errors.append(message))
    _make_service_env(monkeypatch, request_ctx=None, store=None, logger=logger)
    service = ObservabilityService()
    assert service.record_app_event(event_name="noop", category="system", payload={}) is None

    broken_store = SimpleNamespace(record_event=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("persist boom")))
    _make_service_env(monkeypatch, request_ctx=None, store=broken_store, logger=logger)
    assert service.record_app_event(event_name="noop", category="system", payload={}) is None
    assert errors and "persist boom" in errors[-1]
    monkeypatch.setattr(
        obs_service_mod,
        "app_ctx",
        lambda: SimpleNamespace(obs_store=broken_store, logger=None),
    )
    assert service.record_app_event(event_name="noop", category="system", payload={}) is None


def test_observability_service_leaves_correlation_id_null_without_request_context(monkeypatch):
    calls = []
    store = SimpleNamespace(
        record_audit_event=lambda **kwargs: calls.append(("audit", kwargs)) or kwargs,
        record_ai_model_usage=lambda **kwargs: calls.append(("ai_model_usage", kwargs)) or kwargs,
    )
    _make_service_env(monkeypatch, request_ctx=None, store=store)

    service = ObservabilityService()
    service.record_db_mutation(
        operation="update",
        entity_type="demo_rows",
        entity_id="1",
        before={"old": 1},
        after={"new": 2},
        metadata={},
        actor={},
    )
    service.record_auth_event(
        event_type="auth.logout",
        subject_user_id=1,
        success=True,
    )
    service.record_ai_model_usage(
        objective="chat",
        provider="openai",
        engine="openai",
        model_name="gpt-test",
        deployment_mode="cloud",
        request_kind="completion",
    )

    assert calls[0][1]["correlation_id"] is None
    assert calls[1][1]["correlation_id"] is None
    assert calls[2][1]["correlation_id"] is None


def test_sqlalchemy_audit_helpers_and_hooks_cover_commit_skip_and_rollback(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    audit_mod.install_sqlalchemy_audit_hooks()
    events = []
    monkeypatch.setattr(
        audit_mod.observability_service,
        "record_db_mutation",
        lambda **kwargs: events.append(kwargs),
    )

    with SessionLocal() as session:
        attach_session_audit_actor(session, actor_user_id=1)
        row = DemoRow(name="created", secret_token="tok")
        session.add(row)
        session.commit()
        row.name = "updated"
        session.commit()
        session.delete(row)
        session.commit()

    assert [event["operation"] for event in events] == ["insert", "update", "delete"]
    assert events[0]["actor"]["actor_user_id"] == 1

    with SessionLocal() as session:
        session.add(CompactAuditRow(content={"text": "compact me"}, label="visible"))
        session.commit()

    assert events[-1]["compact_fields"] == {"content"}

    with SessionLocal() as session:
        session.info["skip_observability_audit"] = True
        session.add(DemoRow(name="skipped"))
        session.commit()
    assert len(events) == 4

    with SessionLocal() as session:
        attach_session_audit_actor(session, actor_user_id=2)
        session.add(DemoRow(name="rolled-back"))
        session.flush()
        session.rollback()
        assert session.info.get(audit_mod._AUDIT_ENTRIES_KEY) is None

    assert audit_mod._is_observability_table(SimpleNamespace(__tablename__="audit_events")) is True
    assert audit_mod._is_auditable(object()) is False
    with SessionLocal() as session:
        attach_session_audit_actor(session, actor_user_id=3)
        assert audit_mod._actor_metadata(session)["actor_user_id"] == 3
    assert audit_mod._is_auditable(SimpleNamespace(__tablename__="events", __table__=object())) is False
