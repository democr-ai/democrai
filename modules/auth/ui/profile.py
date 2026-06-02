from __future__ import annotations

from datetime import datetime
from typing import Any

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.decorators import render_hook_slot


@render_hook_slot(
    "profile.recommendations",
    optional=True,
    description="Cards shown below the authenticated user profile summary.",
)
def register_profile_recommendations_hook():
    return None


def _session_user_id(session: dict) -> int | None:
    user = session.get("user") if isinstance(session, dict) else None
    if not isinstance(user, dict):
        return None
    try:
        return int(user.get("id"))
    except (TypeError, ValueError):
        return None


def _format_created_at(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    text = str(value or "").strip()
    if not text:
        return "-"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
        try:
            return datetime.strptime(text.replace("Z", ""), fmt).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            continue
    return text


def _profile_summary(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "username": str(user.get("username") or "-"),
        "email": str(user.get("email") or "-"),
        "role": str(user.get("role") or "-"),
        "organization": str(user.get("organization_name") or "-"),
        "created_at": _format_created_at(user.get("created_at")),
    }


async def render(_params: dict, session: dict) -> Any:
    builder = sdk.ui.load("utils/ui/yaml/profile")
    user_id = _session_user_id(session)

    if user_id is None:
        builder.set_data("auth_profile/user", {})
        builder.set_data("auth_profile/summary", _profile_summary({}))
        return builder

    user = sdk.models.users.view(user_id) or {}
    builder.set_data("auth_profile/user", user)
    builder.set_data("auth_profile/summary", _profile_summary(user))

    hook_components = await sdk.hooks.resolve_render_hook(
        "profile.recommendations",
        params={"user_id": user_id},
        session=session,
    )
    hook_ids: list[str] = []
    for component in hook_components:
        builder.add(component)
        if getattr(component, "id", None):
            hook_ids.append(component.id)

    recommendations = builder.get_component("auth_profile_recommendations")
    if recommendations is not None:
        recommendations.set_children(hook_ids)

    empty_state = builder.get_component("auth_profile_recommendations_empty")
    if empty_state is not None:
        empty_state.set_property("visible", not bool(hook_ids))

    return builder
