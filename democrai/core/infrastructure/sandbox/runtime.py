from __future__ import annotations


def check_external_access(**kwargs):
    from democrai.core.application.services.external_access import check_external_access as _f

    return _f(**kwargs)


def get_user_permissions(user_id):
    from democrai.core.application.auth.service import get_user_permissions as _f

    return _f(user_id)


def notify_missing_sandbox_dependency(lib_name: str) -> None:
    """Register a pending admin notification for a sandbox-monitored dependency."""
    try:
        from democrai.core.application.services.external_access import (
            EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY,
            check_external_access,
        )

        check_external_access(
            subject_type="core",
            subject_name="core",
            resource_type=EXTERNAL_RESOURCE_SYSTEM_DEPENDENCY,
            operation="execute",
            target=lib_name,
            register_request=True,
        )
    except Exception as exc:
        _log_sandbox_runtime_warning(
            f"[Sandbox] notify_missing_sandbox_dependency error for {lib_name!r}: {exc}"
        )


def _log_sandbox_runtime_warning(message: str) -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        app_ctx().logger.warning(message, "sandbox")
    except Exception:
        import warnings

        warnings.warn(message)


def log_sandbox_patch_failure(target: str, exc: Exception) -> None:
    """Log a patching failure for an installed library that could not be wrapped."""
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        app_ctx().logger.warning(
            f"[Sandbox] Failed to patch {target!r}: {exc}",
            "sandbox",
        )
    except Exception:
        import warnings

        warnings.warn(f"[Sandbox] Failed to patch {target!r}: {exc}")


def req_ctx():
    from democrai.core.runtime.foundation.app import req_ctx as _f

    return _f()


class ExternalAccessApprovalRequired(PermissionError):
    """Fallback exception used when external access module is not importable."""

    def __init__(
        self,
        *,
        resource_type: str,
        operation: str = "",
        subject_type: str = "module",
        subject_name: str = "",
        target: str,
        message: str,
        code: str = "",
    ) -> None:
        super().__init__(message)
        self.resource_type = str(resource_type or "")
        self.operation = str(operation or "")
        self.subject_type = str(subject_type or "module")
        self.subject_name = str(subject_name or "")
        self.target = str(target or "")
        self.message = str(message or "")
        self.code = str(code or "")


try:
    from democrai.core.application.services.external_access import (
        ExternalAccessApprovalRequired as _ExternalAccessApprovalRequired,
    )

    ExternalAccessApprovalRequired = _ExternalAccessApprovalRequired
except Exception as exc:
    _log_sandbox_runtime_warning(
        f"[Sandbox] ExternalAccessApprovalRequired import failed; using fallback exception: {exc}"
    )
