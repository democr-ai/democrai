from __future__ import annotations

from typing import Any

from democrai.core.application.auth.action import check_access
from democrai.core.application.services import external_access
from democrai.core.infrastructure.database.access_policy import get_pending_access_requests
from democrai.core.platform.utils.identity import to_optional_int


class Access:
    """Expose permission and external-resource access helpers to modules."""

    EXTERNAL_RESOURCE_NETWORK = external_access.EXTERNAL_RESOURCE_NETWORK
    EXTERNAL_RESOURCE_FILESYSTEM = external_access.EXTERNAL_RESOURCE_FILESYSTEM
    EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY = (
        external_access.EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY
    )

    def __init__(self, sdk) -> None:
        self.sdk = sdk

    def check_permissions(
        self,
        required_permissions: list[str],
        user_permissions: list[str],
    ) -> bool:
        return check_access(required_permissions, user_permissions)

    def check_external_access(
        self,
        *,
        resource_type: str,
        operation: str,
        target: str,
        subject_type: str = "module",
        subject_name: str | None = None,
        register_request: bool = True,
    ):
        return external_access.check_external_access(
            subject_type=subject_type,
            subject_name=str(subject_name or self.sdk.module_name),
            resource_type=resource_type,
            operation=operation,
            target=target,
            register_request=register_request,
        )

    def require_external_access(
        self,
        *,
        resource_type: str,
        operation: str,
        target: str,
        subject_type: str = "module",
        subject_name: str | None = None,
        resume_action: str | None = None,
        resume_context: dict[str, Any] | None = None,
    ):
        return external_access.check_external_access(
            subject_type=subject_type,
            subject_name=str(subject_name or self.sdk.module_name),
            resource_type=resource_type,
            operation=operation,
            target=target,
            register_request=True,
            resume_action=resume_action,
            resume_context=resume_context,
        )

    def approve_for_session(
        self,
        *,
        resource_type: str,
        operation: str,
        target: str,
        subject_type: str = "module",
        subject_name: str | None = None,
        session_key: str | None = None,
    ) -> None:
        external_access.approve_for_session(
            subject_type=subject_type,
            subject_name=str(subject_name or self.sdk.module_name),
            resource_type=resource_type,
            operation=operation,
            target=target,
            session_key=session_key,
        )

    def approve_permanently(
        self,
        *,
        resource_type: str,
        operation: str,
        target: str,
        subject_type: str = "module",
        subject_name: str | None = None,
    ) -> None:
        external_access.approve_permanently(
            subject_type=subject_type,
            subject_name=str(subject_name or self.sdk.module_name),
            resource_type=resource_type,
            operation=operation,
            target=target,
        )

    def deny_external_access(
        self,
        *,
        resource_type: str,
        operation: str,
        target: str,
        subject_type: str = "module",
        subject_name: str | None = None,
    ) -> None:
        external_access.deny_external_access(
            subject_type=subject_type,
            subject_name=str(subject_name or self.sdk.module_name),
            resource_type=resource_type,
            operation=operation,
            target=target,
        )

    def is_permanently_approved(
        self,
        *,
        resource_type: str,
        operation: str,
        target: str,
        subject_type: str = "module",
        subject_name: str | None = None,
    ) -> bool:
        return external_access.is_permanently_approved(
            subject_type=subject_type,
            subject_name=str(subject_name or self.sdk.module_name),
            resource_type=resource_type,
            operation=operation,
            target=target,
        )

    def can_manage_external_access(
        self,
        *,
        user_id: int | None,
        role: str | None,
        access_level: int | None,
        organization_id: int | None,
        permissions: list[str] | None = None,
    ) -> bool:
        return external_access.can_manage_external_access(
            user_id=user_id,
            role=role,
            access_level=access_level,
            organization_id=organization_id,
            permissions=permissions,
        )

    def sync_session_external_approvals(
        self,
        approvals: set[str],
        *,
        session: dict[str, Any] | None = None,
    ) -> None:
        from democrai.core.runtime.foundation.app import app_ctx, req_ctx

        context = app_ctx()
        network = getattr(context, "network", None)
        approvals_by_scope = getattr(network, "_session_external_approvals", None)
        if not isinstance(approvals_by_scope, dict):
            return
        request_context = None
        try:
            request_context = req_ctx()
        except Exception:
            request_context = None
        session_obj = session if isinstance(session, dict) else {}
        session_key = str(
            getattr(request_context, "session_key", "")
            or session_obj.get("session_key")
            or ""
        ).strip()
        user_obj = session_obj.get("user") if isinstance(session_obj.get("user"), dict) else {}
        user_id = to_optional_int(user_obj.get("id"))
        if user_id is None:
            user_id = getattr(request_context, "user", None)
        resolved_approvals = {str(item).strip() for item in approvals if str(item).strip()}
        if not resolved_approvals:
            return
        if session_key:
            scoped = approvals_by_scope.setdefault(f"session:{session_key}", set())
            if isinstance(scoped, set):
                scoped.update(resolved_approvals)
        if user_id is not None:
            scoped = approvals_by_scope.setdefault(f"user:{user_id}", set())
            if isinstance(scoped, set):
                scoped.update(resolved_approvals)


def get_pending_external_access_requests() -> list[dict[str, Any]]:
    return get_pending_access_requests()
