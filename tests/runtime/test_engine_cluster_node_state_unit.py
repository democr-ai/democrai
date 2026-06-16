from __future__ import annotations

from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

import democrai.core.application.ai.engine.orchestrator.node_state as node_state_mod
from democrai.core.application.ai.engine.orchestrator.node_state import (
    NodeStateRepository,
    record_instance_running,
)
from democrai.core.infrastructure.database.models import (
    Base,
    EngineNodeInstanceRegistry,
    RuntimeNodeRegistry,
)


@pytest.fixture
def session_factory(tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    yield factory
    engine.dispose()


_SAMPLE = {
    "cpu_percent": 21.5,
    "ram_total_mb": 65_536,
    "ram_free_mb": 30_000,
    "vram_total_mb": 24_576,
    "vram_free_mb": 20_000,
    "has_nvidia_gpu": True,
}


def test_publish_heartbeat_creates_and_updates_row(session_factory):
    repo = NodeStateRepository(session_factory=session_factory)
    repo.publish_heartbeat(node_id="node-a", sample=dict(_SAMPLE))
    with session_factory() as session:
        row = session.query(RuntimeNodeRegistry).filter_by(node_id="node-a").one()
        assert row.orchestrator_last_seen_at is not None
        assert row.ram_free_mb == 30_000
        assert row.vram_free_mb == 20_000
        assert row.has_nvidia_gpu is True
        assert '"vram_total_mb": 24576' in row.gpu_inventory_json
        # core-owned heartbeat untouched
        assert row.last_seen_at is None

    repo.publish_heartbeat(
        node_id="node-a", sample={**_SAMPLE, "ram_free_mb": 1_000}
    )
    with session_factory() as session:
        row = session.query(RuntimeNodeRegistry).filter_by(node_id="node-a").one()
        assert row.ram_free_mb == 1_000

    repo.mark_offline(node_id="node-a")
    with session_factory() as session:
        row = session.query(RuntimeNodeRegistry).filter_by(node_id="node-a").one()
        assert row.orchestrator_last_seen_at is None


def _instance(engine_row_id, model_registry_id, status="running", **extra):
    return {
        "engine_row_id": engine_row_id,
        "model_registry_id": model_registry_id,
        "engine_id": "llamacpp",
        "model": "qwen",
        "config_signature": "sig",
        "pid": 4242,
        "status": status,
        **extra,
    }


def test_reconcile_instances_adds_updates_and_removes(session_factory):
    repo = NodeStateRepository(session_factory=session_factory)
    repo.reconcile_instances(
        node_id="node-a",
        instances=[_instance(9, 11), _instance(9, 12, status="stopped")],
    )
    with session_factory() as session:
        rows = session.query(EngineNodeInstanceRegistry).all()
        assert [(r.engine_row_id, r.model_registry_id, r.status) for r in rows] == [
            (9, 11, "running")
        ]

    # drift: handle 11 gone, handle 13 appeared
    repo.reconcile_instances(node_id="node-a", instances=[_instance(9, 13)])
    with session_factory() as session:
        rows = session.query(EngineNodeInstanceRegistry).all()
        assert [(r.engine_row_id, r.model_registry_id) for r in rows] == [(9, 13)]


def test_reconcile_keeps_loading_rows(session_factory):
    repo = NodeStateRepository(session_factory=session_factory)
    with session_factory() as session:
        session.add(
            EngineNodeInstanceRegistry(
                node_id="node-a",
                engine_row_id=9,
                model_registry_id=99,
                status="loading",
            )
        )
        session.commit()
    repo.reconcile_instances(node_id="node-a", instances=[_instance(9, 11)])
    with session_factory() as session:
        statuses = {
            (r.engine_row_id, r.model_registry_id): r.status
            for r in session.query(EngineNodeInstanceRegistry).all()
        }
    assert statuses == {(9, 99): "loading", (9, 11): "running"}


def test_reconcile_does_not_touch_other_nodes(session_factory):
    repo = NodeStateRepository(session_factory=session_factory)
    repo.reconcile_instances(node_id="node-b", instances=[_instance(9, 11)])
    repo.reconcile_instances(node_id="node-a", instances=[])
    with session_factory() as session:
        rows = session.query(EngineNodeInstanceRegistry).all()
        assert [(r.node_id, r.model_registry_id) for r in rows] == [("node-b", 11)]


def test_purge_node_instances(session_factory):
    repo = NodeStateRepository(session_factory=session_factory)
    repo.reconcile_instances(
        node_id="node-a", instances=[_instance(9, 11), _instance(9, 12)]
    )
    assert repo.purge_node_instances(node_id="node-a") == 2
    with session_factory() as session:
        assert session.query(EngineNodeInstanceRegistry).count() == 0


def test_upsert_and_remove_instance(session_factory):
    repo = NodeStateRepository(session_factory=session_factory)
    repo.upsert_running_instance(
        node_id="node-a",
        engine_row_id=9,
        model_registry_id=11,
        engine_id="llamacpp",
        model="qwen",
        config_signature="sig",
        pid=1,
    )
    repo.upsert_running_instance(
        node_id="node-a",
        engine_row_id=9,
        model_registry_id=11,
        engine_id="llamacpp",
        model="qwen",
        config_signature="sig2",
        pid=2,
    )
    with session_factory() as session:
        rows = session.query(EngineNodeInstanceRegistry).all()
        assert len(rows) == 1
        assert rows[0].config_signature == "sig2"
        assert rows[0].pid == 2

    repo.remove_instance(node_id="node-a", engine_row_id=9, model_registry_id=11)
    with session_factory() as session:
        assert session.query(EngineNodeInstanceRegistry).count() == 0


def test_write_through_noop_outside_orchestrator_process(monkeypatch):
    monkeypatch.delenv("DEMOCRAI_ENGINE_ORCHESTRATOR", raising=False)
    calls = []
    monkeypatch.setattr(
        node_state_mod,
        "NodeStateRepository",
        lambda *a, **k: calls.append("constructed"),
    )
    record_instance_running(engine_row_id=9, model_registry_id=11)
    assert calls == []


def test_write_through_noop_when_cluster_disabled(monkeypatch):
    monkeypatch.setenv("DEMOCRAI_ENGINE_ORCHESTRATOR", "1")
    monkeypatch.setattr(
        node_state_mod,
        "app_ctx",
        lambda: SimpleNamespace(config=SimpleNamespace(get=lambda k, d=None: d)),
    )
    calls = []
    monkeypatch.setattr(
        node_state_mod,
        "NodeStateRepository",
        lambda *a, **k: calls.append("constructed"),
    )
    record_instance_running(engine_row_id=9, model_registry_id=11)
    assert calls == []
