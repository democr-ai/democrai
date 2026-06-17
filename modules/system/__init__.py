from __future__ import annotations

from modules.system import notification_center as _notification_center  # noqa: F401
from modules.system import profile_hooks as _profile_hooks  # noqa: F401


def init(_context: dict | None = None) -> dict:
    return {
        "sidebar_entries": [
            {
                "id": "system",
                "label": "System Services",
                "icon": "ric.settings-2-line",
                "priority": 50,
                "position": "top",
                "action": {
                    "name": "nav",
                    "context": {"type": "nav", "path": "/system/index"},
                },
                "active_path": "/system",
            }
        ]
    }
