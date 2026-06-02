from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk


def _session_user_id(session: dict) -> int | None:
    user = session.get("user") if isinstance(session, dict) else None
    if not isinstance(user, dict):
        return None
    try:
        return int(user.get("id"))
    except (TypeError, ValueError):
        return None


async def render(_params: dict, session: dict):
    builder = sdk.ui.load("utils/ui/yaml/profile_edit")
    user_id = _session_user_id(session)
    user = sdk.models.users.view(user_id) if user_id is not None else {}
    builder.set_data(
        "auth_profile/edit_values",
        {
            "username": str((user or {}).get("username") or ""),
            "email": str((user or {}).get("email") or ""),
        },
    )
    return builder
