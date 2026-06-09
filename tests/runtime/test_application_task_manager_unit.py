from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy.models import AccessResource, AccessSubject
import democrai.core.application.tasks.task_manager as mod


def _access_rule(subject_kind: str, subject: str, resource_type: str, operation: str, target: str):
    return AccessManifestRule(
        subject=AccessSubject.create(subject_kind, subject),
        resource=AccessResource.create(
            resource_type=resource_type,
            operation=operation,
            target=target,
        ),
    )


class _Logger:
    def __init__(self):
        self.infos = []
        self.warns = []
        self.errors = []

    def info(self, msg, *_a, **_k):
        self.infos.append(msg)

    def warning(self, msg, *_a, **_k):
        self.warns.append(msg)

    def error(self, msg, *_a, **_k):
        self.errors.append(msg)


def _ctx(**kwargs):
    logger = kwargs.pop("logger", _Logger())
    base = {
        "logger": logger,
        "db": None,
        "connection_registry": None,
        "redis_task_bridge": None,
        "modules": None,
    }
    base.update(kwargs)
    return SimpleNamespace(**base)


def test_task_manager_storage_paths(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: _ctx(logger=logger))
    manager = mod.TaskManager()
    assert manager._send_to_user(1, None, {"x": 1}) is False

    class _Registry:
        def __init__(self, conns):
            self.conns = conns

        def get_connections(self, *_a, **_k):
            return self.conns

    bridge_calls = []
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: _ctx(
            logger=logger,
            connection_registry=_Registry([]),
            redis_task_bridge=SimpleNamespace(publish=lambda *a: bridge_calls.append(a)),
        ),
    )
    assert manager._send_to_user(1, 2, {"m": 1}) is True
    assert bridge_calls

    class _Bus:
        def __init__(self, boom=False):
            self.boom = boom
            self.sent = []

        def send(self, client_id, message):
            if self.boom:
                raise RuntimeError("send-fail")
            self.sent.append((client_id, message))

    bus_ok = _Bus()
    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: _ctx(
            logger=logger,
            connection_registry=_Registry([(bus_ok, "c1"), (_Bus(boom=True), "c2")]),
        ),
    )
    assert manager._send_to_user(1, None, {"a": 1}) is True
    assert bus_ok.sent and logger.errors

    class _NQ:
        def __init__(self):
            self.enqueued = []

        def _build_message(self, notif_type, task_id, payload):
            return {"built": (notif_type, task_id, payload)}

        def enqueue(self, *args):
            self.enqueued.append(args)

    nq = _NQ()
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.tasks.notification_queue",
        SimpleNamespace(NotificationQueue=lambda: nq),
    )
    monkeypatch.setattr(manager, "_send_to_user", lambda *_a, **_k: False)
    manager._notify_user(7, 8, "t1", "progress", {"p": 1})
    assert nq.enqueued

    db_obj = object()
    monkeypatch.setattr(mod, "app_ctx", lambda: _ctx(logger=logger, db=SimpleNamespace(get_session=lambda: db_obj)))
    assert manager._get_db() is db_obj


