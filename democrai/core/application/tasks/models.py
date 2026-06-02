"""
Database models for background tasks and pending notifications.
Uses the same Base as core.infrastructure.database.models for unified schema management.
"""

from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean
from democrai.core.infrastructure.database.models import Base
from democrai.core.platform.utils.timezone import utc_now_naive


class BackgroundTaskRecord(Base):
    """Persistent record for a background task."""

    __tablename__ = "background_tasks"

    id = Column(String(36), primary_key=True)  # UUID
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    task_key = Column(String(500), nullable=True, index=True)
    module = Column(String(255), nullable=False)
    label = Column(String(500), nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    # Status values: pending, running, completed, failed, interrupted, waiting_confirmation
    progress = Column(Float, default=0.0)
    checkpoint = Column(Text, nullable=True)  # JSON-serialized checkpoint data
    result = Column(Text, nullable=True)  # JSON-serialized result
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f"<BackgroundTask(id='{self.id}', label='{self.label}', status='{self.status}')>"


class PendingNotificationRecord(Base):
    """Queued notification for an offline user."""

    __tablename__ = "pending_notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    task_id = Column(String(36), nullable=False)
    type = Column(String(50), nullable=False)  # completed, failed, confirmation
    payload = Column(Text, nullable=False)  # JSON-serialized payload
    created_at = Column(DateTime, default=utc_now_naive)
    delivered = Column(Boolean, default=False)

    def __repr__(self):
        return f"<PendingNotification(user='{self.user_id}', type='{self.type}')>"
