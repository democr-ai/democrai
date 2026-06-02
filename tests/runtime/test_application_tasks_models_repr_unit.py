from __future__ import annotations

from democrai.core.application.tasks.models import BackgroundTaskRecord
from democrai.core.application.tasks.models import PendingNotificationRecord


def test_tasks_models_repr_branches():
    task = BackgroundTaskRecord(id="t-1", user_id=1, organization_id=None, module="core", label="Run", status="running")
    notif = PendingNotificationRecord(user_id=1, organization_id=None, task_id="t-1", type="completed", payload="{}")

    assert "BackgroundTask" in repr(task)
    assert "t-1" in repr(task)
    assert "PendingNotification" in repr(notif)
    assert "completed" in repr(notif)
