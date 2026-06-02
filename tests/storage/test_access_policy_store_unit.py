from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from democrai.core.application.access_policy import AccessRequest
from democrai.core.application.access_policy import AccessScope
from democrai.core.infrastructure.database.models import Base
from democrai.core.infrastructure.database.models import ExternalAccessRequest
import democrai.core.infrastructure.database.access_policy as store_mod


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(engine)
    return engine, SessionLocal


def _request(operation: str, *, session_key: str = "sess-1") -> AccessRequest:
    return AccessRequest.create(
        subject_type="module",
        subject_name="system",
        resource_type="network",
        operation=operation,
        target="https://api.example.com/v1",
        requested_by=1,
        session_key=session_key,
        task_id="task-1",
    )


def test_access_policy_store_upserts_pending_request_without_operation_collision(monkeypatch):
    engine, SessionLocal = _session_factory()
    monkeypatch.setattr(store_mod, "session_scope", lambda: SessionLocal())
    try:
        receive = _request("receive")
        send = _request("send")

        assert store_mod.upsert_pending_access_request(receive) is True
        assert store_mod.upsert_pending_access_request(send) is True
        assert store_mod.upsert_pending_access_request(receive) is False

        with SessionLocal() as session:
            rows = session.query(ExternalAccessRequest).all()
            assert len(rows) == 2
            assert {row.operation for row in rows} == {"receive", "send"}
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_access_policy_store_approvals_are_operation_specific(monkeypatch):
    engine, SessionLocal = _session_factory()
    monkeypatch.setattr(store_mod, "session_scope", lambda: SessionLocal())
    try:
        receive = _request("receive")
        send = _request("send")
        permanent = AccessScope.permanent()

        store_mod.upsert_access_approval(
            subject=receive.subject,
            resource=receive.resource,
            scope=permanent,
            approved_by=1,
        )

        assert (
            store_mod.has_access_approval(
                subject=receive.subject,
                resource=receive.resource,
                scope=permanent,
            )
            is True
        )
        assert (
            store_mod.has_access_approval(
                subject=send.subject,
                resource=send.resource,
                scope=permanent,
            )
            is False
        )
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_access_policy_store_session_decision_requires_matching_session(monkeypatch):
    engine, SessionLocal = _session_factory()
    monkeypatch.setattr(store_mod, "session_scope", lambda: SessionLocal())
    try:
        request = _request("receive", session_key="sess-1")
        other_session = _request("receive", session_key="sess-2")
        store_mod.upsert_pending_access_request(request)
        store_mod.upsert_pending_access_request(other_session)

        rows = store_mod.mark_access_request_decision(
            request,
            status="session",
            scope=AccessScope.session("sess-1"),
        )

        assert len(rows) == 1
        assert rows[0]["session_key"] == "sess-1"
        assert rows[0]["status"] == "session"

        pending = store_mod.get_pending_access_requests()
        assert len(pending) == 1
        assert pending[0]["session_key"] == "sess-2"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
