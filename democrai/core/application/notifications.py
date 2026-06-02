from __future__ import annotations

from typing import Any

from democrai.core.application.services import external_access
from democrai.core.infrastructure.database.access_policy import (
    get_pending_access_requests,
)
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.registry import notification_center_view_registry


def notification_center_view_path() -> str:
    """Return the registered notification center route, if any."""
    return notification_center_view_registry.get_path()


def can_manage_notifications(session: dict[str, Any]) -> bool:
    user = session.get("user") or {}
    user_permissions = user.get("permissions")
    if not isinstance(user_permissions, list):
        user_permissions = []
    return external_access.can_manage_external_access(
        user_id=to_optional_int(user.get("id")),
        role=user.get("role"),
        access_level=to_optional_int(user.get("access_level")),
        organization_id=to_optional_int(user.get("organization_id")),
        permissions=user_permissions,
    )


def list_notifications(session: dict[str, Any]) -> list[dict[str, Any]]:
    if not can_manage_notifications(session):
        return []
    return get_pending_access_requests()


def pending_notification_count(session: dict[str, Any]) -> int:
    return len(list_notifications(session))


def notification_state_values(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "/core/notifications/pending_count": pending_notification_count(session),
        "/core/notifications/view_path": notification_center_view_path(),
    }


def apply_external_access_decision(ctx: dict[str, Any]) -> None:
    subject_type = str(ctx.get("subject_type") or "module").strip() or "module"
    subject_name = str(ctx.get("subject_name") or ctx.get("module_name") or "").strip()
    target = str(ctx.get("target") or "").strip()
    request_session_key = str(ctx.get("request_session_key") or "").strip() or None
    decision = str(ctx.get("decision") or "deny").strip().lower()
    resource_type = str(
        ctx.get("resource_type") or external_access.EXTERNAL_RESOURCE_NETWORK
    ).strip()
    operation = str(ctx.get("operation") or "").strip()

    if (
        not subject_name
        or not operation
        or not target
        or decision not in {"session", "permanent", "deny"}
    ):
        raise ValueError("invalid_external_access_decision_payload")

    if decision == "session":
        external_access.approve_for_session(
            resource_type=resource_type,
            operation=operation,
            subject_type=subject_type,
            subject_name=subject_name,
            target=target,
            session_key=request_session_key,
        )
        return
    if decision == "permanent":
        external_access.approve_permanently(
            resource_type=resource_type,
            operation=operation,
            subject_type=subject_type,
            subject_name=subject_name,
            target=target,
        )
        return
    external_access.deny_external_access(
        resource_type=resource_type,
        operation=operation,
        subject_type=subject_type,
        subject_name=subject_name,
        target=target,
    )
