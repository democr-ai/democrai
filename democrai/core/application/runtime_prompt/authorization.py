from __future__ import annotations

from democrai.core.application.auth.action import check_access
from democrai.core.application.auth.roles import is_super_role, normalize_role
from democrai.core.application.runtime_prompt.models import (
    RuntimePromptAction,
    RuntimePromptRequest,
)


def check_prompt_authorization(
    request: RuntimePromptRequest,
    permissions: list[str],
) -> str | None:
    if request.required_role:
        normalized = normalize_role(request.required_role)
        if normalized == "super":
            if not is_super_role(request.role, level=request.access_level):
                return "runtime_prompt_forbidden"
        elif normalize_role(request.role) != normalized:
            return "runtime_prompt_forbidden"

    if request.required_access_level is not None:
        if request.access_level is None:
            return "runtime_prompt_forbidden"
        if request.access_level > request.required_access_level:
            return "runtime_prompt_forbidden"

    if request.required_permissions and not check_access(
        list(request.required_permissions),
        permissions,
    ):
        return "runtime_prompt_forbidden"

    return None


def check_action_authorization(
    action: RuntimePromptAction,
    permissions: list[str],
) -> str | None:
    if action.required_permissions and not check_access(
        list(action.required_permissions),
        permissions,
    ):
        return "runtime_prompt_action_forbidden"
    return None
