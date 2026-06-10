from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from democrai.core.application.access_policy.operations import ResourceType


NETWORK_DENY = "deny"
NETWORK_PROXY = "proxy"
NETWORK_ALLOW_ALL = "allow_all"
NETWORK_MODES = {NETWORK_DENY, NETWORK_PROXY, NETWORK_ALLOW_ALL}


@dataclass(frozen=True)
class FilesystemLaunchAccess:
    operation: str
    target: str
    subject: str = ""
    subject_kind: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "operation": self.operation,
            "target": self.target,
            "subject": self.subject,
            "subject_kind": self.subject_kind,
        }


@dataclass(frozen=True)
class NetworkLaunchEndpoint:
    operation: str
    target: str

    def to_dict(self) -> dict[str, str]:
        return {
            "operation": self.operation,
            "target": self.target,
        }


@dataclass(frozen=True)
class SandboxLaunchPolicy:
    command: list[str]
    cwd: str | None
    env: dict[str, str] | None
    filesystem_access: tuple[FilesystemLaunchAccess, ...]
    network_mode: str
    network_endpoints: tuple[NetworkLaunchEndpoint, ...] = ()
    subject: str = ""
    subject_kind: str = ""
    subject_chain: tuple[dict[str, str], ...] = ()
    user_id: int | None = None
    organization_id: int | None = None
    session_key: str | None = None
    audit_only: bool = False
    inherit_os_sandbox_helper_env: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 2,
            "command": list(self.command),
            "cwd": self.cwd,
            "env": dict(self.env) if self.env is not None else None,
            "filesystem_access": [item.to_dict() for item in self.filesystem_access],
            "network_mode": self.network_mode,
            "network_endpoints": [item.to_dict() for item in self.network_endpoints],
            "subject": self.subject,
            "subject_kind": self.subject_kind,
            "subject_chain": [dict(item) for item in self.subject_chain],
            "user_id": self.user_id,
            "organization_id": self.organization_id,
            "session_key": self.session_key,
            "audit_only": self.audit_only,
            "inherit_os_sandbox_helper_env": self.inherit_os_sandbox_helper_env,
        }


def policy_from_payload(payload: dict[str, Any]) -> SandboxLaunchPolicy:
    if not isinstance(payload, dict):
        raise RuntimeError("sandbox_launch_policy_invalid")
    if payload.get("version") != 2:
        raise RuntimeError("sandbox_launch_policy_version_unsupported")
    command = payload.get("command")
    if not isinstance(command, list) or not command:
        raise RuntimeError("sandbox_launch_policy_command_required")
    if "filesystem_access" not in payload:
        raise RuntimeError("sandbox_launch_policy_filesystem_access_required")
    if "network_mode" not in payload:
        raise RuntimeError("sandbox_launch_policy_network_mode_required")
    network_mode = str(payload.get("network_mode") or NETWORK_DENY).strip()
    if network_mode not in NETWORK_MODES:
        raise RuntimeError(f"sandbox_launch_policy_invalid_network_mode:{network_mode}")
    return SandboxLaunchPolicy(
        command=[str(item) for item in command],
        cwd=str(payload["cwd"]) if payload.get("cwd") is not None else None,
        env=_string_dict_or_none(payload.get("env")),
        filesystem_access=_filesystem_access_from_payload(payload),
        network_mode=network_mode,
        network_endpoints=tuple(
            NetworkLaunchEndpoint(
                operation=str(item.get("operation") or "").strip(),
                target=str(item.get("target") or "").strip(),
            )
            for item in list(payload.get("network_endpoints") or [])
            if isinstance(item, dict) and str(item.get("target") or "").strip()
        ),
        subject=str(payload.get("subject") or "").strip(),
        subject_kind=str(payload.get("subject_kind") or "").strip(),
        subject_chain=tuple(
            {
                "kind": str(item.get("kind") or "").strip(),
                "name": str(item.get("name") or "").strip(),
            }
            for item in list(payload.get("subject_chain") or [])
            if isinstance(item, dict)
            and str(item.get("kind") or "").strip()
            and str(item.get("name") or "").strip()
        ),
        user_id=_optional_int(payload.get("user_id")),
        organization_id=_optional_int(payload.get("organization_id")),
        session_key=str(payload.get("session_key") or "").strip() or None,
        audit_only=bool(payload.get("audit_only", False)),
        inherit_os_sandbox_helper_env=bool(
            payload.get("inherit_os_sandbox_helper_env", False)
        ),
    )


def build_launch_policy(
    *,
    command: list[str],
    cwd: str | None,
    env: dict[str, str] | None,
    state: dict[str, Any],
    audit_only: bool = False,
    allow_all_network: bool = False,
) -> SandboxLaunchPolicy:
    filesystem_access: list[FilesystemLaunchAccess] = []
    network_endpoints: list[NetworkLaunchEndpoint] = []
    for rule in tuple(state.get("access") or ()):
        resource = getattr(rule, "resource", None)
        if resource is None:
            continue
        resource_type = getattr(resource.resource_type, "value", resource.resource_type)
        operation = str(getattr(resource.operation, "value", resource.operation) or "").strip()
        target = str(getattr(resource, "normalized_target", None) or getattr(resource, "target", "") or "").strip()
        if not target:
            continue
        if resource_type == ResourceType.FILESYSTEM.value:
            subject = getattr(rule, "subject", None)
            filesystem_access.append(
                FilesystemLaunchAccess(
                    operation=operation,
                    target=target,
                    subject=str(getattr(subject, "subject_name", "") or "").strip(),
                    subject_kind=str(getattr(subject, "subject_type", "") or "").strip(),
                )
            )
        elif resource_type == ResourceType.NETWORK.value:
            network_endpoints.append(NetworkLaunchEndpoint(operation=operation, target=target))
    network_mode = NETWORK_ALLOW_ALL if allow_all_network else NETWORK_PROXY if network_endpoints else NETWORK_DENY
    return SandboxLaunchPolicy(
        command=[str(item) for item in command],
        cwd=str(cwd) if cwd is not None else None,
        env={str(key): str(value) for key, value in dict(env).items()} if isinstance(env, dict) else None,
        filesystem_access=tuple(filesystem_access),
        network_mode=network_mode,
        network_endpoints=tuple(network_endpoints),
        subject=str(state.get("subject") or "").strip(),
        subject_kind=str(state.get("subject_kind") or "").strip(),
        subject_chain=tuple(dict(item) for item in list(state.get("subject_chain") or []) if isinstance(item, dict)),
        user_id=_optional_int(state.get("user_id")),
        organization_id=_optional_int(state.get("organization_id")),
        session_key=str(state.get("session_key") or "").strip() or None,
        audit_only=bool(audit_only),
        inherit_os_sandbox_helper_env=bool(
            state.get("inherit_os_sandbox_helper_env", False)
        ),
    )


def _filesystem_access_from_payload(payload: dict[str, Any]) -> tuple[FilesystemLaunchAccess, ...]:
    raw_access = payload.get("filesystem_access")
    result: list[FilesystemLaunchAccess] = []
    for item in list(raw_access or []):
        if not isinstance(item, dict):
            continue
        operation = str(item.get("operation") or "").strip()
        target = str(item.get("target") or "").strip()
        if operation and target:
            result.append(
                FilesystemLaunchAccess(
                    operation=operation,
                    target=target,
                    subject=str(item.get("subject") or "").strip(),
                    subject_kind=str(item.get("subject_kind") or "").strip(),
                )
            )
    return tuple(result)


def _string_dict_or_none(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): str(item) for key, item in value.items()}


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except Exception:
        return None
