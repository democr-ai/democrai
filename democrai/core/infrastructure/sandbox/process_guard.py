from __future__ import annotations

import asyncio
import builtins
import concurrent.futures
import contextlib
import contextvars
import importlib
import io
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import threading
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy.models import AccessResource
from democrai.core.application.access_policy.models import AccessSubject
from democrai.core.application.access_policy.operations import ResourceType
from democrai.core.infrastructure.network.policy_guard import network_policy_context
from democrai.core.infrastructure.sandbox.access_constants import system_read_paths
from democrai.core.platform.utils.debug import debug_os_sandbox_flow
from democrai.core.runtime.foundation.paths import (
    cache_dir,
    config_dir,
    data_dir,
    logs_dir,
    state_dir,
)
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.observability.profiling import current_request_profiler


_ORIGINALS: dict[str, Any] = {}
_ACTIVE = False
_ACTIVE_COUNT = 0
_ACTIVE_LOCK = threading.Lock()
_STATE: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "process_guard_state",
    default=None,
)
_BYPASS: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "process_guard_bypass",
    default=False,
)
_PATH_CHECK_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar(
    "process_guard_path_check_depth",
    default=0,
)
_INTERNAL_FD_PATH_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar(
    "process_guard_internal_fd_path_depth",
    default=0,
)
_EXTERNAL_ACCESS_CACHE: contextvars.ContextVar[dict[tuple[str, str, str, str], dict[str, Any]] | None] = contextvars.ContextVar(
    "process_guard_external_access_cache",
    default=None,
)
_SENSITIVE_IMPORT_ROOTS = {"ctypes", "_ctypes", "cffi", "_cffi_backend"}
_PROTECTED_ENV_PREFIX = "DEMOCRAI_"
_EXTERNAL_ACCESS_CACHE_MAX = 512
_PATH_ACCESS_CACHE_MAX = 512
_RUNTIME_ACCESS_CACHE_LOCK = threading.Lock()
_CONFIG_DENIED_SUBJECT_KINDS = {"agent", "mcp", "tool"}


def _config_snapshot(config: Any) -> tuple[tuple[str, str], ...]:
    raw = getattr(config, "_config", None)
    if isinstance(raw, dict):
        try:
            return tuple(
                sorted(
                    (
                        str(key),
                        json.dumps(value, sort_keys=True, default=str),
                    )
                    for key, value in raw.items()
                )
            )
        except Exception:
            return tuple(sorted((str(key), str(value)) for key, value in raw.items()))
    return ()


def _profile_span(name: str):
    profiler = current_request_profiler()
    return profiler.span(name) if profiler else contextlib.nullcontext()


def _profile_count(name: str, amount: int = 1) -> None:
    profiler = current_request_profiler()
    if profiler is None or not profiler.enabled:
        return
    profiler.metrics[name] = profiler.metrics.get(name, 0.0) + float(amount)


def _state() -> dict[str, Any]:
    current = _STATE.get()
    return current if isinstance(current, dict) else {}


def _request_context() -> tuple[int | None, int | None, str | None]:
    current_state = _state()
    return (
        to_optional_int(current_state.get("user_id")),
        to_optional_int(current_state.get("organization_id")),
        str(current_state.get("session_key") or "").strip() or None,
    )


def _request_context_from_runtime() -> tuple[int | None, int | None, str | None]:
    try:
        from democrai.core.runtime.foundation.app import req_ctx

        current = req_ctx()
        return current.user, current.organization_id, current.session_key
    except Exception:
        return None, None, None


def _bypass_enabled() -> bool:
    return bool(_BYPASS.get())


def _internal_fd_paths_enabled() -> bool:
    return _INTERNAL_FD_PATH_DEPTH.get() > 0


@contextlib.contextmanager
def _internal_fd_path_context():
    depth = _INTERNAL_FD_PATH_DEPTH.get()
    token = _INTERNAL_FD_PATH_DEPTH.set(depth + 1)
    try:
        yield
    finally:
        _INTERNAL_FD_PATH_DEPTH.reset(token)


def _protected_env_name(key: Any) -> bool:
    return str(key or "").strip().upper().startswith(_PROTECTED_ENV_PREFIX)


def _normalize_paths(values: list[str] | None) -> list[str]:
    resolved: list[str] = []
    seen: set[str] = set()
    for item in list(values or []):
        raw = str(item or "").strip()
        if not raw:
            continue
        candidate = raw[3:].strip() if raw.startswith("ro:") else raw
        for normalized in _normalized_path_variants(candidate):
            if normalized in seen:
                continue
            seen.add(normalized)
            resolved.append(normalized)
    return resolved


def _normalize_subject_kind(value: str | None) -> str:
    raw = str(value or "").strip().lower()
    return raw or "module"


def _normalize_subject_entry(
    kind: str | None, name: str | None
) -> dict[str, str] | None:
    resolved_name = str(name or "").strip()
    if not resolved_name:
        return None
    return {
        "kind": _normalize_subject_kind(kind),
        "name": resolved_name,
    }


