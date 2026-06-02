"""
NotificationQueue — stores notifications for offline users and flushes them on reconnect.
"""

import json
from typing import Optional
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.platform.utils.identity import to_optional_int, to_required_int


def _organization_log_value(organization_id: Optional[int]) -> str:
    return "none" if organization_id is None else str(organization_id)


class NotificationQueue:
    """
    Manages pending notifications for users who are currently offline.

    When a background task completes or requires user attention but the user
    is disconnected, the notification is enqueued in the database. When the
    user reconnects, the queue can be flushed to deliver all pending messages.
    """

    def enqueue(
        self,
        user_id: int,
        task_id: str,
        notif_type: str,
        payload: dict,
        organization_id: Optional[int] = None,
    ) -> None:
        """
        Stores a notification in the database for later delivery.

        :param user_id: ID of the recipient user.
        :param task_id: ID of the task related to the notification.
        :param notif_type: Kind of notification (e.g., 'completed', 'failed').
        :param payload: Data dictionary for the notification.
        :param organization_id: Optional organization filtering.
        """
        user_id = to_required_int(user_id, "user_id")
        organization_id = to_optional_int(organization_id)
        db = self._get_db()
        try:
            from democrai.core.application.tasks.models import PendingNotificationRecord

            record = PendingNotificationRecord(
                user_id=user_id,
                organization_id=organization_id,
                task_id=task_id,
                type=notif_type,
                payload=json.dumps(payload, default=str),
            )
            db.add(record)
            db.commit()
            app_ctx().logger.info(
                f"[NotificationQueue] Queued '{notif_type}' for user '{user_id}' org '{_organization_log_value(organization_id)}' (task {task_id})"
            )
        except Exception as e:
            db.rollback()
            app_ctx().logger.error(f"[NotificationQueue] Failed to enqueue: {e}")
        finally:
            db.close()

    def flush(
        self, user_id: int, send_fn, organization_id: Optional[int] = None
    ) -> int:
        """
        Delivers all pending notifications for a user and marks them as delivered.

        :param user_id: ID of the user to flush notifications for.
        :param send_fn: A callable that accepts a message dict and sends it to the user.
        :param organization_id: Optional organization filtering.
        :return: The number of notifications successfully flushed.
        """
        db = self._get_db()
        user_id = to_required_int(user_id, "user_id")
        organization_id = to_optional_int(organization_id)
        delivered = 0
        try:
            from democrai.core.application.tasks.models import PendingNotificationRecord

            pending = (
                db.query(PendingNotificationRecord)
                .filter(
                    PendingNotificationRecord.user_id == user_id,
                    PendingNotificationRecord.organization_id == organization_id,
                    PendingNotificationRecord.delivered == False,
                )
                .order_by(PendingNotificationRecord.created_at)
                .all()
            )

            for notif in pending:
                try:
                    payload = json.loads(notif.payload)
                    # Build the appropriate A2UI message
                    message = self._build_message(notif.type, notif.task_id, payload)
                    send_fn(message)
                    notif.delivered = True
                    delivered += 1
                except Exception as e:
                    app_ctx().logger.error(
                        f"[NotificationQueue] Failed to deliver notification {notif.id}: {e}"
                    )

            db.commit()
            if delivered:
                app_ctx().logger.info(
                    f"[NotificationQueue] Flushed {delivered} notifications for user '{user_id}' org '{_organization_log_value(organization_id)}'"
                )
        except Exception as e:
            db.rollback()
            app_ctx().logger.error(f"[NotificationQueue] Flush error: {e}")
        finally:
            db.close()

        return delivered

    def _build_message(self, notif_type: str, task_id: str, payload: dict) -> dict:
        """Convert a stored notification into an A2UI message."""
        if notif_type == "completed":
            return {
                "backgroundTaskCompleted": {
                    "taskId": task_id,
                    "label": payload.get("label", ""),
                    "result": payload.get("result"),
                    "updatedAt": payload.get("updatedAt"),
                    "updatedAtLabel": payload.get("updatedAtLabel"),
                }
            }
        elif notif_type == "failed":
            return {
                "backgroundTaskError": {
                    "taskId": task_id,
                    "label": payload.get("label", ""),
                    "error": payload.get("error", "Unknown error"),
                    "updatedAt": payload.get("updatedAt"),
                    "updatedAtLabel": payload.get("updatedAtLabel"),
                }
            }
        elif notif_type == "confirmation":
            return {
                "backgroundTaskConfirmation": {
                    "taskId": task_id,
                    "label": payload.get("label", ""),
                    "surfaceId": payload.get("surfaceId"),
                    "components": payload.get("components", []),
                    "updatedAt": payload.get("updatedAt"),
                    "updatedAtLabel": payload.get("updatedAtLabel"),
                }
            }
        elif notif_type == "event":
            return {"eventNotification": payload}
        else:
            return {"backgroundTaskUpdate": {"taskId": task_id, **payload}}

    def _get_db(self):
        ctx = app_ctx()
        if ctx.db:
            return ctx.db.get_session()
        else:
            from democrai.core.infrastructure.database import _default_SessionLocal

            return _default_SessionLocal()
