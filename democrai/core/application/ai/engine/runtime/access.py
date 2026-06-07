from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from democrai.core.application.access_policy import AccessManifestRule
from democrai.core.application.access_policy import AccessResource
from democrai.core.application.access_policy import AccessSubject
from democrai.core.application.access_policy.manifest import parse_access_manifest_rules
from democrai.core.application.ai.engine.access_constants import (
    DEFAULT_ENGINE_INSTALL_RECEIVE_URLS,
    engine_runtime_device_modify_paths,
    engine_runtime_device_read_paths,
)
from democrai.core.application.ai.engine.runtime.environment import (
    engine_phase_access_section,
    engine_phase_section,
)
from democrai.core.application.ai.engine.runtime.toolchain import (
    engine_runtime_engine_env_executable_paths,
    ensure_engine_runtime_driver_libs,
    ensure_engine_runtime_toolchain,
)
from democrai.core.runtime.dependencies.engine_env import (
    get_engine_local_cache_path,
    get_engine_local_config_path,
    get_engine_local_env_path,
    get_engine_local_tmp_path,
    get_engine_venv_path,
    get_engine_venv_python_path,
)
from democrai.core.runtime.foundation.app import app_ctx


def _allowed_config_url_keys(section: dict[str, Any]) -> list[str]:
    raw = section.get("allowed_config_urls")
    if isinstance(raw, str):
        return [raw] if raw else []
    if isinstance(raw, list):
        return [item for item in raw if item]
    return []


def _config_urls_by_keys(config: dict[str, Any] | None, keys: list[str]) -> list[str]:
    values: list[str] = []
    payload = config or {}
    for key in keys:
        current = payload.get(key)
        if isinstance(current, str):
            if current:
                values.append(current)
            continue
        if isinstance(current, list):
            for item in current:
                if item:
                    values.append(item)
    return values


def get_engine_network_access(
    engine_id: str,
    phase: str,
    config: dict[str, Any] | None = None,
) -> tuple[AccessManifestRule, ...]:
    section = engine_phase_section(engine_id, phase)
    subject = AccessSubject.create("engine", engine_id)
    access = [
        *parse_access_manifest_rules(
            engine_phase_access_section(engine_id, phase),
            subject_type="engine",
            subject_name=engine_id,
        )
    ]
    if phase == "install":
        access.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation="receive",
                    target=target,
                ),
            )
            for target in DEFAULT_ENGINE_INSTALL_RECEIVE_URLS
        )
    for target in _config_urls_by_keys(config, _allowed_config_url_keys(section)):
        access.append(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation="connect",
                    target=target,
                ),
            )
        )
        access.append(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation="send",
                    target=target,
                ),
            )
        )
        access.append(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="network",
                    operation="receive",
                    target=target,
                ),
            )
        )
    return tuple(access)


def get_engine_filesystem_access(engine_id: str, phase: str) -> tuple[AccessManifestRule, ...]:
    subject = AccessSubject.create("engine", engine_id)
    engine_env_path = str(get_engine_local_env_path(engine_id).resolve())
    engine_venv_path = str(get_engine_venv_path(engine_id).resolve())
    rules = [
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="filesystem",
                operation="read",
                target=path,
            ),
        )
        for path in [
            engine_env_path,
            engine_venv_path,
        ]
    ]
    if phase in {"install", "runtime"}:
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation=operation,
                    target=engine_env_path,
                ),
            )
            for operation in ("create", "modify", "delete")
        )
    if phase in {"install", "runtime"}:
        cache_path = str(get_engine_local_cache_path(engine_id).resolve())
        config_path = str(get_engine_local_config_path(engine_id).resolve())
        tmp_path = str(get_engine_local_tmp_path(engine_id).resolve())
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation=operation,
                    target=cache_path,
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
                    target=tmp_path,
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
    if phase in {"install", "runtime"}:
        executable_targets = tuple(
            dict.fromkeys(
                (
                    str(sys.executable),
                    os.path.realpath(str(sys.executable)),
                    str(get_engine_venv_python_path(engine_id)),
                    os.path.realpath(str(get_engine_venv_python_path(engine_id))),
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
    if phase == "runtime":
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=path,
                ),
            )
            for path in engine_runtime_device_read_paths()
        )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="modify",
                    target=path,
                ),
            )
            for path in engine_runtime_device_modify_paths()
        )
        driver_lib_path, driver_lib_targets = ensure_engine_runtime_driver_libs(engine_id)
        if driver_lib_path is not None:
            rules.append(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation="read",
                        target=str(driver_lib_path),
                    ),
                )
            )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=str(path),
                ),
            )
            for path in driver_lib_targets
        )
        compiler_path, compiler_targets = ensure_engine_runtime_toolchain(engine_id)
        if compiler_path is not None:
            toolchain_bin_path = compiler_path.parent
            rules.append(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation="read",
                        target=str(toolchain_bin_path),
                    ),
                )
            )
            rules.append(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation="execute",
                        target=str(toolchain_bin_path),
                    ),
                )
            )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=str(path),
                ),
            )
            for path in compiler_targets
        )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="execute",
                    target=str(path),
                ),
            )
            for path in compiler_targets
        )
        engine_env_executable_paths = engine_runtime_engine_env_executable_paths(engine_id)
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="read",
                    target=str(path),
                ),
            )
            for path in engine_env_executable_paths
        )
        rules.extend(
            AccessManifestRule(
                subject=subject,
                resource=AccessResource.create(
                    resource_type="filesystem",
                    operation="execute",
                    target=str(path),
                ),
            )
            for path in engine_env_executable_paths
        )
        media_models_path = _local_media_models_path()
        if media_models_path:
            rules.append(
                AccessManifestRule(
                    subject=subject,
                    resource=AccessResource.create(
                        resource_type="filesystem",
                        operation="read",
                        target=media_models_path,
                    ),
                )
            )
    return tuple(rules)


def _local_media_models_path() -> str:
    config = app_ctx().config
    if config is None:
        return ""
    media_type = config.get("storage.media.type", "local")
    if media_type != "local":
        return ""
    media_path = config.get("storage.media.path")
    if not media_path:
        return ""
    return str(Path(media_path).expanduser().resolve() / "models")


def get_engine_allowed_imports(engine_id: str, phase: str) -> list[str]:
    section = engine_phase_section(engine_id, phase)
    return [
        item.split(".", 1)[0]
        for item in section.get("allowed_imports", [])
        if item
    ]


def get_engine_access(
    engine_id: str,
    phase: str,
    config: dict[str, Any] | None = None,
) -> tuple[AccessManifestRule, ...]:
    return (
        *get_engine_filesystem_access(engine_id, phase),
        *get_engine_network_access(engine_id, phase, config=config),
    )
