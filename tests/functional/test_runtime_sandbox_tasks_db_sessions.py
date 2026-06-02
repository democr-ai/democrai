from __future__ import annotations

import asyncio
import contextlib
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from democrai.core.application.auth.roles import ROLE_LEVEL_ORGANIZATION
from democrai.core.application.auth.roles import ROLE_LEVEL_SUPER
from democrai.core.application.auth.roles import ROLE_LEVEL_USER
from democrai.core.application.models.base import BaseCoreModel
from democrai.core.application.models.context import CoreModelContext
from democrai.core.application.session.service import SessionService
from democrai.core.application.tasks.models import BackgroundTaskRecord
from democrai.core.application.access_policy import parse_access_manifest_rules
from democrai.core.infrastructure.database.session_store import SessionStore
from democrai.core.runtime.foundation.app import app_ctx

sys.modules.setdefault(
    "democrai.core.infrastructure.network.policy_guard",
    SimpleNamespace(network_policy_context=lambda **_kwargs: contextlib.nullcontext()),
)

from democrai.core.application.tasks.task_manager import TaskManager
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context


def test_functional_sandbox_python_level(tmp_path: Path):
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir(parents=True, exist_ok=True)
    allowed_file = allowed_dir / "ok.txt"
    allowed_file.write_text("ok", encoding="utf-8")
    access = parse_access_manifest_rules(
        {
            "access": [
                {
                    "resource_type": "filesystem",
                    "operation": "read",
                    "target": str(allowed_dir),
                }
            ]
        },
        subject_type="module",
        subject_name="functional.sandbox",
    )

    with process_guard_context(
        subject="functional.sandbox",
        access=access,
        allow_subprocess=False,
    ):
        assert allowed_file.read_text(encoding="utf-8") == "ok"
        try:
            Path("/var/lib/democrai_guard_probe_denied").read_text(encoding="utf-8")
            assert False, "expected filesystem deny outside allowed paths"
        except PermissionError as exc:
            assert "sandbox_filesystem_denied" in str(exc)

def test_functional_task_manager_background_and_db_persistence(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}")
    BackgroundTaskRecord.__table__.create(bind=engine, checkfirst=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    ctx = app_ctx()
    previous_db = getattr(ctx, "db", None)
    previous_logger = getattr(ctx, "logger", None)
    previous_registry = getattr(ctx, "connection_registry", None)
    previous_bridge = getattr(ctx, "redis_task_bridge", None)
    ctx.db = SimpleNamespace(get_session=lambda: SessionLocal())
    ctx.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )
    ctx.connection_registry = None
    ctx.redis_task_bridge = None

    async def _scenario():
        manager = TaskManager()

        async def _job():
            await asyncio.sleep(0.01)
            return {"done": True, "steps": 1}

        task_id = await manager.submit(
            user_id=101,
            organization_id=55,
            task_or_coro=_job(),
            label="Functional background task",
            module="core",
            task_key="functional.task",
        )

        timeout_at = time.monotonic() + 3.0
        while time.monotonic() < timeout_at:
            task = manager.get_task(task_id)
            if task is not None and task.status in {"completed", "failed", "interrupted"}:
                break
            await asyncio.sleep(0.01)

        task = manager.get_task(task_id)
        assert task is not None
        assert task.status == "completed"
        assert task.result == {"done": True, "steps": 1}

        with SessionLocal() as session:
            row = session.query(BackgroundTaskRecord).filter(BackgroundTaskRecord.id == task_id).first()
            assert row is not None
            assert row.user_id == 101
            assert row.organization_id == 55
            assert row.status == "completed"
            assert float(row.progress or 0.0) == 1.0

    try:
        asyncio.run(_scenario())
    finally:
        ctx.db = previous_db
        ctx.logger = previous_logger
        ctx.connection_registry = previous_registry
        ctx.redis_task_bridge = previous_bridge