def _normalize_subject_chain(
    values: list[dict[str, Any]] | None
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in list(values or []):
        if not isinstance(item, dict):
            continue
        entry = _normalize_subject_entry(item.get("kind"), item.get("name"))
        if entry is None:
            continue
        key = (entry["kind"], entry["name"])
        if key in seen:
            continue
        seen.add(key)
        normalized.append(entry)
    return normalized


def _merge_subject_chain(
    parent: list[dict[str, Any]] | None,
    current: dict[str, str] | None,
) -> list[dict[str, str]]:
    merged = _normalize_subject_chain(parent)
    if current is None:
        return merged
    if merged and merged[-1] == current:
        return merged
    return [*merged, current]


def _normalize_import_roots(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in list(values or []):
        root = str(item or "").strip().split(".", 1)[0]
        if not root or root in seen:
            continue
        seen.add(root)
        normalized.append(root)
    return normalized


def _normalized_path_variants(path_value: Any) -> list[str]:
    with _profile_span("process_guard.path.normalize"):
        raw = os.fsdecode(os.fspath(path_value))
        expanded = os.path.expanduser(raw)
        variants = [
            os.path.normpath(os.path.abspath(expanded)),
            os.path.normpath(os.path.realpath(expanded)),
        ]
        deduped: list[str] = []
        seen: set[str] = set()
        for item in variants:
            if item in seen:
                continue
            seen.add(item)
            deduped.append(item)
        return deduped


def _access_resource_key(rule: AccessManifestRule) -> tuple[str, str, str]:
    resource = rule.resource
    return (
        resource.resource_type.value,
        resource.operation.value,
        resource.normalized_target,
    )


def _merge_access_rules(
    *rule_groups: list[AccessManifestRule] | tuple[AccessManifestRule, ...],
) -> tuple[AccessManifestRule, ...]:
    merged: list[AccessManifestRule] = []
    seen: set[tuple[str, str, str]] = set()
    for rules in rule_groups:
        for rule in rules:
            if not isinstance(rule, AccessManifestRule):
                raise TypeError("process_guard_access_rule_required")
            key = _access_resource_key(rule)
            if key in seen:
                continue
            seen.add(key)
            merged.append(rule)
    return tuple(merged)


def _access_rules_to_dicts(
    rules: list[AccessManifestRule] | tuple[AccessManifestRule, ...],
) -> list[dict[str, dict[str, str]]]:
    return [rule.to_dict() for rule in rules]


def _filesystem_access_by_operation(
    rules: list[AccessManifestRule] | tuple[AccessManifestRule, ...],
) -> dict[str, tuple[str, ...]]:
    indexed: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for rule in rules:
        if not isinstance(rule, AccessManifestRule):
            continue
        resource = rule.resource
        if resource.resource_type != ResourceType.FILESYSTEM:
            continue
        operation = resource.operation.value
        target = resource.normalized_target
        key = (operation, target)
        if key in seen:
            continue
        seen.add(key)
        indexed.setdefault(operation, []).append(target)
    return {operation: tuple(paths) for operation, paths in indexed.items()}


def _filesystem_access_summary(
    rules: list[AccessManifestRule] | tuple[AccessManifestRule, ...],
) -> dict[str, list[str]]:
    summary: dict[str, list[str]] = {}
    for rule in rules:
        if not isinstance(rule, AccessManifestRule):
            continue
        resource = rule.resource
        if resource.resource_type != ResourceType.FILESYSTEM:
            continue
        operation = resource.operation.value
        paths = summary.setdefault(operation, [])
        if resource.normalized_target not in paths:
            paths.append(resource.normalized_target)
    return summary


def _access_rule_from_dict(item: dict[str, Any]) -> AccessManifestRule:
    subject = item["subject"]
    resource = item["resource"]
    return AccessManifestRule(
        subject=AccessSubject.create(
            subject["subject_type"],
            subject["subject_name"],
        ),
        resource=AccessResource.create(
            resource_type=resource["resource_type"],
            operation=resource["operation"],
            target=resource["target"],
        ),
    )


def _access_rules_from_dicts(values: list[dict[str, Any]]) -> tuple[AccessManifestRule, ...]:
    return tuple(_access_rule_from_dict(item) for item in values)


def _subject_access_entry(
    subject: dict[str, str] | None,
    access: tuple[AccessManifestRule, ...],
) -> dict[str, Any] | None:
    if subject is None:
        return None
    return {
        **subject,
        "access": _access_rules_to_dicts(access),
    }


def _merge_subject_access_chain(
    parent: list[dict[str, Any]] | None,
    current: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    merged = list(parent or [])
    if current is None:
        return merged
    if merged and (merged[-1].get("kind"), merged[-1].get("name")) == (
        current.get("kind"),
        current.get("name"),
    ):
        merged[-1] = current
        return merged
    return [*merged, current]


def _configured_runtime_paths() -> list[str]:
    try:
        from democrai.core.runtime.foundation.app import app_ctx
    except Exception:
        return []

    try:
        config = getattr(app_ctx(), "config", None)
    except Exception:
        return []
    if config is None:
        return []

    getter = getattr(config, "get", None)
    if not callable(getter):
        return []

    try:
        media_type = str(getter("storage.media.type", "local") or "").strip().lower()
    except Exception:
        media_type = "local"
    if media_type != "local":
        return []

    try:
        media_path = str(getter("storage.media.path") or "").strip()
    except Exception:
        media_path = ""
    if not media_path:
        return []
    return [media_path]


def _configured_media_storage_path() -> str:
    try:
        from democrai.core.runtime.foundation.app import app_ctx
    except Exception:
        return ""

    try:
        config = getattr(app_ctx(), "config", None)
    except Exception:
        return ""
    if config is None:
        return ""

    getter = getattr(config, "get", None)
    if not callable(getter):
        return ""

    try:
        media_type = str(getter("storage.media.type", "local") or "").strip().lower()
    except Exception:
        media_type = "local"
    if media_type != "local":
        return ""

    try:
        return str(getter("storage.media.path") or "").strip()
    except Exception:
        return ""


def _application_temp_path() -> str:
    try:
        return str((data_dir() / "tmp").resolve())
    except Exception:
        return ""


def runtime_system_read_paths() -> list[str]:
    paths: list[str] = list(system_read_paths())
    try:
        paths.append(tempfile.gettempdir())
    except Exception:
        pass
    for item in list(sys.path):
        raw = str(item or "").strip()
        if raw:
            paths.append(raw)
    for key in ("stdlib", "platstdlib", "purelib", "platlib", "data", "include", "scripts"):
        raw = sysconfig.get_paths().get(key)
        if raw:
            paths.append(raw)
    for item in (sys.prefix, sys.exec_prefix):
        raw = str(item or "").strip()
        if raw:
            paths.append(raw)
    return _normalize_paths(paths)


def _runtime_filesystem_read_paths() -> list[str]:
    paths: list[str] = runtime_system_read_paths()
    for path_factory in (data_dir, config_dir, cache_dir, state_dir, logs_dir):
        try:
            paths.append(str(path_factory().resolve()))
        except Exception:
            continue
    app_temp_path = _application_temp_path()
    if app_temp_path:
        paths.append(app_temp_path)
    paths.extend(_configured_runtime_paths())
    return _normalize_paths(paths)


def _filesystem_access_rules(
    *,
    subject: AccessSubject,
    operation: str,
    paths: list[str],
) -> tuple[AccessManifestRule, ...]:
    return tuple(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type=ResourceType.FILESYSTEM,
                operation=operation,
                target=path,
            ),
        )
        for path in _normalize_paths(paths)
    )


def _configured_logging_network_access_rules(
    *,
    subject: AccessSubject,
) -> tuple[AccessManifestRule, ...]:
    try:
        from democrai.core.runtime.foundation.app import app_ctx
    except Exception:
        return ()

    try:
        config = getattr(app_ctx(), "config", None)
    except Exception:
        return ()
    getter = getattr(config, "get", None)
    if not callable(getter):
        return ()

    try:
        provider = str(getter("logging.provider", "local") or "local").strip().lower()
        target = str(getter("logging.url", "") or "").strip()
    except Exception:
        return ()
    if provider != "http" or not target:
        return ()

    return tuple(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type=ResourceType.NETWORK,
                operation=operation,
                target=target,
            ),
        )
        for operation in ("connect", "send", "receive")
    )


def _configured_remote_service_network_access_rules(
    *,
    subject: AccessSubject,
) -> tuple[AccessManifestRule, ...]:
    try:
        from democrai.core.infrastructure.sandbox.os.sources import (
            collect_config_access_targets,
        )
        from democrai.core.runtime.foundation.app import app_ctx
    except Exception:
        return ()

    try:
        targets = collect_config_access_targets(getattr(app_ctx(), "config", None))
    except Exception:
        return ()

    rules: list[AccessManifestRule] = []
    for target in targets:
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type=ResourceType.NETWORK,
                    operation=operation,
                    target=target,
                ),
            )
            for operation in ("connect", "send", "receive")
        )
    return tuple(rules)


def _runtime_access_cache_key() -> tuple[Any, ...]:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        config = getattr(app_ctx(), "config", None)
    except Exception:
        config = None
    return (
        id(config),
        _config_snapshot(config),
        id(data_dir),
        id(config_dir),
        id(cache_dir),
        id(state_dir),
        id(logs_dir),
        id(system_read_paths),
        id(sysconfig.get_paths),
        id(_runtime_filesystem_read_paths),
        id(_configured_runtime_paths),
        id(_configured_media_storage_path),
        id(_configured_logging_network_access_rules),
        id(_configured_remote_service_network_access_rules),
        tuple(str(item or "") for item in sys.path),
        str(sys.prefix or ""),
        str(sys.exec_prefix or ""),
        tempfile.gettempdir(),
    )


def _get_cached_runtime_access(
    key: tuple[Any, ...],
) -> tuple[AccessManifestRule, ...] | None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        cache = getattr(app_ctx(), "process_guard_runtime_access", None)
    except Exception:
        return None
    if not isinstance(cache, dict):
        return None
    if cache.get("key") != key:
        return None
    access = cache.get("access")
    if not isinstance(access, tuple):
        return None
    return access


def _set_cached_runtime_access(
    key: tuple[Any, ...],
    access: tuple[AccessManifestRule, ...],
) -> None:
    try:
        from democrai.core.runtime.foundation.app import app_ctx

        app_ctx().process_guard_runtime_access = {
            "key": key,
            "access": access,
        }
    except Exception:
        return


def _build_runtime_access() -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("core", "process_guard_runtime")
    read_paths = _runtime_filesystem_read_paths()
    writable_paths: list[str] = []
    delete_paths: list[str] = []
    for path_factory in (data_dir, cache_dir, state_dir, logs_dir):
        try:
            writable_paths.append(str(path_factory().resolve()))
        except Exception:
            continue
    app_temp_path = _application_temp_path()
    if app_temp_path:
        writable_paths.append(app_temp_path)
        delete_paths.append(app_temp_path)
    try:
        writable_paths.append(tempfile.gettempdir())
        delete_paths.append(tempfile.gettempdir())
    except Exception:
        pass
    try:
        delete_paths.append(str(cache_dir().resolve()))
    except Exception:
        pass
    try:
        delete_paths.append(str(logs_dir().resolve()))
    except Exception:
        pass
    media_storage_path = _configured_media_storage_path()
    if media_storage_path:
        delete_paths.append(media_storage_path)
    writable_paths.extend(_configured_runtime_paths())
    return _merge_access_rules(
        _filesystem_access_rules(subject=subject, operation="read", paths=read_paths),
        _filesystem_access_rules(subject=subject, operation="create", paths=writable_paths),
        _filesystem_access_rules(subject=subject, operation="modify", paths=writable_paths),
        _filesystem_access_rules(subject=subject, operation="delete", paths=delete_paths),
        _configured_logging_network_access_rules(subject=subject),
        _configured_remote_service_network_access_rules(subject=subject),
    )


