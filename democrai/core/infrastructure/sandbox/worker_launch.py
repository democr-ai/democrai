from __future__ import annotations

import os
import hashlib
import site
import sys
import sysconfig
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.runtime.foundation.paths import is_frozen
from democrai.core.runtime.foundation.paths import runtime_ipc_dir
from democrai.core.runtime.foundation.paths import state_dir


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
    paths = [ipc_path]
    if sys.platform == "darwin" and ipc_path.startswith("/var/"):
        paths.append("/private" + ipc_path)
    if sys.platform == "darwin":
        paths.extend(_darwin_runtime_ipc_variants())
    if sys.platform.startswith("linux"):
        paths.append("/dev/shm")
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
        for path in _python_runtime_read_paths()
    )
    return tuple(rules)


def _darwin_runtime_ipc_variants() -> tuple[str, ...]:
    try:
        candidate = state_dir() / "ipc"
        raw_uid = str(os.getuid()) if hasattr(os, "getuid") else "user"
        digest = hashlib.sha1(str(candidate).encode("utf-8")).hexdigest()[:12]
    except Exception:
        return ()
    bases = [
        os.environ.get("TMPDIR", ""),
        "/tmp",
        "/private/tmp",
        "/var/tmp",
        "/private/var/tmp",
    ]
    return tuple(
        dict.fromkeys(
            os.path.join(str(base).rstrip("/"), f"dc-ipc-{raw_uid}-{digest}")
            for base in bases
            if str(base or "").strip()
        )
    )


def _python_runtime_read_paths() -> tuple[str, ...]:
    paths: list[str] = []
    try:
        paths.extend(str(item) for item in site.getsitepackages())
    except Exception:
        pass
    try:
        paths.append(str(site.getusersitepackages()))
    except Exception:
        pass
    if sys.platform == "darwin":
        home = str(os.environ.get("HOME") or "").strip()
        if home:
            version = f"{sys.version_info.major}.{sys.version_info.minor}"
            paths.append(
                os.path.join(
                    home,
                    "Library",
                    "Python",
                    version,
                    "lib",
                    "python",
                    "site-packages",
                )
            )
    try:
        paths.extend(str(item) for item in sysconfig.get_paths().values())
    except Exception:
        pass
    return tuple(dict.fromkeys(path for path in paths if path))


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
