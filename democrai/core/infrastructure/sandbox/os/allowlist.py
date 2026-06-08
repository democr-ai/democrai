from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
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


@dataclass(frozen=True)
class NetworkPolicyRequest:
    scope: str
    subject_kind: str = ""
    subject_id: str = ""
    phase: str = ""
    subject_chain: tuple[dict[str, str], ...] = ()
    session_key: str | None = None
    inheritance_mode: str = "none"


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


def build_framework_network_allowlist(
    *,
    config: Any,
    modules: Any = None,
    mcp_servers: Iterable[Any] | None = None,
    access_policy_approvals: Iterable[Any] | None = None,
    access_policy_session_approvals: Iterable[Any] | None = None,
) -> ApplicationNetworkAllowlist:
    endpoints: list[NetworkEndpoint] = []
    endpoints.extend(collect_config_endpoints(config))
    endpoints.extend(collect_module_endpoints(modules))
    endpoints.extend(collect_mcp_server_endpoints(mcp_servers))
    endpoints.extend(
        _filter_subject_endpoints(
            collect_access_policy_approval_endpoints(access_policy_approvals),
            subject_prefixes=("module:", "framework:", "system:"),
        )
    )
    endpoints.extend(
        _filter_subject_endpoints(
            collect_access_policy_session_approval_endpoints(
                access_policy_session_approvals
            ),
            subject_prefixes=("module:", "framework:", "system:"),
        )
    )
    endpoints.extend(collect_observed_endpoints(config))
    deduped = dedupe_endpoints(endpoints)
    debug_os_sandbox_flow(
        "allowlist.build_framework",
        endpoint_count=len(deduped),
    )
    return ApplicationNetworkAllowlist(endpoints=deduped)


def build_subject_network_allowlist(
    request: NetworkPolicyRequest,
    *,
    config: Any = None,
    modules: Any = None,
    engines: Iterable[Any] | None = None,
    extractors: Iterable[Any] | None = None,
    mcp_servers: Iterable[Any] | None = None,
    access_policy_approvals: Iterable[Any] | None = None,
    access_policy_session_approvals: Iterable[Any] | None = None,
) -> ApplicationNetworkAllowlist:
    scope = _normalized(request.scope)
    kind = _normalized(request.subject_kind)
    name = _normalized(request.subject_id)
    phase = _normalized(request.phase)
    endpoints: list[NetworkEndpoint] = []

    if scope in {"engine_install", "engine_runtime"} or kind == "engine":
        endpoints.extend(
            _filter_subject_endpoints(
                collect_engine_endpoints(engines),
                subject_prefixes=(f"engine:{name}",),
                purposes=_phase_purposes("engine", phase or _scope_phase(scope)),
            )
        )
    elif scope in {"extractor_install", "extractor_runtime"} or kind == "extractor":
        endpoints.extend(
            _filter_subject_endpoints(
                collect_extractor_endpoints(extractors),
                subject_prefixes=(f"extractor:{name}",),
                purposes=_phase_purposes("extractor", phase or _scope_phase(scope)),
            )
        )
    elif scope == "skill_runtime" or kind == "skill":
        module_name = _chain_name(request.subject_chain, "module")
        if module_name:
            endpoints.extend(
                _filter_subject_endpoints(
                    collect_module_endpoints(modules),
                    subject_prefixes=(f"module:{module_name}",),
                )
            )
    elif scope == "mcp_http" or (kind == "mcp" and name):
        server_name = name.removeprefix("mcp.")
        endpoints.extend(
            _filter_subject_endpoints(
                collect_mcp_server_endpoints(mcp_servers),
                subject_prefixes=(f"mcp:{server_name}",),
            )
        )

    subject_prefix = f"{kind}:{name}" if kind and name else ""
    if kind and name:
        endpoints.extend(
            _approval_endpoints_for_subject(
                access_policy_approvals,
                subject_kind=kind,
                subject_id=name,
                session_key=None,
                session_only=False,
            )
        )
        endpoints.extend(
            _approval_endpoints_for_subject(
                access_policy_session_approvals,
                subject_kind=kind,
                subject_id=name,
                session_key=request.session_key,
                session_only=True,
            )
        )

    deduped = dedupe_endpoints(endpoints)
    debug_os_sandbox_flow(
        "allowlist.build_subject",
        scope=scope,
        subject_kind=kind,
        subject_id=name,
        phase=phase,
        endpoint_count=len(deduped),
    )
    return ApplicationNetworkAllowlist(endpoints=deduped)