def test_functional_db_scope_filters_user_and_organization_are_automatic(tmp_path: Path):
    Base = declarative_base()

    class _Record(Base):
        __tablename__ = "functional_scope_records"
        id = Column(Integer, primary_key=True, autoincrement=True)
        user_id = Column(Integer, nullable=False, index=True)
        organization_id = Column(Integer, nullable=False, index=True)
        label = Column(String(64), nullable=False)

    class _RecordModel(BaseCoreModel):
        name = "functional_scope_records"
        sqlalchemy_model = _Record

        def serialize_row(self, item):
            return {
                "id": int(item.id),
                "user_id": int(item.user_id),
                "organization_id": int(item.organization_id),
                "label": str(item.label),
            }

        def filters_model(self):
            return [{"field": "label", "type": "text"}]

        def table_model(self):
            return [{"field": "id", "type": "int"}, {"field": "label", "type": "str"}]

        def create(self, payload):
            raise NotImplementedError

        def update(self, entity_id, payload):
            raise NotImplementedError

        def delete(self, entity_id):
            raise NotImplementedError

    engine = create_engine(f"sqlite:///{tmp_path / 'scope.db'}")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        session.add_all(
            [
                _Record(user_id=1, organization_id=10, label="u1-org10"),
                _Record(user_id=2, organization_id=10, label="u2-org10"),
                _Record(user_id=3, organization_id=20, label="u3-org20"),
            ]
        )
        session.commit()

    user_model = _RecordModel(
        CoreModelContext(
            user_id=1,
            organization_id=10,
            access_level=ROLE_LEVEL_USER,
            module_name="functional",
            session={},
        )
    )
    org_model = _RecordModel(
        CoreModelContext(
            user_id=999,
            organization_id=10,
            access_level=ROLE_LEVEL_ORGANIZATION,
            module_name="functional",
            session={},
        )
    )
    super_model = _RecordModel(
        CoreModelContext(
            user_id=999,
            organization_id=999,
            access_level=ROLE_LEVEL_SUPER,
            module_name="functional",
            session={},
        )
    )
    for model in (user_model, org_model, super_model):
        model._session_factory = lambda _session_factory=SessionLocal: _session_factory

    user_rows = user_model.list(filters={"user_id": 2, "label": "org10"})["rows"]
    org_rows = org_model.list(filters={"label": "org10"})["rows"]
    super_rows = super_model.list(filters={})["rows"]

    assert [row["user_id"] for row in user_rows] == [1]
    assert sorted(row["user_id"] for row in org_rows) == [1, 2]
    assert sorted(row["user_id"] for row in super_rows) == [1, 2, 3]


def test_functional_concurrent_sessions_keep_isolated_contexts():
    ctx = app_ctx()
    previous_setup_mode = getattr(ctx, "setup_mode", False)
    previous_config = getattr(ctx, "config", None)
    previous_logger = getattr(ctx, "logger", None)

    ctx.setup_mode = True
    ctx.config = {}
    ctx.logger = SimpleNamespace(
        info=lambda *a, **k: None,
        debug=lambda *a, **k: None,
        warning=lambda *a, **k: None,
        error=lambda *a, **k: None,
    )

    try:
        store = SessionStore()
        service = SessionService(store)

        errors: list[str] = []

        def _worker(user_id: int):
            session_key = f"session-{user_id}"
            session = service.get_or_create(None, "Guest", session_key=session_key)
            session["current_path"] = f"/module/{user_id}/index"
            session["custom_ctx"] = {"user": user_id}
            key = service._storage_key_for_identity(None, session_key)
            service.persist(key)
            loaded = service.get_or_create(None, "Guest", session_key=session_key)
            if loaded.get("custom_ctx", {}).get("user") != user_id:
                errors.append(f"context mismatch for {user_id}")
            if loaded.get("current_path") != f"/module/{user_id}/index":
                errors.append(f"path mismatch for {user_id}")

        threads = [threading.Thread(target=_worker, args=(user_id,)) for user_id in range(1, 9)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)

        assert not errors, "; ".join(errors)
        assert sorted(store.identity_store.keys()) == [
            f"session-{i}" for i in range(1, 9)
        ]
    finally:
        ctx.setup_mode = previous_setup_mode
        ctx.config = previous_config
        ctx.logger = previous_logger