def test_task_manager_persist_task(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: _ctx(logger=logger))

    class _DB:
        def __init__(self, row=None, boom=False):
            self.row = row
            self.boom = boom
            self.added = []
            self.commits = 0
            self.rollbacks = 0
            self.closed = 0

        def get(self, *_a, **_k):
            return self.row

        def add(self, obj):
            self.added.append(obj)

        def commit(self):
            if self.boom:
                raise RuntimeError("db-fail")
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed += 1

    class _Row:
        pass

    class _Record:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.tasks.models",
        SimpleNamespace(BackgroundTaskRecord=_Record),
    )
    task = mod.BackgroundTask(
        id="t1",
        user_id=1,
        organization_id=2,
        task_key="k",
        module="m",
        label="L",
        status="running",
        progress=0.2,
        checkpoint={"a": 1},
        result={"r": 1},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    manager = mod.TaskManager()

    row = _Row()
    db_update = _DB(row=row)
    monkeypatch.setattr(manager, "_get_db", lambda: db_update)
    manager._persist_task(task)
    assert row.status == "running" and db_update.commits == 1 and db_update.closed == 1

    db_create = _DB(row=None)
    monkeypatch.setattr(manager, "_get_db", lambda: db_create)
    manager._persist_task(task)
    assert db_create.added and db_create.commits == 1 and db_create.closed == 1

    db_fail = _DB(row=row, boom=True)
    monkeypatch.setattr(manager, "_get_db", lambda: db_fail)
    manager._persist_task(task)
    assert db_fail.rollbacks == 1 and db_fail.closed == 1 and logger.errors


@pytest.mark.asyncio
async def test_task_manager_runtime_paths(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: _ctx(logger=logger, modules=SimpleNamespace(get_module=lambda _n: None)))
    monkeypatch.setattr(mod, "req_ctx", lambda: (_ for _ in ()).throw(LookupError()))
    assert mod._capture_request_context() is None

    built = mod._build_task_request_context(task_id="t", user_id=9, organization_id=None, current=None)
    assert built.request_id == "task:t" and built.user == 9
    assert mod._task_execution_context(module_name="core", request_context=built).__class__.__name__ == "nullcontext"
    with pytest.raises(RuntimeError):
        mod._task_execution_context(module_name="", request_context=built)

    class _CM:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(
        mod,
        "app_ctx",
        lambda: _ctx(
            logger=logger,
            modules=SimpleNamespace(
                get_module=lambda _n: SimpleNamespace(
                    access=[_access_rule("module", "demo", "filesystem", "read", "/tmp/demo")]
                )
            ),
        ),
    )
    guard_kwargs = {}
    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.infrastructure.sandbox.process_guard",
        SimpleNamespace(
            process_guard_context=lambda **kwargs: guard_kwargs.update(kwargs) or _CM()
        ),
    )
    inherited_access = (
        _access_rule("module", "demo", "filesystem", "read", "/tmp/demo"),
        _access_rule("module", "demo", "filesystem", "create", "/tmp/models"),
    )
    inherited_state = {
        "subject": "demo",
        "subject_kind": "module",
        "access": inherited_access,
        "allowed_imports": ["json"],
        "allowed_subprocess_commands": ["tool"],
        "allow_subprocess": True,
        "allow_fork": False,
    }
    with mod._task_execution_context(
        module_name="demo",
        request_context=built,
        inherited_sandbox_state=inherited_state,
    ):
        pass
    assert tuple(guard_kwargs["access"]) == inherited_access
    assert guard_kwargs["include_runtime_access"] is True
    assert guard_kwargs["inherit_parent_access"] is False
    assert guard_kwargs["allow_subprocess"] is True

    manager = mod.TaskManager()
    monkeypatch.setattr(manager, "_persist_task", lambda *_a, **_k: None)
    monkeypatch.setattr(manager, "_send_to_user", lambda *_a, **_k: True)
    monkeypatch.setattr(manager, "_notify_user", lambda *_a, **_k: None)
    monkeypatch.setattr(mod, "uuid4", lambda: "t-1")
    monkeypatch.setattr(mod, "_capture_request_context", lambda: None)
    monkeypatch.setattr(mod, "set_req_ctx", lambda _ctx: "tok")
    monkeypatch.setattr(mod, "reset_req_ctx", lambda _tok: None)
    monkeypatch.setattr(mod, "utc_now_naive", lambda: datetime(2026, 1, 1))
    monkeypatch.setattr(mod, "_task_execution_context", lambda **_k: _CM())

    async def _ok():
        return {"ok": True}

    task_id = await manager.submit(1, _ok(), "LBL", module="core")
    assert task_id == "t-1"
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert manager._tasks["t-1"].status == "completed"

    monkeypatch.setattr(mod, "uuid4", lambda: "t-ext")
    t_ext, created = await manager.submit_external(3, "External", module="m")
    assert created is True and t_ext == "t-ext"

    await manager.update_progress("t-ext", 1.4, checkpoint={"x": 1}, label="L2")
    assert manager._tasks["t-ext"].progress == 1.0
    assert manager._tasks["t-ext"].label == "L2"
    await manager.emit_progress("t-ext", 0.5, label="live line")
    assert await manager.complete_external("missing", {}) is False
    assert await manager.complete_external("t-ext", {"r": 1}) is True
    assert await manager.fail_external("missing", "e") is False
    with pytest.raises(RuntimeError, match="task_error_required"):
        await manager.fail_external("t-ext", "")
    assert await manager.fail_external("t-ext", "e") is True

    confirm_task = asyncio.create_task(
        manager.request_confirmation("t-ext", [{"type": "text"}])
    )
    await asyncio.sleep(0)
    manager._tasks["t-ext"]._confirmation_future.set_result({"confirm": True})
    assert await confirm_task == {"confirm": True}
    with pytest.raises(ValueError):
        await manager.request_confirmation("unknown", [])

    await manager.respond_confirmation("unknown", {"x": 1})
    manager._tasks["t-ext"]._confirmation_future = asyncio.get_event_loop().create_future()
    await manager.respond_confirmation("t-ext", {"ok": 1})
    assert manager._tasks["t-ext"]._confirmation_future.done()

    class _AsyncTask:
        def __init__(self, done=False):
            self._done = done
            self.cancelled = False

        def done(self):
            return self._done

        def cancel(self):
            self.cancelled = True

    manager._tasks["t-ext"]._asyncio_task = _AsyncTask(done=False)
    assert await manager.cancel("t-ext") is True
    manager._tasks["t-ext"]._asyncio_task = _AsyncTask(done=True)
    assert await manager.cancel("t-ext") is False


