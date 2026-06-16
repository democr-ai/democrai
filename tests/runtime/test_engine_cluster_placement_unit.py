from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

import democrai.core.infrastructure.ai.engine.invocation.queue.maintenance as maintenance_mod
import democrai.core.application.ai.engine.orchestrator.placement as placement_mod
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.maintenance import (
    EngineQueueMaintenance,
)
from democrai.core.application.ai.engine.orchestrator.node_views import (
    NodeResourcesView,
)
from democrai.core.application.ai.engine.orchestrator.placement import (
    EnginePlacement,
)
from democrai.core.infrastructure.database.models import Base
from democrai.core.platform.utils.timezone import utc_now_naive
from tests.runtime.fake_redis import FakeRedisStream


def _view(node_id):
    return NodeResourcesView(node_id=node_id, has_gpu=True, ram_gb=64.0, vram_gb=24.0)


@pytest.fixture
def make_placement(monkeypatch):
    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        logger=None,
    )
    monkeypatch.setattr(placement_mod, "app_ctx", lambda: fake_ctx)

    def _factory(*, node_id, views, scores):
        monkeypatch.setattr(
            placement_mod,
            "load_active_node_views",
            lambda threshold_seconds: views,
        )
        placement = EnginePlacement(node_id=node_id)

        def _score(row, view):
            base = scores.get(view.node_id)
            if base is None:
                return None
            if row.get("prefer_local") and view.node_id == row.get("origin_node_id"):
                return base + placement_mod._ORIGIN_AFFINITY_BONUS
            return base

        placement._score = _score
        return placement

    return _factory


def _row(**overrides):
    values = {
        "id": "req-1",
        "selector_type": "objective",
        "objective": "chat",
        "capabilities_json": "[]",
        "prefer_local": None,
        "origin_node_id": "node-a",
        "created_at": utc_now_naive(),
        "available_at": utc_now_naive(),
    }
    values.update(overrides)
    return values


def test_defers_to_strictly_better_node(make_placement):
    placement = make_placement(
        node_id="node-b",
        views=[_view("node-a"), _view("node-b")],
        scores={"node-a": 100, "node-b": 50},
    )
    assert placement.should_claim(_row()) is False


def test_claims_when_best(make_placement):
    placement = make_placement(
        node_id="node-b",
        views=[_view("node-a"), _view("node-b")],
        scores={"node-a": 50, "node-b": 100},
    )
    assert placement.should_claim(_row()) is True


def test_tie_breaks_on_smallest_node_id(make_placement):
    views = [_view("node-a"), _view("node-b")]
    scores = {"node-a": 100, "node-b": 100}
    assert make_placement(
        node_id="node-a", views=views, scores=scores
    ).should_claim(_row()) is True
    assert make_placement(
        node_id="node-b", views=views, scores=scores
    ).should_claim(_row()) is False


def test_force_claim_after_age_threshold(make_placement):
    placement = make_placement(
        node_id="node-b",
        views=[_view("node-a"), _view("node-b")],
        scores={"node-a": 100, "node-b": 50},
    )
    old = utc_now_naive() - timedelta(seconds=60)
    assert (
        placement.should_claim(_row(created_at=old, available_at=old)) is True
    )


def test_claims_when_own_view_missing(make_placement):
    placement = make_placement(
        node_id="node-b",
        views=[_view("node-a")],
        scores={"node-a": 100},
    )
    assert placement.should_claim(_row()) is True


def test_defers_when_cannot_serve_selector(make_placement):
    placement = make_placement(
        node_id="node-b",
        views=[_view("node-a"), _view("node-b")],
        scores={"node-a": 100, "node-b": None},
    )
    assert placement.should_claim(_row()) is False


def test_prefer_local_gives_origin_affinity(make_placement):
    views = [_view("node-a"), _view("node-b")]
    scores = {"node-a": 100, "node-b": 100}
    placement_origin = make_placement(node_id="node-a", views=views, scores=scores)
    placement_other = make_placement(node_id="node-b", views=views, scores=scores)
    row = _row(prefer_local=True, origin_node_id="node-a")
    assert placement_origin.should_claim(dict(row)) is True
    assert placement_other.should_claim(dict(row)) is False


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'maint.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


def test_maintenance_dead_letters_orphaned_origin_hitl(
    session_factory, monkeypatch
):
    fake_ctx = SimpleNamespace(
        config=SimpleNamespace(get=lambda key, default=None: default),
        logger=None,
    )
    monkeypatch.setattr(maintenance_mod, "app_ctx", lambda: fake_ctx)
    monkeypatch.setattr(maintenance_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(
        maintenance_mod,
        "load_active_node_views",
        lambda threshold_seconds: [_view("node-b")],
    )
    store = EngineInvocationQueueStore(session_factory=session_factory)
    redis = FakeRedisStream()

    orphaned = store.enqueue(
        request_id="req-orphan",
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin_node_id="node-dead",
    )
    store.claim([orphaned], owner="node-b", lease_seconds=60)
    store.release(
        orphaned, defer_seconds=0, requires_origin_hitl=True, reason="hitl"
    )
    alive = store.enqueue(
        request_id="req-alive",
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin_node_id="node-b",
    )
    store.claim([alive], owner="node-b", lease_seconds=60)
    store.release(alive, defer_seconds=0, requires_origin_hitl=True, reason="hitl")

    maintenance = EngineQueueMaintenance(
        node_id="node-b",
        store=store,
        response_stream=redis,
        orphan_origin_check_enabled=True,
    )
    asyncio.run(maintenance.run_once())

    assert store.get_status(orphaned)["status"] == "dead_letter"
    assert store.get_status(alive)["status"] == "pending"
    key = f"democrai:engine:resp:{orphaned}"
    kinds = [fields.get("kind") for _id, fields in redis.streams.get(key, [])]
    assert kinds == ["error"]
