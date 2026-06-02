from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from democrai.core.platform.utils.debug import debug_os_sandbox_flow

from .models import ApplicationNetworkAllowlist, NetworkEndpoint
from .normalize import dedupe_endpoints
from .sources import (
    collect_access_policy_approval_endpoints,
    collect_access_policy_session_approval_endpoints,
    collect_config_endpoints,
    collect_engine_endpoints,
    collect_extractor_endpoints,
    collect_mcp_server_endpoints,
    collect_module_endpoints,
    collect_observed_endpoints,
)


def build_application_network_allowlist(
    *,
    config: Any,
    modules: Any = None,
    engines: Iterable[Any] | None = None,
    mcp_servers: Iterable[Any] | None = None,
    extractors: Iterable[Any] | None = None,
    access_policy_approvals: Iterable[Any] | None = None,
    access_policy_session_approvals: Iterable[Any] | None = None,
) -> ApplicationNetworkAllowlist:
    endpoints: list[NetworkEndpoint] = []
    endpoints.extend(collect_config_endpoints(config))
    endpoints.extend(collect_module_endpoints(modules))
    endpoints.extend(collect_engine_endpoints(engines))
    endpoints.extend(collect_mcp_server_endpoints(mcp_servers))
    endpoints.extend(collect_extractor_endpoints(extractors))
    endpoints.extend(collect_access_policy_approval_endpoints(access_policy_approvals))
    endpoints.extend(collect_access_policy_session_approval_endpoints(access_policy_session_approvals))
    endpoints.extend(collect_observed_endpoints(config))
    deduped = dedupe_endpoints(endpoints)
    debug_os_sandbox_flow(
        "allowlist.build",
        endpoint_count=len(deduped),
        config_present=config is not None,
        modules_present=modules is not None,
        engines_provided=engines is not None,
        mcp_servers_provided=mcp_servers is not None,
        extractors_provided=extractors is not None,
        approvals_provided=access_policy_approvals is not None,
        session_approvals_provided=access_policy_session_approvals is not None,
    )
    return ApplicationNetworkAllowlist(endpoints=deduped)