def test_task_manager_queries_and_recovery(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(mod, "app_ctx", lambda: _ctx(logger=logger))
    manager = mod.TaskManager()
    manager._tasks["t2"] = SimpleNamespace(
        id="t2",
        user_id=3,
        organization_id=None,
        task_key="k.x",
        status="pending",
        created_at=datetime(2026, 1, 1),
        to_dict=lambda: {"id": "t2"},
    )
    manager._tasks["t3"] = SimpleNamespace(
        id="t3",
        user_id=3,
        organization_id=None,
        task_key="k.y",
        status="completed",
        created_at=datetime(2026, 1, 2),
        to_dict=lambda: {"id": "t3"},
    )
    assert manager._find_active_task_by_key("k.x", None).id == "t2"
    assert manager.get_tasks_by_key("k.x", None)
    assert manager.get_tasks_by_key_prefix("k.", None)
    assert manager.get_user_tasks(3, None)
    assert manager.get_user_tasks_serialized(3, None)[0]["id"] == "t3"
    task = mod.BackgroundTask(id="tid", user_id=3, module="core", label="L")
    assert task.to_dict()["organizationId"] is None

    class _RowsQuery:
        def __init__(self, rows):
            self.rows = rows

        def filter(self, *_a, **_k):
            return self

        def all(self):
            return self.rows

    class _DB:
        def __init__(self, rows=None, exc=None):
            self.rows = rows or []
            self.exc = exc
            self.commits = 0
            self.rollbacks = 0
            self.closed = 0

        def query(self, *_a, **_k):
            if self.exc:
                raise self.exc
            return _RowsQuery(self.rows)

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed += 1

    class _ModelStatus:
        @staticmethod
        def in_(_vals):
            return True

    class _Record:
        status = _ModelStatus()

        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    monkeypatch.setitem(
        __import__("sys").modules,
        "democrai.core.application.tasks.models",
        SimpleNamespace(BackgroundTaskRecord=_Record),
    )
    db_rows = [
        _Record(
            id="r1",
            user_id=1,
            organization_id=None,
            task_key="rk",
            module="m",
            label="L",
            status="running",
            progress=0.5,
            checkpoint=json.dumps({"a": 1}),
            created_at=datetime(2026, 1, 1),
        )
    ]
    monkeypatch.setattr(manager, "_get_db", lambda: _DB(rows=db_rows))
    assert manager.recover_from_db() == 1
    assert manager._tasks["r1"].status == "interrupted"

    monkeypatch.setattr(
        manager,
        "_get_db",
        lambda: _DB(exc=OperationalError("x", {}, Exception("no such table: background_tasks"))),
    )
    assert manager.recover_from_db() == 0
