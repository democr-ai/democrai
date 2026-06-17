from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from democrai.core.application.ai.constants import AIDeployment
from democrai.core.application.ai.engine.config_crypto import decrypt_provider_config
from democrai.core.application.ai.engine.manifests import get_provider_definition
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import EngineRegistry
from democrai.core.runtime.dependencies.env_constants import system_command_path
from democrai.core.runtime.dependencies.installer_env import engine_support_status


def _provider_payload(provider_id: str) -> str:
    if not provider_id:
        raise ValueError("provider_id is required")
    return provider_id


def _provider_config_schema(definition: dict[str, Any]) -> list[dict[str, Any]]:
    schema = definition.get("config_schema") or []
    return [item for item in schema]


def _requires_config(config_schema: list[dict[str, Any]]) -> bool:
    for field in config_schema:
        for validation in field.get("validations") or []:
            if validation.get("rule") == "required":
                return True
    return False


def _missing_dependencies(dependencies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing: list[dict[str, Any]] = []
    for dep in dependencies:
        check_type = dep.get("check_type", "module")
        if check_type == "command_any":
            raw = dep.get("commands", "")
            commands = [
                command.strip() for command in raw.split(",") if command.strip()
            ]
            found = any(_command_exists(command) for command in commands)
        elif check_type == "command":
            command = dep.get("command", "")
            found = bool(command) and _command_exists(command)
        else:
            module_name = dep.get("module", "")
            if not module_name:
                continue
            try:
                found = importlib.util.find_spec(module_name) is not None
            except (ModuleNotFoundError, ValueError):
                found = False
        if not found:
            missing.append(dep)
    return missing


def _command_exists(command_name: str) -> bool:
    if not command_name:
        return False
    for base_dir in [item for item in system_command_path().split(os.pathsep) if item]:
        candidate = Path(base_dir) / command_name
        try:
            if (
                candidate.exists()
                and candidate.is_file()
                and os.access(candidate, os.X_OK)
            ):
                return True
        except Exception:
            continue
    return False


def config_has_required_values(
    provider_id: str,
    config: dict[str, Any] | None,
) -> bool:
    requirements = provider_requirements(provider_id=provider_id)
    values = {
        field["name"]: field.get("value")
        for field in requirements.get("config_schema", [])
        if field.get("name")
    }
    if config is not None:
        values.update(config)
    for field in requirements.get("config_schema", []):
        name = field.get("name")
        if not name:
            continue
        required = any(
            validation.get("rule") == "required"
            for validation in (field.get("validations") or [])
        )
        if not required:
            continue
        value = values.get(name)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def provider_requirements(provider_id: str) -> dict[str, Any]:
    provider = _provider_payload(provider_id)
    definition = get_provider_definition(provider) or {}
    if not definition:
        return {
            "provider": provider,
            "provider_label": provider,
            "supported": False,
            "support_reason": "provider_definition_not_found",
            "configurable": False,
            "remote": False,
            "requires_config": False,
            "dependencies": [],
            "missing_dependencies": [],
            "config_schema": [],
        }

    deployment = definition.get("deployment", "")
    config_schema = _provider_config_schema(definition)
    support = engine_support_status(provider)
    dependencies = [item for item in definition.get("dependencies", [])]
    return {
        "provider": provider,
        "provider_label": definition.get("title")
        or definition.get("label")
        or definition.get("name")
        or provider,
        "supported": support.get("supported"),
        "support_reason": support.get("reason", ""),
        "configurable": definition.get("configurable", False),
        "remote": deployment == AIDeployment.REMOTE,
        "requires_config": _requires_config(config_schema),
        "dependencies": dependencies,
        "missing_dependencies": _missing_dependencies(dependencies),
        "config_schema": config_schema,
    }


async def activation_requirements(engine_registry_id: int) -> dict[str, Any]:
    with SessionLocal() as session:
        row = (
            session.query(EngineRegistry)
            .filter(EngineRegistry.id == engine_registry_id)
            .first()
        )
        if row is None:
            return {
                "ready": False,
                "reason": "engine_registry_row_not_found",
                "engine_registry_id": engine_registry_id,
                "provider": "",
                "provider_label": "",
                "supported": False,
                "requires_config": False,
                "missing_dependencies": [],
                "activation_message": "engine_registry_row_not_found",
            }
        provider = _provider_payload(row.provider)
        config = decrypt_provider_config(provider, row.config)

    requirements = provider_requirements(provider_id=provider)
    if not requirements.get("supported"):
        return {
            "ready": False,
            "reason": "provider_not_supported",
            "engine_registry_id": engine_registry_id,
            "provider": provider,
            "provider_label": requirements.get("provider_label") or provider,
            "supported": False,
            "requires_config": requirements.get("requires_config"),
            "missing_dependencies": [],
            "activation_message": requirements.get("support_reason", ""),
        }

    if not config_has_required_values(provider, config):
        return {
            "ready": False,
            "reason": "missing_config",
            "engine_registry_id": engine_registry_id,
            "provider": provider,
            "provider_label": requirements.get("provider_label") or provider,
            "supported": True,
            "requires_config": requirements.get("requires_config"),
            "missing_dependencies": [],
            "activation_message": "missing_config",
        }

    from democrai.core.application.ai.engine.runtime import check_engine_ready_runtime
    from democrai.core.runtime.dependencies.engine_env import get_engine_venv_python_path

    ready_result = check_engine_ready_runtime(engine_id=provider)
    missing = [
        {"dependency_key": item, "label": item}
        for item in [
            *ready_result.get("missing_shared", []),
            *ready_result.get("missing_local", []),
        ]
        if item
    ]
    if not ready_result.get("ready"):
        if not missing:
            if not get_engine_venv_python_path(provider, create=False).exists():
                # If the engine venv does not exist yet, install must provision all
                # declared engine-local dependencies before readiness can inspect them.
                missing = [item for item in requirements.get("dependencies", [])]
            else:
                missing = [item for item in requirements.get("missing_dependencies", [])]
        return {
            "ready": False,
            "reason": "missing_dependencies",
            "engine_registry_id": engine_registry_id,
            "provider": provider,
            "provider_label": requirements.get("provider_label") or provider,
            "supported": True,
            "requires_config": requirements.get("requires_config"),
            "missing_dependencies": missing,
            "activation_message": ready_result.get("message", ""),
        }

    if requirements.get("remote"):
        return {
            "ready": True,
            "reason": "",
            "engine_registry_id": engine_registry_id,
            "provider": provider,
            "provider_label": requirements.get("provider_label") or provider,
            "supported": True,
            "requires_config": requirements.get("requires_config"),
            "missing_dependencies": [],
            "activation_message": "",
        }

    return {
        "ready": ready_result.get("ready"),
        "reason": "" if ready_result.get("ready") else "missing_dependencies",
        "engine_registry_id": engine_registry_id,
        "provider": provider,
        "provider_label": requirements.get("provider_label") or provider,
        "supported": True,
        "requires_config": requirements.get("requires_config"),
        "missing_dependencies": missing,
        "activation_message": ready_result.get("message", ""),
    }
