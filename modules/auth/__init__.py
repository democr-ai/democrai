from __future__ import annotations

from democrai.sdk.decorators import guest_page, home_page


@home_page("/auth/profile", priority=100)
def register_auth_profile_home():
    return None


@guest_page("/auth/login", priority=100)
def register_auth_login_guest():
    return None


def init(_context: dict | None = None) -> dict:
    return {
        "sidebar_entries": [
            {
                "id": "profile",
                "label": "Profile",
                "icon": "ric.function-ai-line",
                "position": "top",
                "action": {"name": "nav", "context": {"path": "/auth/profile"}},
                "active_path": "/auth/profile",
            },
            {
                "id": "auth",
                "label": "Login",
                "icon": "ric.logout-box-line",
                "position": "bottom",
                "action": {"name": "nav", "context": {"path": "/auth/index"}},
                "guest_action": {"name": "nav", "context": {"path": "/auth/login"}},
                "authenticated_label": "Logout",
                "authenticated_action": {"name": "logout", "context": {}},
                "active_path": "/auth/logout",
            },
        ]
    }