def _runtime_access() -> tuple[AccessManifestRule, ...]:
    key = _runtime_access_cache_key()
    cached = _get_cached_runtime_access(key)
    if cached is not None:
        _profile_count("process_guard.runtime_access.cache_hits")
        return cached
    with _RUNTIME_ACCESS_CACHE_LOCK:
        cached = _get_cached_runtime_access(key)
        if cached is not None:
            _profile_count("process_guard.runtime_access.cache_hits")
            return cached
        access = _build_runtime_access()
        _set_cached_runtime_access(key, access)
        return access


def _path_allowed(path_value: Any, *, operation: str) -> bool:
    _profile_count("process_guard.path_allowed.calls")
    with _profile_span("process_guard.path_allowed"):
        if _bypass_enabled():
            return True
        current_state = _state()
        if not current_state:
            return True
        if isinstance(path_value, int):
            return False
        filesystem_access = current_state.get("filesystem_access") or {}
        allowed_roots = filesystem_access.get(operation) or ()
        if not allowed_roots:
            access = current_state.get("access") or ()
            if access:
                filesystem_access = _filesystem_access_by_operation(tuple(access))
                allowed_roots = filesystem_access.get(operation) or ()
        if not allowed_roots:
            return False
        cache_key = _path_access_cache_key(path_value, operation=operation)
        cache = current_state.get("path_access_cache")
        if cache_key is not None and isinstance(cache, dict):
            cached = cache.get(cache_key)
            if cached is not None:
                _profile_count("process_guard.path_allowed.cache_hits")
                return bool(cached)
        variants = _normalized_path_variants(path_value)
        allowed_result = True
        for resolved in variants:
            allowed = False
            with _profile_span("process_guard.path_allowed.scan_rules"):
                for allowed_root in allowed_roots:
                    _profile_count("process_guard.path_allowed.rules_checked")
                    if resolved == allowed_root or resolved.startswith(allowed_root + os.sep):
                        allowed = True
                        break
            if not allowed:
                allowed_result = False
                break
        if cache_key is not None and isinstance(cache, dict):
            _path_access_cache_set(cache, cache_key, allowed_result)
        return allowed_result


def _debug_path_denial(path_value: Any, *, operation: str) -> None:
    try:
        with process_guard_bypass_context():
            current_state = _state()
            debug_os_sandbox_flow(
                "process_guard.path_denied",
                operation=str(operation or ""),
                path=str(path_value or ""),
                subject=str(current_state.get("subject") or ""),
                subject_kind=str(current_state.get("subject_kind") or ""),
                subject_chain=current_state.get("subject_chain"),
                filesystem_access=_filesystem_access_summary(
                    tuple(current_state.get("access") or ())
                ),
            )
    except Exception:
        return


def _external_filesystem_access_allowed(
    path_value: Any,
    *,
    operation: str,
    register_request: bool = False,
) -> bool:
    _profile_count("process_guard.external_fs.calls")
    with _profile_span("process_guard.external_fs"):
        current_state = _state()
        subject = str(current_state.get("subject") or "").strip()
        subject_kind = str(current_state.get("subject_kind") or "module").strip() or "module"
        if not subject:
            return False
        try:
            from democrai.core.runtime.foundation.app import app_ctx

            if bool(getattr(app_ctx(), "setup_mode", False)):
                return False
        except Exception:
            return False
        if isinstance(path_value, int):
            return False
        target = os.fspath(path_value)
        normalized_target = os.path.normpath(os.path.realpath(os.path.abspath(target)))
        cache_key = (subject_kind, subject, operation, normalized_target)
        cache = _EXTERNAL_ACCESS_CACHE.get()
        if cache is None:
            cache = {}
            _EXTERNAL_ACCESS_CACHE.set(cache)
        cached = cache.get(cache_key)
        if isinstance(cached, dict):
            _profile_count("process_guard.external_fs.cache_hits")
            if cached.get("allowed") is True:
                return True
            if cached.get("requires_approval") is True:
                from democrai.core.application.services.external_access import (
                    EXTERNAL_RESOURCE_FILESYSTEM,
                    ExternalAccessApprovalRequired,
                )

                raise ExternalAccessApprovalRequired(
                    resource_type=EXTERNAL_RESOURCE_FILESYSTEM,
                    operation=operation,
                    subject_type=subject_kind,
                    subject_name=subject,
                    target=target,
                    message=str(cached.get("message") or f"sandbox_filesystem_denied:{subject}:{target}"),
                    code=str(cached.get("code") or ""),
                )
            return False
        try:
            from democrai.core.application.services.external_access import (
                EXTERNAL_RESOURCE_FILESYSTEM,
                ExternalAccessApprovalRequired,
                check_external_access,
            )

            with _profile_span("process_guard.external_fs.db_check"):
                access = check_external_access(
                    subject_type=subject_kind,
                    subject_name=subject,
                    resource_type=EXTERNAL_RESOURCE_FILESYSTEM,
                    operation=operation,
                    target=target,
                    register_request=register_request,
                )
            if bool(getattr(access, "allowed", False)):
                _external_access_cache_set(cache, cache_key, {"allowed": True})
                return True
            if bool(getattr(access, "requires_approval", False)):
                cached_denial = {
                    "allowed": False,
                    "requires_approval": True,
                    "message": f"sandbox_filesystem_denied:{subject}:{target}",
                    "code": getattr(access, "code", ""),
                }
                _external_access_cache_set(cache, cache_key, cached_denial)
                raise ExternalAccessApprovalRequired(
                    resource_type=EXTERNAL_RESOURCE_FILESYSTEM,
                    operation=operation,
                    subject_type=subject_kind,
                    subject_name=subject,
                    target=target,
                    message=str(cached_denial["message"]),
                    code=getattr(access, "code", ""),
                )
            _external_access_cache_set(
                cache,
                cache_key,
                {
                    "allowed": False,
                    "requires_approval": False,
                    "message": str(getattr(access, "message", "") or ""),
                    "code": str(getattr(access, "code", "") or ""),
                },
            )
        except PermissionError:
            raise
        except Exception as exc:
            try:
                from democrai.core.runtime.foundation.app import app_ctx

                logger = getattr(app_ctx(), "logger", None)
                if logger is not None:
                    logger.error(
                        "[process_guard] external filesystem access check failed "
                        f"subject_kind={subject_kind} subject={subject} "
                        f"operation={operation} target={target} "
                        f"normalized_target={normalized_target} error={exc}",
                        exc_info=True,
                    )
            except Exception:
                pass
            raise RuntimeError("sandbox_external_access_check_failed") from exc
        return False


def _external_access_cache_set(
    cache: dict[tuple[str, str, str, str], dict[str, Any]],
    key: tuple[str, str, str, str],
    value: dict[str, Any],
) -> None:
    if key in cache:
        cache[key] = value
        return
    if len(cache) >= _EXTERNAL_ACCESS_CACHE_MAX:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            cache.clear()
    cache[key] = value


def _path_access_cache_key(path_value: Any, *, operation: str) -> tuple[str, str, str] | None:
    if isinstance(path_value, int):
        return None
    try:
        raw = os.fsdecode(os.fspath(path_value))
    except TypeError:
        return None
    return (operation, os.getcwd(), raw)


def _path_access_cache_set(
    cache: dict[tuple[str, str, str], bool],
    key: tuple[str, str, str],
    value: bool,
) -> None:
    if key in cache:
        cache[key] = value
        return
    if len(cache) >= _PATH_ACCESS_CACHE_MAX:
        try:
            cache.pop(next(iter(cache)))
        except Exception:
            cache.clear()
    cache[key] = value


