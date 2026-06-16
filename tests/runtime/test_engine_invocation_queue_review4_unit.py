from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

import democrai.core.infrastructure.ai.engine.invocation.queue.maintenance as maintenance_mod
import democrai.core.infrastructure.ai.engine.invocation.transports.queue as queue_mod
from democrai.core.application.ai.engine.invocation import (
    EngineInvocationRequest,
    EngineInvocationTarget,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.maintenance import (
    EngineQueueMaintenance,
)
from democrai.core.infrastructure.ai.engine.invocation.queue.store import (
    EngineInvocationQueueStore,
)
from democrai.core.infrastructure.ai.engine.invocation.transports.queue import (
    EngineQueueTransport,
)
from democrai.core.infrastructure.ai.engine.response.writer import (
    EngineResponseStreamWriter,
)
from democrai.core.infrastructure.database.models import (
    Base,
    EngineNodeInstallRegistry,
    EngineNodeInstanceRegistry,
    RuntimeNodeRegistry,
)
from democrai.core.platform.utils.timezone import utc_now_naive
from tests.runtime.fake_redis import FakeRedisStream


def _config(values: dict | None = None):
    data = values or {}
    return SimpleNamespace(get=lambda key, default=None: data.get(key, default))


def _ctx(values: dict | None = None):
    return SimpleNamespace(config=_config(values), node_id="node-b", logger=None)


def _seed_active_node(session, node_id: str) -> None:
    now = utc_now_naive()
    session.add(
        RuntimeNodeRegistry(
            node_id=node_id,
            hostname=node_id,
            status="active",
            orchestrator_last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    )


class _ClosableFakeStream(FakeRedisStream):
    def __init__(self):
        super().__init__()
        self.closed = 0

    async def aclose(self):
        self.closed += 1
        await super().aclose()


class _FailingPublishStream(FakeRedisStream):
    async def publish(self, channel_id: str, data: dict) -> None:
        raise RuntimeError("queued publish failed")


def test_queue_status_requires_active_receiver(monkeypatch, tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue-status.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(queue_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(queue_mod, "app_ctx", lambda: _ctx())

    store = EngineInvocationQueueStore(session_factory=session_factory)
    transport = EngineQueueTransport(store=store, response_stream=FakeRedisStream())

    assert transport.status().ok is False

    with session_factory() as session:
        session.add(
            RuntimeNodeRegistry(
                node_id="node-a",
                hostname="node-a",
                status="inactive",
                orchestrator_last_seen_at=utc_now_naive(),
                created_at=utc_now_naive(),
                updated_at=utc_now_naive(),
            )
        )
        session.commit()

    assert transport.status().ok is False

    with session_factory() as session:
        _seed_active_node(session, "node-b")
        session.add(
            EngineNodeInstanceRegistry(
                node_id="node-b",
                engine_row_id=7,
                model_registry_id=11,
                engine_id="demo",
                model="demo-model",
                status="running",
                created_at=utc_now_naive(),
                updated_at=utc_now_naive(),
            )
        )
        session.commit()

    status = transport.status()
    assert status.ok is True
    instances = json.loads(status.active_instances_json)
    assert instances == [
        {
            "node_id": "node-b",
            "engine_row_id": 7,
            "engine_id": "demo",
            "model_registry_id": 11,
            "model": "demo-model",
            "config_signature": "",
            "pid": None,
            "status": "running",
        }
    ]
    engine.dispose()


def test_queue_active_jobs_are_paginated_and_status_is_bounded(monkeypatch, tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue-jobs.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(queue_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(queue_mod, "app_ctx", lambda: _ctx())
    store = EngineInvocationQueueStore(session_factory=session_factory)
    transport = EngineQueueTransport(store=store, response_stream=FakeRedisStream())

    with session_factory() as session:
        _seed_active_node(session, "node-b")
        session.commit()
    for index in range(520):
        store.enqueue(
            request_id=f"req-status-{index}",
            selector_type="objective",
            objective="chat",
            method="generate_completion",
            origin_node_id="node-a",
        )

    jobs = json.loads(transport.status().active_jobs_json)
    page = transport.list_active_jobs(offset=512, limit=16)

    assert len(jobs) == queue_mod.ACTIVE_JOBS_STATUS_LIMIT
    assert jobs[0]["request_id"] == "req-status-0"
    assert len(page) == 8
    assert page[0]["request_id"] == "req-status-512"
    engine.dispose()


def test_queue_enqueue_failure_after_db_write_cancels_row(monkeypatch, tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue-enqueue-fail.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(queue_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(queue_mod, "app_ctx", lambda: _ctx())
    store = EngineInvocationQueueStore(session_factory=session_factory)
    transport = EngineQueueTransport(store=store, response_stream=_FailingPublishStream())

    async def scenario():
        with pytest.raises(RuntimeError, match="queued publish failed"):
            await transport.invoke(
                EngineInvocationTarget(
                    selector_type="objective",
                    objective="chat",
                ),
                EngineInvocationRequest(
                    method="generate_completion",
                    request_id="req-enqueue-fail",
                ),
            )

    asyncio.run(scenario())

    assert store.get_status("req-enqueue-fail")["status"] == "cancelled"
    engine.dispose()


def test_queue_transport_keeps_shared_response_stream_after_invoke(monkeypatch, tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue-close.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(queue_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(queue_mod, "app_ctx", lambda: _ctx())
    monkeypatch.setattr(
        queue_mod.EngineResponseStreamFactory,
        "is_cross_process_provider",
        staticmethod(lambda _provider_type: True),
    )
    stream = _ClosableFakeStream()

    def _resolve_stream(response_stream=None):
        return stream if response_stream is None else response_stream

    monkeypatch.setattr(
        queue_mod,
        "resolve_engine_response_stream",
        _resolve_stream,
    )
    store = EngineInvocationQueueStore(session_factory=session_factory)
    transport = EngineQueueTransport(store=store)

    async def scenario():
        task = asyncio.create_task(
            transport.invoke(
                EngineInvocationTarget(
                    selector_type="objective",
                    objective="chat",
                ),
                EngineInvocationRequest(
                    method="generate_completion",
                    request_id="req-close",
                ),
            )
        )
        while store.get_status("req-close") is None:
            await asyncio.sleep(0.01)
        writer = EngineResponseStreamWriter(
            stream,
            transport._store_stream_key("req-close"),
            node_id="node-b",
        )
        await writer.result({"ok": True})
        await writer.end()
        assert await task == {"ok": True}

    asyncio.run(scenario())

    assert stream.closed == 0
    engine.dispose()


def test_queue_control_targets_only_active_engine_nodes(monkeypatch, tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue-targets.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(queue_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(queue_mod, "app_ctx", lambda: _ctx())

    store = EngineInvocationQueueStore(session_factory=session_factory)
    transport = EngineQueueTransport(store=store, response_stream=FakeRedisStream())

    with session_factory() as session:
        _seed_active_node(session, "node-b")
        session.add(
            EngineNodeInstallRegistry(
                node_id="node-a",
                engine_id="vllm",
                status="installed",
                created_at=utc_now_naive(),
                updated_at=utc_now_naive(),
            )
        )
        session.add(
            EngineNodeInstanceRegistry(
                node_id="node-a",
                engine_row_id=9,
                model_registry_id=13,
                status="running",
                created_at=utc_now_naive(),
                updated_at=utc_now_naive(),
            )
        )
        session.commit()

    assert transport._node_for_engine_install("vllm") is None
    assert transport._nodes_with_instance(engine_registry_id=9) == []

    with session_factory() as session:
        session.add(
            EngineNodeInstallRegistry(
                node_id="node-b",
                engine_id="vllm",
                status="installed",
                created_at=utc_now_naive(),
                updated_at=utc_now_naive(),
            )
        )
        session.commit()

    assert transport._node_for_engine_install("vllm") == "node-b"
    engine.dispose()


def test_queue_control_fanout_runs_all_targets_before_raising():
    class _Transport(EngineQueueTransport):
        def __init__(self):
            pass

        async def _invoke_control_one(
            self,
            method,
            payload,
            *,
            target_node_id=None,
        ):
            del method, payload
            started.append(str(target_node_id))
            if len(started) == 3:
                all_started.set()
            await all_started.wait()
            completed.append(str(target_node_id))
            if target_node_id == "node-b":
                raise RuntimeError("node-b failed")
            return target_node_id

    started: list[str] = []
    completed: list[str] = []
    all_started = asyncio.Event()
    transport = _Transport()

    async def scenario():
        with pytest.raises(RuntimeError, match="node-b failed"):
            await asyncio.wait_for(
                transport._invoke_control_many(
                    "__control_test__",
                    {},
                    target_node_ids=["node-a", "node-b", "node-c"],
                ),
                timeout=1.0,
            )

    asyncio.run(scenario())

    assert started == ["node-a", "node-b", "node-c"]
    assert set(completed) == {"node-a", "node-b", "node-c"}


def test_queue_maintenance_does_not_orphan_hitl_when_disabled(monkeypatch, tmp_path):
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'queue-maintenance.db'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(maintenance_mod, "SessionLocal", session_factory)
    monkeypatch.setattr(maintenance_mod, "app_ctx", lambda: _ctx())
    monkeypatch.setattr(maintenance_mod, "load_active_node_views", lambda **_: [])

    store = EngineInvocationQueueStore(session_factory=session_factory)
    request_id = store.enqueue(
        request_id="req-hitl",
        selector_type="objective",
        objective="chat",
        method="generate_completion",
        origin_node_id="node-a",
    )
    store.claim([request_id], owner="node-b", lease_seconds=60)
    store.release(
        request_id,
        defer_seconds=0,
        requires_origin_hitl=True,
        reason="hitl",
    )
    maintenance = EngineQueueMaintenance(
        node_id="node-b",
        store=store,
        response_stream=FakeRedisStream(),
    )

    asyncio.run(maintenance.run_once())

    assert store.get_status(request_id)["status"] == "pending"
    engine.dispose()


def test_queue_maintenance_does_not_emit_error_when_fail_is_stale(monkeypatch):
    monkeypatch.setattr(maintenance_mod, "app_ctx", lambda: _ctx())
    redis = FakeRedisStream()
    store = SimpleNamespace(
        purge_terminal=lambda *, retention_seconds: None,
        fail=lambda *args, **kwargs: "stale",
    )
    maintenance = EngineQueueMaintenance(
        node_id="node-b",
        store=store,
        response_stream=redis,
        orphan_origin_check_enabled=True,
    )
    maintenance._orphaned_origin_hitl_rows = lambda: [
        {
            "id": "req-race",
            "response_stream_key": "democrai:engine:resp:req-race",
        }
    ]

    asyncio.run(maintenance.run_once())

    assert redis.streams == {}