def _filter_subject_endpoints(
    endpoints: list[NetworkEndpoint],
    *,
    subject_prefixes: tuple[str, ...],
    purposes: tuple[str, ...] = (),
) -> list[NetworkEndpoint]:
    prefixes = tuple(_normalized(item) for item in subject_prefixes if item)
    purpose_set = {_normalized(item) for item in purposes if item}
    result: list[NetworkEndpoint] = []
    for endpoint in endpoints:
        source = _normalized(endpoint.source)
        purpose = _normalized(endpoint.purpose)
        if prefixes and not any(source == prefix for prefix in prefixes):
            continue
        if purpose_set and purpose not in purpose_set:
            continue
        result.append(endpoint)
    return result


def _phase_purposes(kind: str, phase: str) -> tuple[str, ...]:
    resolved_kind = _normalized(kind)
    resolved_phase = _normalized(phase)
    if resolved_phase == "install":
        return (
            f"{resolved_kind}_install_manifest",
            f"{resolved_kind}_install_config",
            f"{resolved_kind}_install_default",
        )
    if resolved_phase == "runtime":
        return (
            f"{resolved_kind}_runtime_manifest",
            f"{resolved_kind}_runtime_config",
        )
    return ()


def _scope_phase(scope: str) -> str:
    if scope.endswith("_install"):
        return "install"
    if scope.endswith("_runtime"):
        return "runtime"
    return ""


def _chain_name(chain: tuple[dict[str, str], ...], kind: str) -> str:
    expected = _normalized(kind)
    for item in reversed(tuple(chain or ())):
        if not isinstance(item, dict):
            continue
        if _normalized(item.get("kind")) == expected:
            return _normalized(item.get("name"))
    return ""


def _normalized(value: Any) -> str:
    return str(value or "").strip().lower()


def _approval_endpoints_for_subject(
    approvals: Iterable[Any] | None,
    *,
    subject_kind: str,
    subject_id: str,
    session_key: str | None,
    session_only: bool,
) -> list[NetworkEndpoint]:
    rows = list(approvals or [])
    if approvals is None:
        rows = _load_approval_rows(
            subject_kind=subject_kind,
            subject_id=subject_id,
            session_key=session_key,
            session_only=session_only,
        )
    endpoints: list[NetworkEndpoint] = []
    for row in rows:
        if _normalized(getattr(row, "resource_type", "")) != "network":
            continue
        if _normalized(getattr(row, "subject_type", "")) != subject_kind:
            continue
        if _normalized(getattr(row, "subject_name", "")) != subject_id:
            continue
        if session_only and str(getattr(row, "session_key", "") or "") != str(session_key or ""):
            continue
        target = str(getattr(row, "target", "") or "").strip()
        if not target:
            continue
        from .normalize import endpoint_from_target

        endpoint = endpoint_from_target(
            target,
            source=f"{subject_kind}:{subject_id}",
            purpose="db_session_approval" if session_only else "db_approval",
        )
        if endpoint is not None:
            endpoints.append(endpoint)
    return dedupe_endpoints(endpoints)


def _load_approval_rows(
    *,
    subject_kind: str,
    subject_id: str,
    session_key: str | None,
    session_only: bool,
) -> list[Any]:
    try:
        from sqlalchemy.exc import OperationalError

        from democrai.core.infrastructure.database import SessionLocal
        from democrai.core.infrastructure.database.models import (
            ExternalAccessApproval,
            ExternalAccessRequest,
        )
        from democrai.core.runtime.foundation.app import app_ctx

        if getattr(app_ctx(), "db", None) is None:
            return []
        with SessionLocal() as session:
            if session_only:
                if not session_key:
                    return []
                return list(
                    session.query(ExternalAccessRequest)
                    .filter(
                        ExternalAccessRequest.status == "session",
                        ExternalAccessRequest.subject_type == subject_kind,
                        ExternalAccessRequest.subject_name == subject_id,
                        ExternalAccessRequest.resource_type == "network",
                        ExternalAccessRequest.session_key == session_key,
                    )
                    .all()
                )
            return list(
                session.query(ExternalAccessApproval)
                .filter(
                    ExternalAccessApproval.subject_type == subject_kind,
                    ExternalAccessApproval.subject_name == subject_id,
                    ExternalAccessApproval.resource_type == "network",
                )
                .all()
            )
    except Exception:
        return []
