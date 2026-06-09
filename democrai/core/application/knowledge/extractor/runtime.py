"""Runtime manager for installable external knowledge extractors.

The runtime tracks extractor instances, installation status, path permissions,
and the trusted execution context required to run third-party extraction code.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import threading
from dataclasses import dataclass, field
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
from democrai.core.application.knowledge.extractor.access_constants import (
    extractor_runtime_create_paths,
    extractor_runtime_dependency_read_paths,
    extractor_runtime_modify_paths,
    extractor_runtime_read_paths,
    extractor_runtime_system_probe_read_paths,
)
from democrai.core.application.knowledge.extractor.manifests import (
    get_extractor_manifest,
    load_extractor_class,
)
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_cache_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_config_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_env_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_local_tmp_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_venv_path
from democrai.core.runtime.dependencies.extractor_env import get_extractor_venv_python_path
from democrai.core.runtime.dependencies.extractor_env import extractor_env_context
from democrai.core.runtime.dependencies.extractor_env import isolate_extractor_imports
from democrai.core.application.knowledge.extractor.worker_subject import (
    ExtractorWorkerSubject,
)
from democrai.core.application.knowledge.extractor.worker_subject import (
    worker_runtime_config,
)
from democrai.core.infrastructure.sandbox.process_guard import process_guard_context
from democrai.core.platform.utils.normalize import os_key
from democrai.core.runtime.foundation.paths import logs_dir

_EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET_ENV = "DEMOCRAI_EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET"


def _extractor_phase_section(extractor_id: str, phase: str) -> dict[str, Any]:
    manifest = get_extractor_manifest(extractor_id) or {}
    if not manifest:
        normalized = str(extractor_id or "").strip().lower()
        manifest_path = (
            Path(__file__).resolve().parents[5]
            / "extractors"
            / normalized
            / "manifest.json"
        )
        try:
            loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            loaded = None
        if isinstance(loaded, dict):
            manifest = loaded
    section = manifest.get(phase) if isinstance(manifest, dict) else None
    return section if isinstance(section, dict) else {}


def _extractor_phase_access_section(extractor_id: str, phase: str) -> dict[str, Any]:
    section = deepcopy(_extractor_phase_section(extractor_id, phase))
    access = [
        item
        for item in section.get("access", [])
    ]
    raw_access_by_os = section.get("access_by_os")
    if isinstance(raw_access_by_os, dict):
        os_access = raw_access_by_os.get(os_key())
        if isinstance(os_access, list):
            access.extend(os_access)
    section["access"] = access
    return section


def get_extractor_allowed_imports(extractor_id: str, phase: str) -> list[str]:
    section = _extractor_phase_section(extractor_id, phase)
    return [
        str(item).strip().split(".", 1)[0]
        for item in list(section.get("allowed_imports") or [])
        if str(item).strip()
    ]


def get_extractor_environment(extractor_id: str, phase: str) -> dict[str, str]:
    section = _extractor_phase_section(extractor_id, phase)
    environment = section.get("environment")
    if environment is None:
        return {}
    if not isinstance(environment, dict):
        raise ValueError("invalid_extractor_environment")
    for key, value in environment.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("invalid_extractor_environment")
    return dict(environment)


def _contains_model_registry_source(value: Any) -> bool:
    if isinstance(value, dict):
        source = value.get("source")
        if isinstance(source, dict) and source.get("type") == "model_registry":
            return True
        return any(_contains_model_registry_source(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_model_registry_source(item) for item in value)
    return False


def _extractor_uses_engine_orchestrator(extractor_id: str) -> bool:
    runtime_section = _extractor_phase_section(extractor_id, "runtime")
    return _contains_model_registry_source(runtime_section.get("config_schema"))


def _extractor_framework_runtime_access(
    extractor_id: str,
    phase: str,
) -> tuple[AccessManifestRule, ...]:
    if phase != "runtime" or not _extractor_uses_engine_orchestrator(extractor_id):
        return ()
    from democrai.core.infrastructure.sandbox.worker_launch import framework_ipc_access

    return framework_ipc_access(
        subject_kind="extractor",
        subject_name=extractor_id,
    )


def get_extractor_access(
    extractor_id: str,
    phase: str,
) -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("extractor", extractor_id)
    rules = list(
        parse_access_manifest_rules(
            _extractor_phase_access_section(extractor_id, phase),
            subject_type="extractor",
            subject_name=extractor_id,
        )
    )
    if phase in {"install", "runtime"}:
        env_path = str(get_extractor_local_env_path(extractor_id).resolve())
        cache_path = str(get_extractor_local_cache_path(extractor_id).resolve())
        config_path = str(get_extractor_local_config_path(extractor_id).resolve())
        tmp_path = str(get_extractor_local_tmp_path(extractor_id).resolve())
        venv_path = str(get_extractor_venv_path(extractor_id).resolve())
        log_path = str(logs_dir().resolve())
        rules.append(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=env_path,
                ),
            )
        )
        rules.append(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=venv_path,
                ),
            )
        )
        for operation in ("create", "modify", "delete"):
            rules.append(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation=operation,
                        target=env_path,
                    ),
                )
            )
        for path in (cache_path, tmp_path):
            rules.extend(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation=operation,
                        target=path,
                    ),
                )
                for operation in ("read", "create", "modify", "delete")
            )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation=operation,
                    target=config_path,
                ),
            )
            for operation in ("read", "create", "modify")
        )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation=operation,
                    target=log_path,
                ),
            )
            for operation in ("read", "create", "modify", "delete")
        )
        for operation, paths in (
            (
                "read",
                (
                    *extractor_runtime_read_paths(),
                    *extractor_runtime_system_probe_read_paths(),
                    *extractor_runtime_dependency_read_paths(),
                ),
            ),
            ("modify", extractor_runtime_modify_paths()),
        ):
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
            )
    if phase in {"install", "runtime"}:
        executable_targets = tuple(
            dict.fromkeys(
                (
                    str(sys.executable),
                    os.path.realpath(str(sys.executable)),
                    str(get_extractor_venv_python_path(extractor_id)),
                    os.path.realpath(str(get_extractor_venv_python_path(extractor_id))),
                )
            )
        )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="execute",
                    target=target,
                ),
            )
            for target in executable_targets
        )
        for operation, paths in (
            ("create", extractor_runtime_create_paths()),
        ):
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
            )
    framework_rules = _extractor_framework_runtime_access(extractor_id, phase)
    if framework_rules:
        from democrai.core.infrastructure.sandbox.worker_launch import merge_access_rules

        return merge_access_rules(tuple(rules), framework_rules)
    return tuple(rules)


def _extractor_install_proxy_access(
    extractor_id: str,
    target: str | None = None,
) -> tuple[AccessManifestRule, ...]:
    target = str(
        target
        if target is not None
        else os.environ.get(_EXTRACTOR_INSTALL_PROXY_CONNECT_TARGET_ENV)
        or ""
    ).strip()
    host, separator, raw_port = target.rpartition(":")
    if host != "127.0.0.1" or separator != ":" or not raw_port.isdigit():
        return ()
    port = int(raw_port)
    if port <= 0 or port > 65535:
        return ()
    subject = AccessSubject.create("extractor", extractor_id)
    return (
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="network",
                operation="connect",
                target=f"127.0.0.1:{port}",
            ),
        ),
    )


@dataclass
class _ExtractorHandle:
    extractor_id: str
    config: dict[str, Any]
    runtime_config: dict[str, Any]
    subject: ExtractorWorkerSubject
    lock: threading.Lock = field(default_factory=threading.Lock)


class ExtractorRuntime:
    """Manage lifecycle, permissions, and invocation of external extractors."""
    def __init__(self) -> None:
        self._handles: dict[int, _ExtractorHandle] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _phase_guard(extractor_id: str, phase: str):
        return process_guard_context(
            subject=extractor_id,
            subject_kind="extractor",
            access=get_extractor_access(extractor_id, phase),
            allowed_imports=get_extractor_allowed_imports(
                extractor_id,
                phase,
            ),
            allow_subprocess=True,
            allow_fork=True,
        )

    def _ensure_handle(
        self,
        *,
        extractor_row_id: int,
        extractor_id: str,
        config: dict[str, Any],
    ) -> _ExtractorHandle:
        runtime_config = worker_runtime_config()
        with self._lock:
            handle = self._handles.get(extractor_row_id)
            if (
                handle is not None
                and handle.extractor_id == extractor_id
                and handle.config == config
                and getattr(handle, "runtime_config", {}) == runtime_config
            ):
                return handle
            stale = handle
            if stale is not None:
                self._handles.pop(extractor_row_id, None)
        if stale is not None:
            stale.subject.close()
        created = _ExtractorHandle(
            extractor_id=extractor_id,
            config=config,
            runtime_config=runtime_config,
            subject=ExtractorWorkerSubject(
                extractor_id=extractor_id,
                phase="runtime",
                config=config,
            ),
        )
        with self._lock:
            self._handles[extractor_row_id] = created
            return created

    def ensure_running(
        self,
        *,
        extractor_row_id: int,
        extractor_id: str,
        config: dict[str, Any],
    ) -> None:
        with self._phase_guard(extractor_id, "runtime"):
            self._ensure_handle(
                extractor_row_id=extractor_row_id,
                extractor_id=extractor_id,
                config=config,
            )

    def invoke_extractor_class_method(
        self,
        *,
        extractor_id: str,
        phase: str,
        method: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        with self._phase_guard(extractor_id, phase):
            worker = ExtractorWorkerSubject(
                extractor_id=extractor_id,
                phase=phase,
            )
            try:
                return worker.invoke_class(method, payload or {})
            finally:
                worker.close()

    def extract_structured(
        self,
        *,
        extractor_row_id: int,
        extractor_id: str,
        config: dict[str, Any],
        files: list[Any],
    ) -> dict[str, Any]:
        with self._phase_guard(extractor_id, "runtime"):
            handle = self._ensure_handle(
                extractor_row_id=extractor_row_id,
                extractor_id=extractor_id,
                config=config,
            )
        with handle.lock:
            payload = handle.subject.extract(config=config, files=files)
            payload["extractor_id"] = extractor_id
            return payload

    def stop_extractor(self, extractor_row_id: int) -> None:
        with self._lock:
            handle = self._handles.pop(extractor_row_id, None)
        if handle is not None:
            handle.subject.close()

    def shutdown(self) -> None:
        with self._lock:
            handles = list(self._handles.values())
            self._handles.clear()
        for handle in handles:
            handle.subject.close()

    async def sync_active_extractors(self) -> None:
        from democrai.core.infrastructure.database import SessionLocal
        from democrai.core.infrastructure.database.models import ExtractorRegistry

        with SessionLocal() as session:
            rows = (
                session.query(ExtractorRegistry)
                .filter(ExtractorRegistry.status == "active")
                .all()
            )
        active_ids = {row.id for row in rows}
        for key in list(self._handles.keys()):
            if key not in active_ids:
                self.stop_extractor(key)
        for row in rows:
            config = dict(getattr(row, "install_config", None) or {})
            config.update(dict(row.config or {}))
            await asyncio.to_thread(
                self.ensure_running,
                extractor_row_id=row.id,
                extractor_id=row.extractor_id,
                config=config,
            )


def get_extractor_runtime() -> ExtractorRuntime:
    from democrai.core.runtime.foundation.app import app_ctx

    ctx = app_ctx()
    runtime = getattr(ctx, "extractor_runtime", None)
    if runtime is None:
        runtime = ExtractorRuntime()
        ctx.extractor_runtime = runtime
    return runtime


def install_extractor_runtime(
    *,
    extractor_id: str,
    force: bool = False,
    node_id: str | None = None,
    event_id: str | None = None,
    source_node_id: str | None = None,
    install_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with process_guard_context(
        subject=extractor_id,
        subject_kind="extractor",
        access=(
            *get_extractor_access(extractor_id, "install"),
            *_extractor_install_proxy_access(extractor_id),
        ),
        allowed_imports=get_extractor_allowed_imports(extractor_id, "install"),
        allow_subprocess=True,
        allow_fork=True,
    ):
        with extractor_env_context(
            extractor_id,
            env=get_extractor_environment(extractor_id, "install"),
        ):
            isolate_extractor_imports(extractor_id)
            extractor_cls = load_extractor_class(extractor_id)
            if extractor_cls is None:
                raise RuntimeError(f"extractor_runtime_class_not_found:{extractor_id}")
            result = extractor_cls._install_local(
                force=force,
                node_id=node_id,
                event_id=event_id,
                source_node_id=source_node_id,
                install_config=dict(install_config or {}),
            )
    return dict(result or {})


def check_extractor_ready_runtime(
    *,
    extractor_id: str,
    node_id: str | None = None,
) -> dict[str, Any]:
    from democrai.core.runtime.dependencies.extractor_env import (
        get_extractor_venv_python_path,
    )

    if not get_extractor_venv_python_path(extractor_id).exists():
        return {
            "extractor_id": extractor_id,
            "node_id": node_id,
            "ready": False,
            "missing_shared": [],
            "missing_local": [],
            "message": "extractor environment not provisioned",
        }
    result = get_extractor_runtime().invoke_extractor_class_method(
        extractor_id=extractor_id,
        phase="runtime",
        method="_check_ready_local",
        payload={"node_id": node_id},
    )
    return dict(result or {})


def extract_with_runtime(
    *,
    extractor_row_id: int,
    extractor_id: str,
    config: dict[str, Any],
    files: list[Any],
) -> dict[str, Any]:
    return get_extractor_runtime().extract_structured(
        extractor_row_id=extractor_row_id,
        extractor_id=extractor_id,
        config=config,
        files=files,
    )