def _resolve_filesystem_operation(path_value: Any, operation: str) -> str:
    if operation == "create_or_modify":
        return _create_or_modify_operation(path_value)
    return operation


def _application_config_path() -> str:
    try:
        return str((data_dir() / "config.yaml").resolve())
    except Exception:
        return ""


def _config_access_denied(path_value: Any) -> bool:
    current_state = _state()
    subject_kind = str(current_state.get("subject_kind") or "").strip().lower()
    if subject_kind not in _CONFIG_DENIED_SUBJECT_KINDS:
        return False
    if isinstance(path_value, int):
        return False
    config_path = _application_config_path()
    if not config_path:
        return False
    try:
        return any(variant == config_path for variant in _normalized_path_variants(path_value))
    except Exception:
        return False


def _raise_config_access_denied(path_value: Any, *, operation: str) -> None:
    current_state = _state()
    subject_kind = str(current_state.get("subject_kind") or "").strip() or "subject"
    subject = str(current_state.get("subject") or "").strip() or "subject"
    raise PermissionError(
        "sandbox_config_access_denied:"
        f"{subject_kind}:{subject}:{operation}:{path_value}"
    )


def _check_path(path_value: Any, *, operation: str) -> None:
    _profile_count("process_guard.check_path.calls")
    depth = _PATH_CHECK_DEPTH.get()
    if depth > 0:
        return
    token = _PATH_CHECK_DEPTH.set(depth + 1)
    try:
        with _profile_span("process_guard.check_path"):
            resolved_operation = _resolve_filesystem_operation(path_value, operation)
            if _config_access_denied(path_value):
                _raise_config_access_denied(path_value, operation=resolved_operation)
            if _path_allowed(path_value, operation=resolved_operation):
                return
            if _external_filesystem_access_allowed(path_value, operation=resolved_operation):
                return
            _debug_path_denial(path_value, operation=resolved_operation)
            raise PermissionError(
                f"sandbox_filesystem_denied:{_state().get('subject') or 'subject'}:{path_value}"
            )
    finally:
        _PATH_CHECK_DEPTH.reset(token)


def _check_path_pair(
    source: Any,
    target: Any,
    *,
    source_operation: str,
    target_operation: str,
) -> None:
    _profile_count("process_guard.check_path_pair.calls")
    depth = _PATH_CHECK_DEPTH.get()
    if depth > 0:
        return
    token = _PATH_CHECK_DEPTH.set(depth + 1)
    try:
        with _profile_span("process_guard.check_path_pair"):
            resolved_source_operation = _resolve_filesystem_operation(source, source_operation)
            resolved_target_operation = _resolve_filesystem_operation(target, target_operation)
            if _config_access_denied(source):
                _raise_config_access_denied(source, operation=resolved_source_operation)
            if _config_access_denied(target):
                _raise_config_access_denied(target, operation=resolved_target_operation)
            if not _path_allowed(source, operation=resolved_source_operation):
                if not _external_filesystem_access_allowed(source, operation=resolved_source_operation):
                    raise PermissionError(
                        f"sandbox_filesystem_denied:{_state().get('subject') or 'subject'}:{source}"
                    )
            if not _path_allowed(target, operation=resolved_target_operation):
                if not _external_filesystem_access_allowed(target, operation=resolved_target_operation):
                    raise PermissionError(
                        f"sandbox_filesystem_denied:{_state().get('subject') or 'subject'}:{target}"
                    )
    finally:
        _PATH_CHECK_DEPTH.reset(token)


def _check_fd_kwargs(kwargs: dict[str, Any]) -> None:
    # Engine/install flows run with allow_subprocess=True and rely on stdlib/pip
    # internals that use dir_fd-based cleanup APIs (e.g. shutil.rmtree internals).
    # Keep strict fd-deny policy for normal runtime, relax only for install contexts.
    current_state = _state()
    if _internal_fd_paths_enabled():
        return
    if bool(current_state.get("allow_subprocess")):
        return
    for key in ("dir_fd", "src_dir_fd", "dst_dir_fd"):
        if kwargs.get(key) is not None:
            raise PermissionError(
                f"sandbox_filesystem_fd_denied:{_state().get('subject') or 'subject'}:{key}"
            )


def _skip_path_check_for_dir_fd(kwargs: dict[str, Any]) -> bool:
    if not bool(_state().get("allow_subprocess")) and not _internal_fd_paths_enabled():
        return False
    return any(
        kwargs.get(key) is not None for key in ("dir_fd", "src_dir_fd", "dst_dir_fd")
    )


def _skip_path_check_for_fd_path(path: Any) -> bool:
    return isinstance(path, int)


def _path_exists_for_operation(path_value: Any) -> bool:
    with _profile_span("process_guard.path_exists"):
        try:
            if isinstance(path_value, int):
                return False
            original_stat = _ORIGINALS.get("os.stat")
            stat_func = original_stat if callable(original_stat) else os.stat
            stat_func(path_value)
            return True
        except FileNotFoundError:
            return False
        except Exception:
            return False


def _create_or_modify_operation(path_value: Any) -> str:
    with _profile_span("process_guard.create_or_modify"):
        return "modify" if _path_exists_for_operation(path_value) else "create"


