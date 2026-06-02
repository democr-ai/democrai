from __future__ import annotations


def init(_context: dict | None = None) -> dict:
    return {
        "sidebar_entries": [
            {
                "id": "components",
                "label": "Components",
                "icon": "ric.stack-line",
                "position": "top",
                "action": {"name": "nav", "context": {"path": "/components/index"}},
                "active_path": "/components",
            }
        ]
    }
