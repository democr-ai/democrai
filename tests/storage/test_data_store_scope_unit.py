from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy import Column, JSON, String
from sqlalchemy.orm import sessionmaker

from democrai.core.application.observability.sqlalchemy_audit import install_sqlalchemy_audit_hooks
from democrai.core.application.auth.roles import (
    ROLE_LEVEL_ORGANIZATION,
    ROLE_LEVEL_SUPER,
    ROLE_LEVEL_USER,
    is_organization_role,
    is_super_role,
    is_user_role,
    normalize_role,
    resolve_primary_role,
    role_level,
)
from democrai.core.infrastructure.storage.data.mixins import Base, UserMixin
from democrai.core.infrastructure.storage.data.store import DataStore
from democrai.core.runtime.foundation.app import app_ctx, set_req_ctx, reset_req_ctx, RequestContext


class StoreEntry(Base, UserMixin):
    __tablename__ = "store_entries_test"

    id = Column(String, primary_key=True)
    key = Column(String, index=True, nullable=False)
    value = Column(JSON, nullable=False)


def _make_provider():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SimpleNamespace(get_session=SessionLocal)


def test_data_store_scopes_reads_by_access_level():
    provider = _make_provider()
    old_provider = app_ctx().data_store
    app_ctx().data_store = provider
    try:
        with provider.get_session() as session:
            session.add_all(
                [
                    StoreEntry(
                        id="a",
                        key="alpha",
                        value={"v": 1},
                        user_id=1,
                        organization_id=1,
                    ),
                    StoreEntry(
                        id="b",
                        key="beta",
                        value={"v": 2},
                        user_id=2,
                        organization_id=1,
                    ),
                    StoreEntry(
                        id="c",
                        key="gamma",
                        value={"v": 3},
                        user_id=3,
                        organization_id=2,
                    ),
                ]
            )
            session.commit()

        super_store = DataStore(1, organization_id=1, access_level=ROLE_LEVEL_SUPER)
        org_store = DataStore(
            1,
            organization_id=1,
            access_level=ROLE_LEVEL_ORGANIZATION,
        )
        user_store = DataStore(1, organization_id=1, access_level=ROLE_LEVEL_USER)

        assert {item.id for item in super_store.list(StoreEntry)} == {"a", "b", "c"}
        assert {item.id for item in org_store.list(StoreEntry)} == {"a", "b"}
        assert {item.id for item in user_store.list(StoreEntry)} == {"a"}
    finally:
        app_ctx().data_store = old_provider


def test_data_store_applies_organization_id_on_write():
    provider = _make_provider()
    old_provider = app_ctx().data_store
    app_ctx().data_store = provider
    try:
        store = DataStore(
            9,
            organization_id=9,
            access_level=ROLE_LEVEL_ORGANIZATION,
        )
        created = store.add(StoreEntry(id="d", key="delta", value={"v": 4}))

        assert created.user_id == 9
        assert created.organization_id == 9
    finally:
        app_ctx().data_store = old_provider


def test_data_store_update_ignores_ownership_changes_with_warning():
    provider = _make_provider()
    warnings = []
    old_provider = app_ctx().data_store
    old_logger = app_ctx().logger
    app_ctx().data_store = provider
    app_ctx().logger = SimpleNamespace(
        warning=lambda message, *args, **kwargs: warnings.append((message, args, kwargs))
    )
    try:
        with provider.get_session() as session:
            session.add(
                StoreEntry(
                    id="owned",
                    key="alpha",
                    value={"v": 1},
                    user_id=1,
                    organization_id=10,
                )
            )
            session.commit()

        store = DataStore(1, organization_id=10, access_level=ROLE_LEVEL_USER)
        updated = store.update(
            StoreEntry,
            "owned",
            key="beta",
            user_id=2,
            organization_id=20,
        )
        assert updated is not None

        with provider.get_session() as session:
            row = session.query(StoreEntry).filter(StoreEntry.id == "owned").first()
            assert row is not None
            assert row.key == "beta"
            assert row.user_id == 1
            assert row.organization_id == 10
        assert warnings
        assert "Ignoring ownership fields" in warnings[0][0]
    finally:
        app_ctx().data_store = old_provider
        app_ctx().logger = old_logger


def test_data_store_emits_audit_events_for_mutations():
    class AuditEntry(Base):
        __tablename__ = "audit_entries_test"

        id = Column(String, primary_key=True)
        key = Column(String, nullable=False)

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    provider = SimpleNamespace(get_session=SessionLocal)
    audit_events = []
    old_provider = app_ctx().data_store
    old_obs_store = app_ctx().obs_store
    app_ctx().data_store = provider
    app_ctx().obs_store = SimpleNamespace(
        record_audit_event=lambda **kwargs: audit_events.append(kwargs)
    )
    install_sqlalchemy_audit_hooks()
    token = set_req_ctx(
        RequestContext(
            app=app_ctx(),
            request_id="req-audit",
            user="u9",
            role="user",
            organization_id="org-9",
            access_level=3,
            channel="http",
            session_key="sess-1",
            client_ip="127.0.0.1",
        )
    )
    try:
        store = DataStore(9, organization_id=9, access_level=ROLE_LEVEL_USER)
        store.add(AuditEntry(id="a1", key="alpha"))
        store.update(AuditEntry, "a1", key="beta")
        assert store.delete(AuditEntry, "a1") is True
    finally:
        reset_req_ctx(token)
        app_ctx().data_store = old_provider
        app_ctx().obs_store = old_obs_store

    assert [event["operation"] for event in audit_events] == ["insert", "update", "delete"]
    assert audit_events[0]["actor_user_id"] == 9
    assert audit_events[0]["client_ip"] == "127.0.0.1"


def test_auth_roles_helpers_cover_aliases_levels_and_fallbacks():
    assert normalize_role(None) == "guest"
    assert normalize_role("viewer") == "user"
    assert role_level("Admin") == ROLE_LEVEL_SUPER
    assert resolve_primary_role(None) == "guest"
    assert resolve_primary_role(["guest", "user", "org"]) == "organization"
    assert is_super_role("super") is True
    assert is_organization_role("organization") is True
    assert is_user_role("user") is True
    assert is_super_role(level=ROLE_LEVEL_SUPER) is True
    assert is_organization_role(level=ROLE_LEVEL_ORGANIZATION) is True
    assert is_user_role(level=ROLE_LEVEL_USER) is True
