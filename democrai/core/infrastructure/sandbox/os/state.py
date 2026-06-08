from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow
from democrai.core.runtime.foundation.app import app_ctx

from .allowlist import build_framework_network_allowlist
from .models import ApplicationNetworkAllowlist


def get_current_application_network_allowlist() -> ApplicationNetworkAllowlist | None:
    return getattr(app_ctx(), "os_network_allowlist", None)


def is_application_network_allowlist_enabled(
    config: Any | None = None,
) -> bool:
    resolved_config = app_ctx().config if config is None else config
    if resolved_config is None:
        return False
    getter = getattr(resolved_config, "get", None)
    if not callable(getter):
        return False
    enabled = bool(getter("sandbox.os.enabled", False))
    debug_os_sandbox_flow("allowlist.config_enabled", enabled=enabled)
    return enabled


def set_current_application_network_allowlist(
    allowlist: ApplicationNetworkAllowlist | None,
) -> ApplicationNetworkAllowlist | None:
    app_ctx().os_network_allowlist = allowlist
    debug_os_sandbox_flow(
        "allowlist.set_current",
        endpoint_count=len(getattr(allowlist, "endpoints", []) or []),
    )
    return allowlist


def is_application_network_allowlist_active() -> bool:
    return bool(getattr(app_ctx(), "os_network_allowlist_active", False))


def set_application_network_allowlist_active(active: bool) -> bool:
    app_ctx().os_network_allowlist_active = bool(active)
    debug_os_sandbox_flow("allowlist.set_active", active=bool(active))
    return bool(active)


def refresh_application_network_allowlist(
    *,
    config: Any = None,
    modules: Any = None,
    engines: Iterable[Any] | None = None,
    extractors: Iterable[Any] | None = None,
    access_policy_approvals: Iterable[Any] | None = None,
    access_policy_session_approvals: Iterable[Any] | None = None,
) -> ApplicationNetworkAllowlist:
    ctx = app_ctx()
    debug_os_sandbox_flow(
        "allowlist.refresh_requested",
        config_override=config is not None,
        modules_override=modules is not None,
        engines_override=engines is not None,
        extractors_override=extractors is not None,
        approvals_override=access_policy_approvals is not None,
        session_approvals_override=access_policy_session_approvals is not None,
    )
    allowlist = build_framework_network_allowlist(
        config=ctx.config if config is None else config,
        modules=ctx.modules if modules is None else modules,
        access_policy_approvals=access_policy_approvals,
        access_policy_session_approvals=access_policy_session_approvals,
    )
    ctx.os_network_allowlist = allowlist
    debug_os_sandbox_flow(
        "allowlist.refresh_completed",
        endpoint_count=len(allowlist.endpoints),
    )
    return allowlist
