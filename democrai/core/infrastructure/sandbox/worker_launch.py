from __future__ import annotations

import os
import sys
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.infrastructure.sandbox.platform_policy import (
    runtime_ipc_path_variants,
)
from democrai.core.infrastructure.sandbox.runtime_access_baseline import (
    RuntimeAccessBaseline,
)
from democrai.core.runtime.foundation.paths import is_frozen
from democrai.core.runtime.foundation.paths import runtime_ipc_dir


def payload_access_rules(items: list[dict[str, Any]]) -> tuple[AccessManifestRule, ...]:
    rules: list[AccessManifestRule] = []
    for item in items:
        subject = item.get("subject") if isinstance(item, dict) else None
        resource = item.get("resource") if isinstance(item, dict) else None
        if not isinstance(subject, dict) or not isinstance(resource, dict):
            continue
        rules.append(
            AccessManifestRule(
                subject=AccessSubject.create(
                    str(subject.get("subject_type") or ""),
                    str(subject.get("subject_name") or ""),
                ),
                resource=AccessResource.create(
                    resource_type=str(resource.get("resource_type") or ""),
                    operation=str(resource.get("operation") or ""),
                    target=str(resource.get("target") or ""),
                ),
            )
        )
    return tuple(rules)


def build_worker_launch_state(
    *,
    subject_kind: str,
    subject_name: str,
    access: tuple[AccessManifestRule, ...],
    inherit_os_sandbox_helper_env: bool = False,
) -> dict[str, Any]:
    from democrai.core.infrastructure.sandbox import process_guard as process_guard_mod

    kind = str(subject_kind or "").strip().lower()
    name = str(subject_name or "").strip().lower()
    current_state = dict(process_guard_mod._state())
    subject_chain = list(current_state.get("subject_chain") or ())
    entry = {"kind": kind, "name": name}
    if name and (
        not subject_chain
        or dict(subject_chain[-1]).get("kind") != kind
        or dict(subject_chain[-1]).get("name") != name
    ):
        subject_chain.append(entry)
    launch_access = merge_access_rules(
        access,
        framework_runtime_access(subject_kind=kind, subject_name=name),
        process_guard_mod._runtime_access(),
    )
    return {
        "subject": name,
        "subject_kind": kind,
        "subject_chain": subject_chain,
        "access": launch_access,
        "user_id": current_state.get("user_id"),
        "organization_id": current_state.get("organization_id"),
        "session_key": current_state.get("session_key"),
        "os_sandbox_network_allow_all": bool(
            current_state.get("os_sandbox_network_allow_all")
        ),
        "inherit_os_sandbox_helper_env": bool(inherit_os_sandbox_helper_env),
    }


def framework_ipc_access(
    *,
    subject_kind: str,
    subject_name: str,
) -> tuple[AccessManifestRule, ...]:
    return tuple(
        rule
        for rule in framework_runtime_access(
            subject_kind=subject_kind,
            subject_name=subject_name,
        )
        if rule.resource.operation.value != "read"
        or rule.resource.normalized_target != _application_root()
    )


def framework_runtime_access(
    *,
    subject_kind: str,
    subject_name: str,
) -> tuple[AccessManifestRule, ...]:
    rules = list(_framework_application_access(subject_kind, subject_name))
    if os.name == "nt":
        return tuple(rules)
    try:
        ipc_path = str(runtime_ipc_dir().resolve())
    except Exception:
        return tuple(rules)
    paths = list(runtime_ipc_path_variants(ipc_path))
    subject = AccessSubject.create(subject_kind, subject_name)
    rules.extend(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation=operation,
                target=path,
            ),
        )
        for path in paths
        for operation in ("read", "create", "modify", "delete")
    )
    rules.extend(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=path,
            ),
        )
        for path in (
            *RuntimeAccessBaseline.python_runtime_read_paths(),
            *RuntimeAccessBaseline.native_library_read_paths(),
        )
    )
    rules.extend(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation=operation,
                target=path,
            ),
        )
        for path in RuntimeAccessBaseline.python_runtime_execute_paths()
        for operation in ("read", "execute")
    )
    return tuple(rules)


def _framework_application_access(
    subject_kind: str,
    subject_name: str,
) -> tuple[AccessManifestRule, ...]:
    root = _application_root()
    if not root:
        return ()
    subject = AccessSubject.create(subject_kind, subject_name)
    return (
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=root,
            ),
        ),
    )


def _application_root() -> str:
    try:
        if is_frozen():
            return os.path.dirname(os.path.abspath(sys.executable))
        path = os.path.abspath(__file__)
        for _ in range(5):
            path = os.path.dirname(path)
        return path
    except Exception:
        return ""


def merge_access_rules(
    *groups: tuple[AccessManifestRule, ...],
) -> tuple[AccessManifestRule, ...]:
    result: list[AccessManifestRule] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for group in groups:
        for rule in group:
            subject = getattr(rule, "subject", None)
            resource = getattr(rule, "resource", None)
            if subject is None or resource is None:
                continue
            resource_type = getattr(resource.resource_type, "value", resource.resource_type)
            operation = getattr(resource.operation, "value", resource.operation)
            key = (
                str(getattr(subject, "subject_type", "")),
                str(getattr(subject, "subject_name", "")),
                str(resource_type),
                str(operation),
                str(getattr(resource, "target", "") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            result.append(rule)
    return tuple(result)
