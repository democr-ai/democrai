from __future__ import annotations

from democrai.sdk.decorators import notification_center_view


@notification_center_view("/system/notifications", priority=0)
def register_notification_center_view():
    """Register the system module notification center page."""
    return None