def _open_operation(file: Any, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    with _profile_span("process_guard.open_operation"):
        mode = kwargs.get("mode")
        if mode is None and args:
            mode = args[0]
        normalized = str(mode or "r")
        if any(flag in normalized for flag in ("w", "a", "x", "+")):
            return _create_or_modify_operation(file)
        return "read"


def _os_open_operation(path: Any, flags: int) -> str:
    write_flags = (
        getattr(os, "O_WRONLY", 0)
        | getattr(os, "O_RDWR", 0)
        | getattr(os, "O_APPEND", 0)
        | getattr(os, "O_TRUNC", 0)
    )
    create_flags = getattr(os, "O_CREAT", 0) | getattr(os, "O_EXCL", 0)
    if int(flags) & (write_flags | create_flags):
        return _create_or_modify_operation(path)
    return "read"


def _path_method_operation(self: Any, attr: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    if attr == "open":
        return _open_operation(self, args, kwargs)
    if attr in {"write_text", "write_bytes"}:
        return _create_or_modify_operation(self)
    if attr == "touch":
        return _create_or_modify_operation(self)
    if attr == "mkdir":
        return "create"
    if attr in {"unlink", "rmdir"}:
        return "delete"
    if attr in {"chmod", "lchmod"}:
        return "modify"
    return "read"


def _wrap_open(original):
    def wrapper(file, *args, **kwargs):
        _profile_count("process_guard.wrapper.open.calls")
        if isinstance(file, int):
            # Allow file-descriptor based open() calls (used by subprocess pipes).
            return original(file, *args, **kwargs)
        with _profile_span("process_guard.wrapper.open.guard"):
            _check_path(file, operation=_open_operation(file, args, kwargs))
        return original(file, *args, **kwargs)

    return wrapper


def _wrap_os_open(original):
    def wrapper(path, flags, *args, **kwargs):
        _profile_count("process_guard.wrapper.os_open.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(path, flags, *args, **kwargs)
        with _profile_span("process_guard.wrapper.os_open.guard"):
            _check_fd_kwargs(kwargs)
            if not _skip_path_check_for_dir_fd(kwargs):
                _check_path(path, operation=_os_open_operation(path, flags))
        return original(path, flags, *args, **kwargs)

    return wrapper


def _wrap_os_optional_path(original, operation: str, attr: str = ""):
    def wrapper(path=".", *args, **kwargs):
        _profile_count("process_guard.wrapper.os_optional.calls")
        if attr:
            _profile_count(f"process_guard.wrapper.os_optional.{attr}.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(path, *args, **kwargs)
        with _profile_span("process_guard.wrapper.os_optional.guard"):
            if attr:
                span = _profile_span(f"process_guard.wrapper.os_optional.{attr}.guard")
            else:
                span = contextlib.nullcontext()
            with span:
                _check_fd_kwargs(kwargs)
                if not _skip_path_check_for_dir_fd(kwargs) and not _skip_path_check_for_fd_path(
                    path
                ):
                    _check_path(path, operation=operation)
        return original(path, *args, **kwargs)

    return wrapper


def _wrap_os_default_path(original, default_path: str, operation: str, attr: str = ""):
    def wrapper(path=default_path, *args, **kwargs):
        _profile_count("process_guard.wrapper.os_default.calls")
        if attr:
            _profile_count(f"process_guard.wrapper.os_default.{attr}.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(path, *args, **kwargs)
        with _profile_span("process_guard.wrapper.os_default.guard"):
            if attr:
                span = _profile_span(f"process_guard.wrapper.os_default.{attr}.guard")
            else:
                span = contextlib.nullcontext()
            with span:
                _check_fd_kwargs(kwargs)
                if not _skip_path_check_for_dir_fd(kwargs) and not _skip_path_check_for_fd_path(
                    path
                ):
                    _check_path(path, operation=operation)
        return original(path, *args, **kwargs)

    return wrapper


def _wrap_os_makedirs(original):
    def wrapper(name, *args, **kwargs):
        _profile_count("process_guard.wrapper.os_makedirs.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(name, *args, **kwargs)
        with _profile_span("process_guard.wrapper.os_makedirs.guard"):
            _check_path(name, operation="create")
        depth = _PATH_CHECK_DEPTH.get()
        token = _PATH_CHECK_DEPTH.set(depth + 1)
        try:
            return original(name, *args, **kwargs)
        finally:
            _PATH_CHECK_DEPTH.reset(token)

    return wrapper


def _wrap_path_pair(original, source_operation: str, target_operation: str):
    def wrapper(src, dst, *args, **kwargs):
        _profile_count("process_guard.wrapper.path_pair.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(src, dst, *args, **kwargs)
        with _profile_span("process_guard.wrapper.path_pair.guard"):
            _check_fd_kwargs(kwargs)
            if not _skip_path_check_for_dir_fd(kwargs):
                _check_path_pair(
                    src,
                    dst,
                    source_operation=source_operation,
                    target_operation=target_operation,
                )
        return original(src, dst, *args, **kwargs)

    return wrapper


def _wrap_path_method(original, attr: str):
    def wrapper(self, *args, **kwargs):
        _profile_count("process_guard.wrapper.path_method.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(self, *args, **kwargs)
        with _profile_span("process_guard.wrapper.path_method.guard"):
            _check_path(self, operation=_path_method_operation(self, attr, args, kwargs))
        return original(self, *args, **kwargs)

    return wrapper


def _wrap_path_pair_method(original, source_operation: str, target_operation: str):
    def wrapper(self, target, *args, **kwargs):
        _profile_count("process_guard.wrapper.path_pair_method.calls")
        if _PATH_CHECK_DEPTH.get() > 0:
            return original(self, target, *args, **kwargs)
        with _profile_span("process_guard.wrapper.path_pair_method.guard"):
            _check_path_pair(
                self,
                target,
                source_operation=source_operation,
                target_operation=target_operation,
            )
        return original(self, target, *args, **kwargs)

    return wrapper


def _wrap_shutil_unpack_archive(original):
    def wrapper(filename, extract_dir=None, *args, **kwargs):
        _check_path(filename, operation="read")
        if extract_dir is not None:
            _check_path(extract_dir, operation="create")
        return original(filename, extract_dir, *args, **kwargs)

    return wrapper


def _wrap_shutil_make_archive(original):
    def wrapper(base_name, format, root_dir=None, base_dir=None, *args, **kwargs):
        _check_path(base_name, operation=_create_or_modify_operation(base_name))
        if root_dir is not None:
            _check_path(root_dir, operation="read")
        if base_dir is not None:
            _check_path(base_dir, operation="read")
        return original(base_name, format, root_dir, base_dir, *args, **kwargs)

    return wrapper


def _wrap_import(original):
    def wrapper(name, globals=None, locals=None, fromlist=(), level=0):
        _profile_count("process_guard.wrapper.import.calls")
        with _profile_span("process_guard.wrapper.import.guard"):
            if _bypass_enabled():
                return original(name, globals, locals, fromlist, level)
            current_state = _state()
            if not current_state:
                return original(name, globals, locals, fromlist, level)
            root_name = str(name or "").split(".", 1)[0]
            allowed_imports = current_state.get("allowed_import_roots") or set()
            if not allowed_imports:
                allowed_imports = set(
                    _normalize_import_roots(list(current_state.get("allowed_imports") or []))
                )
            if root_name in _SENSITIVE_IMPORT_ROOTS and root_name not in allowed_imports:
                raise PermissionError(f"sandbox_module_denied:{root_name}")
            return original(name, globals, locals, fromlist, level)

    return wrapper


def _patch_attr(owner: Any, attr: str, wrapper_factory) -> None:
    original = getattr(owner, attr, None)
    if not callable(original):
        return
    if owner is pathlib.Path:
        key = f"pathlib.Path.{attr}"
    else:
        key = f"{owner.__name__}.{attr}"
    if key not in _ORIGINALS:
        _ORIGINALS[key] = original
    setattr(owner, attr, wrapper_factory(original))


def _wrap_shutil_single_path(original, operation: str):
    def wrapper(path, *args, **kwargs):
        _profile_count("process_guard.wrapper.shutil_single.calls")
        with _profile_span("process_guard.wrapper.shutil_single.guard"):
            _check_path(path, operation=operation)
        if operation == "delete" and getattr(original, "__name__", "") == "rmtree":
            with _internal_fd_path_context():
                return original(path, *args, **kwargs)
        return original(path, *args, **kwargs)

    return wrapper


def _wrap_shutil_path_pair(original, source_operation: str, target_operation: str):
    def wrapper(src, dst, *args, **kwargs):
        _profile_count("process_guard.wrapper.shutil_path_pair.calls")
        with _profile_span("process_guard.wrapper.shutil_path_pair.guard"):
            _check_path_pair(
                src,
                dst,
                source_operation=source_operation,
                target_operation=target_operation,
            )
        return original(src, dst, *args, **kwargs)

    return wrapper


def _command_executable(command: Any, *, shell: bool = False) -> str | None:
    if isinstance(command, (list, tuple)) and command:
        candidate = command[0]
    elif isinstance(command, str):
        if shell:
            try:
                parts = shlex.split(command)
            except ValueError:
                parts = []
            candidate = parts[0] if parts else command
        else:
            candidate = command
    else:
        return None
    text = str(candidate or "").strip()
    if not text:
        return None
    if os.path.isabs(text) or os.sep in text:
        return text
    resolved = shutil.which(text)
    return resolved


def _process_executable_target(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str | None:
    if name == "os.fork":
        return None
    shell = bool(kwargs.get("shell")) or name in {"os.system", "os.popen", "asyncio.create_subprocess_shell"}
    if name == "asyncio.create_subprocess_exec":
        return _command_executable(args[0] if args else None)
    if name == "asyncio.create_subprocess_shell":
        return _command_executable(args[0] if args else None, shell=True)
    command = args[0] if args else kwargs.get("args")
    return _command_executable(command, shell=shell)


def _process_command_text(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    command = args[0] if args else kwargs.get("args")
    if isinstance(command, str):
        return command.strip()
    return ""


def _process_command_allowed(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> bool:
    command = _process_command_text(name, args, kwargs)
    if not command:
        return False
    return command in set(_state().get("allowed_subprocess_commands") or [])


def _launcher_pythonpath(env: dict[str, str]) -> str:
    app_root = os.path.dirname(
        os.path.dirname(
            os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)),
            )
        )
    )
    current = str(env.get("PYTHONPATH") or "").strip()
    if not current:
        return app_root
    entries = current.split(os.pathsep)
    if app_root in entries:
        return current
    return os.pathsep.join([app_root, current])


def _subprocess_command_sequence(command: Any) -> list[str] | None:
    if not isinstance(command, (list, tuple)) or not command:
        return None
    return [os.fspath(item) for item in command]


def _is_launcher_command(command: list[str]) -> bool:
    return len(command) >= 3 and command[1:3] == [
        "-m",
        "democrai.core.infrastructure.sandbox.launcher",
    ]


def _run_subprocess_via_launcher(
    original,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    cleanup_policy: bool = True,
):
    if bool(kwargs.get("shell")):
        return None
    command = args[0] if args else kwargs.get("args")
    command_sequence = _subprocess_command_sequence(command)
    if command_sequence is None or _is_launcher_command(command_sequence):
        return None

    raw_env = kwargs.get("env")
    policy_env = (
        {str(key): str(value) for key, value in dict(raw_env).items()}
        if isinstance(raw_env, dict)
        else dict(os.environ)
    )
    with process_guard_bypass_context():
        sandbox_launcher = importlib.import_module("democrai.core.infrastructure.sandbox.launcher")
        policy_path = sandbox_launcher._write_policy(
            command=command_sequence,
            cwd=str(kwargs["cwd"]) if kwargs.get("cwd") is not None else None,
            env=policy_env,
        )
    launcher_env = dict(policy_env)
    launcher_env["PYTHONPATH"] = _launcher_pythonpath(launcher_env)
    launcher_command = [
        sys.executable,
        "-m",
        "democrai.core.infrastructure.sandbox.launcher",
        str(policy_path),
    ]
    launcher_kwargs = dict(kwargs)
    launcher_kwargs["env"] = launcher_env
    launcher_kwargs.pop("cwd", None)
    if args:
        launcher_args = (launcher_command, *args[1:])
    else:
        launcher_args = ()
        launcher_kwargs["args"] = launcher_command
    try:
        return original(*launcher_args, **launcher_kwargs)
    finally:
        if cleanup_policy:
            with process_guard_bypass_context():
                try:
                    policy_path.unlink()
                except OSError:
                    pass


def _check_execute_target(target: str) -> None:
    depth = _PATH_CHECK_DEPTH.get()
    if depth > 0:
        return
    token = _PATH_CHECK_DEPTH.set(depth + 1)
    try:
        if _path_allowed(target, operation="execute"):
            return
        try:
            if _external_filesystem_access_allowed(
                target,
                operation="execute",
                register_request=True,
            ):
                return
        except Exception:
            _debug_path_denial(target, operation="execute")
            raise
        _debug_path_denial(target, operation="execute")
        raise PermissionError(
            f"sandbox_filesystem_execute_denied:{_state().get('subject') or 'subject'}:{target}"
        )
    finally:
        _PATH_CHECK_DEPTH.reset(token)


def _blocked_process_call(name: str, original):
    def wrapper(*args, **kwargs):
        if _bypass_enabled():
            return original(*args, **kwargs)
        current_state = _state()
        if bool(current_state.get("allow_subprocess")):
            return original(*args, **kwargs)
        if name == "os.fork" and bool(current_state.get("allow_fork")):
            return original(*args, **kwargs)
        if _process_command_allowed(name, args, kwargs):
            return original(*args, **kwargs)
        target = _process_executable_target(name, args, kwargs)
        if target:
            _check_execute_target(target)
            if name in {"subprocess.run", "subprocess.Popen"}:
                launched = _run_subprocess_via_launcher(
                    original,
                    args,
                    kwargs,
                    cleanup_policy=name != "subprocess.Popen",
                )
                if launched is not None:
                    return launched
            return original(*args, **kwargs)
        raise PermissionError(f"sandbox_subprocess_denied:{name}")

    return wrapper


def _wrap_putenv(original):
    def wrapper(key, value, *args, **kwargs):
        if _bypass_enabled() or not _state() or not _protected_env_name(key):
            return original(key, value, *args, **kwargs)
        raise PermissionError(f"sandbox_env_denied:{key}")

    return wrapper


def _wrap_unsetenv(original):
    def wrapper(key, *args, **kwargs):
        if _bypass_enabled() or not _state() or not _protected_env_name(key):
            return original(key, *args, **kwargs)
        raise PermissionError(f"sandbox_env_denied:{key}")

    return wrapper


def _wrap_environ_setitem(original):
    def wrapper(self, key, value):
        if _bypass_enabled() or not _state() or not _protected_env_name(key):
            return original(self, key, value)
        raise PermissionError(f"sandbox_env_denied:{key}")

    return wrapper


def _wrap_environ_delitem(original):
    def wrapper(self, key):
        if _bypass_enabled() or not _state() or not _protected_env_name(key):
            return original(self, key)
        raise PermissionError(f"sandbox_env_denied:{key}")

    return wrapper


def _wrap_thread_start(original):
    def wrapper(self, *args, **kwargs):
        if _bypass_enabled():
            return original(self, *args, **kwargs)
        current_state = _state()
        if not current_state:
            return original(self, *args, **kwargs)
        if getattr(self, "_democrai_context_wrapped", False):
            return original(self, *args, **kwargs)
        captured = contextvars.copy_context()
        original_run = self.run

        def _run_with_context(*run_args, **run_kwargs):
            return captured.run(original_run, *run_args, **run_kwargs)

        self.run = _run_with_context
        setattr(self, "_democrai_context_wrapped", True)
        return original(self, *args, **kwargs)

    return wrapper


def _wrap_threadpool_submit(original):
    def wrapper(self, fn, /, *args, **kwargs):
        if _bypass_enabled():
            return original(self, fn, *args, **kwargs)
        current_state = _state()
        if not current_state:
            return original(self, fn, *args, **kwargs)
        captured = contextvars.copy_context()

        def _run_with_context(*inner_args, **inner_kwargs):
            return captured.run(fn, *inner_args, **inner_kwargs)

        return original(self, _run_with_context, *args, **kwargs)

    return wrapper


def enable_process_guard(
    *,
    subject: str,
    subject_kind: str = "module",
    access: list[AccessManifestRule] | tuple[AccessManifestRule, ...] | None = None,
    allowed_imports: list[str] | None = None,
    allowed_subprocess_commands: list[str] | None = None,
    allow_subprocess: bool = False,
    allow_fork: bool = False,
    include_runtime_access: bool = True,
    inherit_parent_access: bool = True,
    user_id: int | None = None,
    organization_id: int | None = None,
    session_key: str | None = None,
) -> contextvars.Token:
    global _ACTIVE, _ACTIVE_COUNT
    with _profile_span("process_guard.enable.prepare_state"):
        parent_state = _state()
        runtime_user_id, runtime_organization_id, runtime_session_key = _request_context_from_runtime()
        parent_access = tuple(parent_state.get("access") or ()) if inherit_parent_access else ()
        caller_access = tuple(access or ())
        root_runtime_access = (
            _runtime_access()
            if include_runtime_access and not parent_state
            else ()
        )
        with _profile_span("process_guard.enable.merge_access"):
            merged_access = _merge_access_rules(
                parent_access,
                root_runtime_access,
                caller_access,
            )
        parent_imports = list(parent_state.get("allowed_imports") or []) if inherit_parent_access else []
        merged_imports = _normalize_import_roots(parent_imports + list(allowed_imports or []))
        parent_subprocess_commands = (
            [str(value).strip() for value in list(parent_state.get("allowed_subprocess_commands") or [])]
            if inherit_parent_access
            else []
        )
        merged_subprocess_commands = [
            item
            for item in (
                parent_subprocess_commands
                + [str(value).strip() for value in list(allowed_subprocess_commands or [])]
            )
            if item
        ]
        resolved_subject = (
            str(subject or "").strip() or str(parent_state.get("subject") or "").strip()
        )
        resolved_subject_kind = _normalize_subject_kind(
            subject_kind or parent_state.get("subject_kind")
        )
        resolved_subject_entry = _normalize_subject_entry(
            resolved_subject_kind,
            resolved_subject,
        )
        resolved_subject_allow_entry = (
            _subject_access_entry(
                resolved_subject_entry,
                _merge_access_rules(root_runtime_access, caller_access),
            )
        )
        if parent_state:
            with process_guard_bypass_context():
                debug_os_sandbox_flow(
                    "process_guard.nested_access",
                    parent_subject=str(parent_state.get("subject") or ""),
                    parent_subject_kind=str(parent_state.get("subject_kind") or ""),
                    child_subject=resolved_subject,
                    child_subject_kind=resolved_subject_kind,
                    include_runtime_access=bool(include_runtime_access),
                    parent_filesystem_access=_filesystem_access_summary(parent_access),
                    runtime_filesystem_access=_filesystem_access_summary(root_runtime_access),
                    child_filesystem_access=_filesystem_access_summary(caller_access),
                    merged_filesystem_access=_filesystem_access_summary(merged_access),
                )
        resolved_user_id = (
            user_id
            if user_id is not None
            else parent_state.get("user_id")
            if parent_state.get("user_id") is not None
            else runtime_user_id
        )
        resolved_organization_id = (
            organization_id
            if organization_id is not None
            else parent_state.get("organization_id")
            if parent_state.get("organization_id") is not None
            else runtime_organization_id
        )
        resolved_session_key = (
            str(session_key or "").strip()
            or parent_state.get("session_key")
            or runtime_session_key
        )
    _EXTERNAL_ACCESS_CACHE.set({})
    with _profile_span("process_guard.enable.set_state"):
        filesystem_access = _filesystem_access_by_operation(merged_access)
        token = _STATE.set(
            {
                "subject": resolved_subject,
                "subject_kind": resolved_subject_kind,
                "subject_chain": _merge_subject_chain(
                    parent_state.get("subject_chain"),
                    resolved_subject_entry,
                ),
                "subject_access_chain": _merge_subject_access_chain(
                    parent_state.get("subject_access_chain"),
                    resolved_subject_allow_entry,
                ),
                "access": merged_access,
                "filesystem_access": filesystem_access,
                "path_access_cache": {},
                "allowed_imports": merged_imports,
                "allowed_import_roots": set(merged_imports),
                "allowed_subprocess_commands": merged_subprocess_commands,
                "allow_subprocess": (
                    bool(parent_state.get("allow_subprocess")) if inherit_parent_access else False
                )
                or bool(allow_subprocess),
                "allow_fork": (
                    bool(parent_state.get("allow_fork")) if inherit_parent_access else False
                )
                or bool(allow_fork),
                "user_id": to_optional_int(resolved_user_id),
                "organization_id": to_optional_int(resolved_organization_id),
                "session_key": str(resolved_session_key or "").strip() or None,
            }
        )
    with _profile_span("process_guard.enable.active_count"):
        with _ACTIVE_LOCK:
            _ACTIVE_COUNT += 1
            if _ACTIVE:
                return token
            _ACTIVE = True

    with _profile_span("process_guard.enable.patch_globals"):
        _ORIGINALS["builtins.open"] = builtins.open
        builtins.open = _wrap_open(builtins.open)
        _ORIGINALS["builtins.__import__"] = builtins.__import__
        builtins.__import__ = _wrap_import(builtins.__import__)
        _ORIGINALS["io.open"] = io.open
        io.open = _wrap_open(io.open)
        _ORIGINALS["os.open"] = os.open
        os.open = _wrap_os_open(os.open)
        _ORIGINALS["threading.Thread.start"] = threading.Thread.start
        threading.Thread.start = _wrap_thread_start(threading.Thread.start)
        _ORIGINALS[
            "concurrent.futures.ThreadPoolExecutor.submit"
        ] = concurrent.futures.ThreadPoolExecutor.submit
        concurrent.futures.ThreadPoolExecutor.submit = _wrap_threadpool_submit(
            concurrent.futures.ThreadPoolExecutor.submit
        )
        _patch_attr(os, "putenv", _wrap_putenv)
        _patch_attr(os, "unsetenv", _wrap_unsetenv)
        environ_cls = type(os.environ)
        if "os.environ.__setitem__" not in _ORIGINALS:
            _ORIGINALS["os.environ.__setitem__"] = environ_cls.__setitem__
            environ_cls.__setitem__ = _wrap_environ_setitem(environ_cls.__setitem__)
        if "os.environ.__delitem__" not in _ORIGINALS:
            _ORIGINALS["os.environ.__delitem__"] = environ_cls.__delitem__
            environ_cls.__delitem__ = _wrap_environ_delitem(environ_cls.__delitem__)

        for module_name in ("posix", "nt"):
            module = sys.modules.get(module_name)
            if module is None:
                continue
            for attr in ("access", "chdir", "listdir", "lstat", "readlink", "scandir", "stat"):
                _patch_attr(module, attr, lambda original, op="read", name=attr: _wrap_os_optional_path(original, op, name))
            for attr in ("chmod", "chown", "truncate", "utime"):
                _patch_attr(module, attr, lambda original, op="modify", name=attr: _wrap_os_optional_path(original, op, name))
            _patch_attr(module, "mkdir", lambda original: _wrap_os_optional_path(original, "create", "mkdir"))
            for attr in ("remove", "rmdir", "unlink"):
                _patch_attr(module, attr, lambda original, op="delete", name=attr: _wrap_os_optional_path(original, op, name))
            for attr in ("link",):
                _patch_attr(module, attr, lambda original: _wrap_path_pair(original, "read", "create"))
            for attr in ("rename", "replace"):
                _patch_attr(module, attr, lambda original: _wrap_path_pair(original, "delete", "create_or_modify"))
            _patch_attr(module, "symlink", lambda original: _wrap_path_pair(original, "read", "create"))

        for attr in ("access", "chdir", "listdir", "scandir", "stat", "lstat", "readlink", "walk", "fwalk"):
            _patch_attr(os, attr, lambda original, op="read", name=attr: _wrap_os_optional_path(original, op, name))
        for attr in ("chmod", "chown", "truncate", "utime"):
            _patch_attr(os, attr, lambda original, op="modify", name=attr: _wrap_os_optional_path(original, op, name))
        _patch_attr(os, "mkdir", lambda original: _wrap_os_optional_path(original, "create", "mkdir"))
        for attr in ("remove", "unlink", "rmdir"):
            _patch_attr(os, attr, lambda original, op="delete", name=attr: _wrap_os_optional_path(original, op, name))
        _patch_attr(os, "makedirs", _wrap_os_makedirs)
        _patch_attr(os, "removedirs", lambda original: _wrap_os_default_path(original, ".", "delete", "removedirs"))
        _patch_attr(os, "link", lambda original: _wrap_path_pair(original, "read", "create"))
        for attr in ("rename", "renames", "replace"):
            _patch_attr(os, attr, lambda original: _wrap_path_pair(original, "delete", "create_or_modify"))
        _patch_attr(os, "symlink", lambda original: _wrap_path_pair(original, "read", "create"))

        for attr in (
            "exists",
            "lexists",
            "getatime",
            "getctime",
            "getmtime",
            "getsize",
            "isdir",
            "isfile",
            "islink",
            "ismount",
        ):
            _patch_attr(os.path, attr, lambda original, op="read", name=attr: _wrap_os_optional_path(original, op, name))
        _patch_attr(os.path, "samefile", lambda original: _wrap_path_pair(original, "read", "read"))

        for attr in (
            "open",
            "read_text",
            "write_text",
            "read_bytes",
            "write_bytes",
            "mkdir",
            "iterdir",
            "glob",
            "rglob",
            "unlink",
            "rmdir",
            "stat",
            "lstat",
            "exists",
            "resolve",
            "readlink",
            "owner",
            "group",
            "chmod",
            "lchmod",
            "touch",
            "is_dir",
            "is_file",
            "is_symlink",
            "is_mount",
            "is_block_device",
            "is_char_device",
            "is_fifo",
            "is_socket",
            "walk",
        ):
            _patch_attr(pathlib.Path, attr, lambda original, name=attr: _wrap_path_method(original, name))
        for attr in ("rename", "replace"):
            _patch_attr(pathlib.Path, attr, lambda original: _wrap_path_pair_method(original, "delete", "create_or_modify"))
        _patch_attr(pathlib.Path, "samefile", lambda original: _wrap_path_pair_method(original, "read", "read"))
        for attr in ("symlink_to", "hardlink_to"):
            _patch_attr(pathlib.Path, attr, lambda original: _wrap_path_pair_method(original, "create", "read"))

        _patch_attr(shutil, "rmtree", lambda original: _wrap_shutil_single_path(original, "delete"))
        for attr in ("chown", "copymode", "copystat"):
            _patch_attr(shutil, attr, lambda original: _wrap_shutil_single_path(original, "modify"))
        _patch_attr(shutil, "disk_usage", lambda original: _wrap_shutil_single_path(original, "read"))
        for attr in ("copy", "copy2", "copyfile", "copytree"):
            _patch_attr(shutil, attr, lambda original: _wrap_shutil_path_pair(original, "read", "create_or_modify"))
        _patch_attr(shutil, "move", lambda original: _wrap_shutil_path_pair(original, "delete", "create_or_modify"))
        _patch_attr(shutil, "unpack_archive", _wrap_shutil_unpack_archive)
        _patch_attr(shutil, "make_archive", _wrap_shutil_make_archive)

        if not allow_subprocess:
            for owner, attr in (
                (os, "system"),
                (os, "popen"),
                (subprocess, "Popen"),
                (subprocess, "run"),
                (subprocess, "call"),
                (subprocess, "check_call"),
                (subprocess, "check_output"),
            ):
                original = getattr(owner, attr, None)
                if callable(original):
                    _ORIGINALS[f"{owner.__name__}.{attr}"] = original
                    setattr(
                        owner,
                        attr,
                        _blocked_process_call(f"{owner.__name__}.{attr}", original),
                    )
            if hasattr(os, "fork"):
                _ORIGINALS["os.fork"] = os.fork
                os.fork = _blocked_process_call("os.fork", _ORIGINALS["os.fork"])
            for attr in ("create_subprocess_exec", "create_subprocess_shell"):
                original = getattr(asyncio, attr, None)
                if callable(original):
                    _ORIGINALS[f"asyncio.{attr}"] = original
                    setattr(
                        asyncio, attr, _blocked_process_call(f"asyncio.{attr}", original)
                    )
    return token


def disable_process_guard(token: contextvars.Token | None = None) -> None:
    global _ACTIVE, _ACTIVE_COUNT
    with _profile_span("process_guard.disable.reset_state"):
        if token is not None:
            try:
                _STATE.reset(token)
            except Exception:
                _STATE.set(None)
        else:
            _STATE.set(None)
    if not _ACTIVE:
        return
    with _profile_span("process_guard.disable.active_count"):
        with _ACTIVE_LOCK:
            if _ACTIVE_COUNT > 0:
                _ACTIVE_COUNT -= 1
            if _ACTIVE_COUNT > 0:
                return
    _STATE.set(None)
    _EXTERNAL_ACCESS_CACHE.set(None)
    if not _ACTIVE:
        return
    with _profile_span("process_guard.disable.restore_globals"):
        if "builtins.open" in _ORIGINALS:
            builtins.open = _ORIGINALS["builtins.open"]
        if "builtins.__import__" in _ORIGINALS:
            builtins.__import__ = _ORIGINALS["builtins.__import__"]
        if "io.open" in _ORIGINALS:
            io.open = _ORIGINALS["io.open"]
        if "threading.Thread.start" in _ORIGINALS:
            threading.Thread.start = _ORIGINALS["threading.Thread.start"]
        if "concurrent.futures.ThreadPoolExecutor.submit" in _ORIGINALS:
            concurrent.futures.ThreadPoolExecutor.submit = _ORIGINALS[
                "concurrent.futures.ThreadPoolExecutor.submit"
            ]
        environ_cls = type(os.environ)
        if "os.environ.__setitem__" in _ORIGINALS:
            environ_cls.__setitem__ = _ORIGINALS["os.environ.__setitem__"]
        if "os.environ.__delitem__" in _ORIGINALS:
            environ_cls.__delitem__ = _ORIGINALS["os.environ.__delitem__"]
        for key, original in list(_ORIGINALS.items()):
            if not key.startswith("pathlib.Path."):
                continue
            setattr(pathlib.Path, key.split(".", 2)[2], original)
        module_restore_map = {
            "os": os,
            "posix": sys.modules.get("posix"),
            "nt": sys.modules.get("nt"),
            "posixpath": os.path,
            "ntpath": os.path,
            "subprocess": subprocess,
            "shutil": shutil,
            "asyncio": asyncio,
        }
        for key, original in list(_ORIGINALS.items()):
            owner_name, _, attr = key.partition(".")
            owner = module_restore_map.get(owner_name)
            if (
                owner is None
                or not attr
                or owner_name in {"builtins", "io", "pathlib"}
                or key.startswith("os.environ.")
            ):
                continue
            setattr(owner, attr, original)
        _ORIGINALS.clear()
        _ACTIVE = False
        _STATE.set(None)
        _EXTERNAL_ACCESS_CACHE.set(None)


class process_guard_context:
    def __init__(
        self,
        *,
        subject: str,
        subject_kind: str = "module",
        access: list[AccessManifestRule] | tuple[AccessManifestRule, ...] | None = None,
        allowed_imports: list[str] | None = None,
        allowed_subprocess_commands: list[str] | None = None,
        allow_subprocess: bool = False,
        allow_fork: bool = False,
        include_runtime_access: bool = True,
        inherit_parent_access: bool = True,
        user_id: int | None = None,
        organization_id: int | None = None,
        session_key: str | None = None,
    ) -> None:
        self.subject = str(subject or "").strip()
        self.subject_kind = _normalize_subject_kind(subject_kind)
        self.access = tuple(access or ())
        self.allowed_imports = list(allowed_imports or [])
        self.allowed_subprocess_commands = list(allowed_subprocess_commands or [])
        self.allow_subprocess = bool(allow_subprocess)
        self.allow_fork = bool(allow_fork)
        self.include_runtime_access = bool(include_runtime_access)
        self.inherit_parent_access = bool(inherit_parent_access)
        self.user_id = user_id
        self.organization_id = organization_id
        self.session_key = session_key
        self._network_ctx = network_policy_context(
            subject_name=self.subject,
            subject_type=self.subject_kind,
            user_id=self.user_id,
            organization_id=self.organization_id,
            session_key=self.session_key,
        )
        self._token: contextvars.Token | None = None

    def __enter__(self) -> "process_guard_context":
        with _profile_span("process_guard.context.enter"):
            self._token = enable_process_guard(
                subject=self.subject,
                subject_kind=self.subject_kind,
                access=self.access,
                allowed_imports=self.allowed_imports,
                allowed_subprocess_commands=self.allowed_subprocess_commands,
                allow_subprocess=self.allow_subprocess,
                allow_fork=self.allow_fork,
                include_runtime_access=self.include_runtime_access,
                inherit_parent_access=self.inherit_parent_access,
                user_id=self.user_id,
                organization_id=self.organization_id,
                session_key=self.session_key,
            )
            with _profile_span("process_guard.network.enter"):
                self._network_ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        with _profile_span("process_guard.context.exit"):
            with _profile_span("process_guard.network.exit"):
                self._network_ctx.__exit__(exc_type, exc, tb)
            disable_process_guard(self._token)


@contextlib.contextmanager
def process_guard_bypass_context() -> contextlib.AbstractContextManager[None]:
    token = _BYPASS.set(True)
    try:
        yield
    finally:
        _BYPASS.reset(token)


def process_guard_context_from_env() -> contextlib.AbstractContextManager[None]:
    subject = str(os.environ.get("DEMOCRAI_NETWORK_SUBJECT") or "").strip()
    subject_kind = str(os.environ.get("DEMOCRAI_NETWORK_SUBJECT_KIND") or "").strip()
    raw_access = str(os.environ.get("DEMOCRAI_ACCESS") or "").strip()
    if not subject:
        return contextlib.nullcontext()
    access_payload = json.loads(raw_access) if raw_access else []
    if not isinstance(access_payload, list):
        raise RuntimeError("process_guard_env_access_must_be_list")
    return process_guard_context(
        subject=subject,
        subject_kind=subject_kind or "module",
        access=_access_rules_from_dicts(access_payload),
        user_id=to_optional_int(os.environ.get("DEMOCRAI_USER_ID")),
        organization_id=to_optional_int(os.environ.get("DEMOCRAI_ORGANIZATION_ID")),
        session_key=str(os.environ.get("DEMOCRAI_SESSION_KEY") or "").strip() or None,
    )
