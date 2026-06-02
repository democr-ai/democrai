from __future__ import annotations

from types import SimpleNamespace

import democrai.core.application.tasks.notification_queue as notif_mod


class _Logger:
    def __init__(self):
        self.infos = []
        self.errors = []

    def info(self, message, *args, **kwargs):
        self.infos.append(message)

    def error(self, message, *args, **kwargs):
        self.errors.append(message)


class _Query:
    def __init__(self, pending=None):
        self.pending = pending or []

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return self.pending


class _DB:
    def __init__(self, pending=None, fail_add=False, fail_query=False):
        self.pending = pending or []
        self.fail_add = fail_add
        self.fail_query = fail_query
        self.added = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def add(self, row):
        if self.fail_add:
            raise RuntimeError("add fail")
        self.added.append(row)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True

    def query(self, model):
        if self.fail_query:
            raise RuntimeError("query fail")
        return _Query(self.pending)


def test_notification_queue_enqueue_flush_and_message_building(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(notif_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, db=None))

    models_mod = __import__("democrai.core.application.tasks.models", fromlist=["PendingNotificationRecord"])
    records = []

    class _Record:
        def __init__(self, **kwargs):
            records.append(kwargs)
            self.__dict__.update(kwargs)

    monkeypatch.setattr(models_mod, "PendingNotificationRecord", _Record)

    db = _DB()
    monkeypatch.setattr(notif_mod.NotificationQueue, "_get_db", lambda self: db)
    queue = notif_mod.NotificationQueue()
    queue.enqueue(1, "t1", "completed", {"ok": True}, 1)
    assert records[-1]["organization_id"] == 1
    assert db.committed is True
    assert logger.infos

    sent = []
    pending = [
        SimpleNamespace(id=1, payload='{"label":"Done"}', type="completed", task_id="t1", delivered=False),
        SimpleNamespace(id=2, payload='{"label":"Fail","error":"boom"}', type="failed", task_id="t2", delivered=False),
        SimpleNamespace(id=3, payload='{"surfaceId":"s1","components":[1]}', type="confirmation", task_id="t3", delivered=False),
        SimpleNamespace(id=4, payload='{"kind":"event"}', type="event", task_id="t4", delivered=False),
        SimpleNamespace(id=5, payload='{"x":1}', type="other", task_id="t5", delivered=False),
        SimpleNamespace(id=6, payload='{bad', type="completed", task_id="t6", delivered=False),
    ]
    class _FilterRecord:
        user_id = "user_id"
        organization_id = "organization_id"
        delivered = "delivered"
        created_at = "created_at"

    monkeypatch.setattr(models_mod, "PendingNotificationRecord", _FilterRecord)
    db = _DB(pending=pending)
    monkeypatch.setattr(notif_mod.NotificationQueue, "_get_db", lambda self: db)
    delivered = queue.flush(1, lambda message: sent.append(message), 1)
    assert delivered == 5
    assert pending[0].delivered is True
    assert sent[0]["backgroundTaskCompleted"]["taskId"] == "t1"
    assert sent[1]["backgroundTaskError"]["taskId"] == "t2"
    assert sent[2]["backgroundTaskConfirmation"]["taskId"] == "t3"
    assert sent[3] == {"eventNotification": {"kind": "event"}}
    assert sent[4]["backgroundTaskUpdate"]["taskId"] == "t5"
    assert logger.errors


def test_notification_queue_error_and_db_fallback_paths(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(notif_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, db=SimpleNamespace(get_session=lambda: "session")))

    queue = notif_mod.NotificationQueue()
    assert queue._get_db() == "session"

    infra_mod = __import__("democrai.core.infrastructure.database", fromlist=["_default_SessionLocal"])
    monkeypatch.setattr(infra_mod, "_default_SessionLocal", lambda: "default-session")
    monkeypatch.setattr(notif_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, db=None))
    assert queue._get_db() == "default-session"

    db = _DB(fail_add=True)
    monkeypatch.setattr(notif_mod.NotificationQueue, "_get_db", lambda self: db)
    queue.enqueue(1, "t1", "completed", {"ok": True})
    assert db.rolled_back is True

    db = _DB(fail_query=True)
    monkeypatch.setattr(notif_mod.NotificationQueue, "_get_db", lambda self: db)
    assert queue.flush(1, lambda message: None) == 0
    assert db.rolled_back is True

    db_empty = _DB(pending=[])
    monkeypatch.setattr(notif_mod.NotificationQueue, "_get_db", lambda self: db_empty)
    assert queue.flush(1, lambda message: None) == 0
    assert db_empty.committed is True
    assert db_empty.closed is True


def test_notification_queue_tolerates_minimal_db_session_stubs(monkeypatch):
    logger = _Logger()
    monkeypatch.setattr(notif_mod, "app_ctx", lambda: SimpleNamespace(logger=logger, db=None))

    class _MinimalDB:
        def rollback(self):
            return None

        def close(self):
            return None

    monkeypatch.setattr(notif_mod.NotificationQueue, "_get_db", lambda self: _MinimalDB())
    queue = notif_mod.NotificationQueue()
    queue.enqueue(1, "t1", "completed", {"ok": True})

    assert any("Failed to enqueue" in message for message in logger.errors)
