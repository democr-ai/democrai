from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import democrai.core.application.ai.engine.quotas.service as quota_service_mod
import democrai.core.application.ai.engine.quotas.subjects as quota_subjects_mod
import democrai.core.infrastructure.ai.engine.quotas.repository as quota_repo_mod
from democrai.core.application.ai.engine.quotas import check_engine_quota
from democrai.core.application.ai.engine.quotas.types import PERIOD_DAY
from democrai.core.application.ai.engine.quotas.types import PERIOD_HOUR
from democrai.core.application.ai.engine.quotas.types import PERIOD_MINUTE
from democrai.core.application.ai.engine.quotas.types import PERIOD_MONTH
from democrai.core.application.ai.engine.quotas.types import PERIOD_WEEK
from democrai.core.application.ai.engine.quotas.types import SCOPE_ALL
from democrai.core.application.ai.engine.quotas.types import SCOPE_GUEST
from democrai.core.application.ai.engine.quotas.types import SCOPE_ORGANIZATION
from democrai.core.application.ai.engine.quotas.types import SCOPE_ROLE
from democrai.core.application.ai.engine.quotas.types import SCOPE_USER
from democrai.core.infrastructure.database.models import Base
from democrai.core.infrastructure.database.models import EngineRegistry
from democrai.core.infrastructure.database.models import Role
from democrai.core.infrastructure.database.models import User
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaCounter
from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaLimit


class _UsageStore:
    def __init__(self, value: int = 0):
        self.value = value
        self.calls = []

    def sum_ai_model_usage_total_tokens(self, **kwargs):
        self.calls.append(kwargs)
        return self.value


@pytest.fixture()
def quota_env(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(quota_subjects_mod, "SessionLocal", SessionLocal)
    monkeypatch.setattr(quota_repo_mod, "SessionLocal", SessionLocal)
    store = _UsageStore()
    monkeypatch.setattr(
        quota_repo_mod,
        "app_ctx",
        lambda: SimpleNamespace(obs_store=store),
    )

    with SessionLocal() as session:
        engine_row = EngineRegistry(
            name="engine-1",
            provider="openai",
            config={},
            status="active",
            supported=True,
        )
        role = Role(name="operator")
        user = User(username="user-1", access_level=3, organization_id=22)
        user.roles = [role]
        session.add_all([engine_row, role, user])
        session.commit()
        session.refresh(engine_row)
        session.refresh(role)
        session.refresh(user)
        ids = {
            "engine_row_id": engine_row.id,
            "role_id": role.id,
            "user_id": user.id,
        }

    try:
        yield SimpleNamespace(SessionLocal=SessionLocal, store=store, **ids)
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def _limit(env, *, period_unit=PERIOD_DAY, scope_type=SCOPE_ALL, scope_id=None, limit=10):
    with env.SessionLocal() as session:
        count = session.query(EngineQuotaCounter.id).count()
        counter = EngineQuotaCounter(
            name=f"counter-{scope_type}-{period_unit}-{count}",
            period_unit=period_unit,
        )
        session.add(counter)
        session.flush()
        session.add(
            EngineQuotaLimit(
                counter_id=counter.id,
                engine_row_id=env.engine_row_id,
                scope_type=scope_type,
                scope_id=scope_id,
                limit_total_tokens=limit,
            )
        )
        session.commit()


def test_engine_quota_allows_when_no_limits(quota_env):
    decision = check_engine_quota(
        engine_registry_id=quota_env.engine_row_id,
        user_id=quota_env.user_id,
        request_context={"user": quota_env.user_id},
    )
    assert decision.allowed is True
    assert quota_env.store.calls == []


def test_engine_quota_all_limit_blocks(quota_env):
    _limit(quota_env, scope_type=SCOPE_ALL, limit=10)
    quota_env.store.value = 10

    decision = check_engine_quota(
        engine_registry_id=quota_env.engine_row_id,
        user_id=quota_env.user_id,
        request_context={"user": quota_env.user_id, "organization_id": 22},
    )

    assert decision.allowed is False
    assert decision.scope_type == SCOPE_ALL
    assert quota_env.store.calls[-1]["engine_row_id"] == quota_env.engine_row_id


def test_engine_quota_organization_user_and_role_are_individual_filters(quota_env):
    _limit(quota_env, scope_type=SCOPE_ORGANIZATION, scope_id=22, limit=100)
    _limit(quota_env, scope_type=SCOPE_ROLE, scope_id=quota_env.role_id, limit=100)
    _limit(quota_env, scope_type=SCOPE_USER, scope_id=quota_env.user_id, limit=5)
    quota_env.store.value = 5

    decision = check_engine_quota(
        engine_registry_id=quota_env.engine_row_id,
        user_id=quota_env.user_id,
        request_context={"user": quota_env.user_id, "organization_id": 22},
    )

    assert decision.allowed is False
    assert decision.scope_type == SCOPE_USER
    assert quota_env.store.calls[0]["organization_id"] == 22
    assert quota_env.store.calls[1]["user_id"] == quota_env.user_id
    assert quota_env.store.calls[2]["user_id"] == quota_env.user_id


def test_engine_quota_guest_uses_session_key(quota_env):
    _limit(quota_env, scope_type=SCOPE_GUEST, limit=3)
    quota_env.store.value = 3

    decision = check_engine_quota(
        engine_registry_id=quota_env.engine_row_id,
        user_id=None,
        request_context={"session_key": "guest-session"},
    )

    assert decision.allowed is False
    assert quota_env.store.calls[-1]["session_id"] == "guest-session"


def test_engine_quota_windows_are_rolling(quota_env, monkeypatch):
    now = datetime(2026, 3, 31, 12, 0, 0)
    monkeypatch.setattr(quota_service_mod, "utc_now_naive", lambda: now)
    expected = {
        PERIOD_MINUTE: now - timedelta(minutes=1),
        PERIOD_HOUR: now - timedelta(hours=1),
        PERIOD_DAY: now - timedelta(days=1),
        PERIOD_WEEK: now - timedelta(weeks=1),
        PERIOD_MONTH: datetime(2026, 2, 28, 12, 0, 0),
    }

    for unit, started_at in expected.items():
        quota_env.store.calls.clear()
        _limit(quota_env, period_unit=unit, scope_type=SCOPE_ALL, limit=100)
        decision = check_engine_quota(
            engine_registry_id=quota_env.engine_row_id,
            user_id=quota_env.user_id,
            request_context={"user": quota_env.user_id},
        )
        assert decision.allowed is True
        assert quota_env.store.calls[-1]["started_at"] == started_at
        assert quota_env.store.calls[-1]["ended_at"] == now
