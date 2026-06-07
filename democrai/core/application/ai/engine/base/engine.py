from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from abc import ABC
from typing import Any

from democrai.core.application.ai.engine.manifests import get_engine_manifest
from democrai.core.application.ai.engine.install_events import (
    emit_engine_install_output,
)
from democrai.core.application.ai.engine.install_events import get_runtime_node_id
from democrai.core.application.ai.engine.registry_config import (
    apply_engine_registry_config_updates,
)
from democrai.core.platform.utils.debug import debug_engine_install_flow
from democrai.core.runtime.dependencies.env_constants import system_command_path
from democrai.core.runtime.dependencies.engine_env import (
    bootstrap_engine_env,
    clear_local_engine_env,
    engine_env_context,
    has_engine_env_context,
    isolate_engine_imports,
)


class BaseEngine(ABC):
    """Common base class for installable engines."""

    engine_id: str | None = None

    def __init__(self, config: dict):
        self.config = config
        self.api_key = config.get("api_key")
        self.base_url = config.get("base_url")
        self.model_name = config.get("model")
        self.model_revision = config.get("model_revision")

    @classmethod
    def get_manifest(cls) -> dict[str, Any]:
        return get_engine_manifest(cls.engine_id or "") or {}

    @classmethod
    def get_manifest_version(cls) -> str:
        manifest = cls.get_manifest()
        return manifest.get("manifest_version") or "1"

    @classmethod
    def _sanitized_command_path(cls) -> str:
        if has_engine_env_context():
            return os.environ.get("PATH") or ""
        return system_command_path()

    @classmethod
    def _command_exists(cls, command_name: str) -> bool:
        if not command_name:
            return False
        sanitized_path = cls._sanitized_command_path()
        debug_engine_install_flow(
            "base_engine.command_exists.begin",
            engine_id=cls.engine_id or "",
            command=command_name,
            sanitized_path=sanitized_path,
        )
        try:
            result = False
            for base_dir in [item for item in sanitized_path.split(os.pathsep) if item]:
                candidate = Path(base_dir) / command_name
                try:
                    if (
                        candidate.exists()
                        and candidate.is_file()
                        and os.access(candidate, os.X_OK)
                    ):
                        result = True
                        break
                except PermissionError:
                    debug_engine_install_flow(
                        "base_engine.command_exists.skip_permission_error",
                        engine_id=cls.engine_id or "",
                        command=command_name,
                        candidate=str(candidate),
                    )
                    continue
            debug_engine_install_flow(
                "base_engine.command_exists.end",
                engine_id=cls.engine_id or "",
                command=command_name,
                exists=result,
            )
            return result
        except Exception as exc:
            debug_engine_install_flow(
                "base_engine.command_exists.error",
                engine_id=cls.engine_id or "",
                command=command_name,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise

    @classmethod
    def _resolve_system_command(cls, command_name: str) -> str:
        if not command_name:
            raise RuntimeError("system_command_name_required")
        for base_dir in [
            item for item in system_command_path().split(os.pathsep) if item
        ]:
            candidate = Path(base_dir) / command_name
            try:
                if (
                    candidate.exists()
                    and candidate.is_file()
                    and os.access(candidate, os.X_OK)
                ):
                    return str(candidate)
            except PermissionError:
                continue
        raise RuntimeError(f"system_command_not_found:{command_name}")

    @classmethod
    def is_supported(cls, env: dict[str, Any] | None = None) -> bool:
        return True

    @classmethod
    def unsupported_reason(cls, env: dict[str, Any] | None = None) -> str:
        return ""

    @classmethod
    def check_supported(cls, env: dict[str, Any] | None = None) -> dict[str, Any]:
        return cls._check_supported(env=env)

    @classmethod
    def support_status(cls, env: dict[str, Any] | None = None) -> dict[str, Any]:
        return cls.check_supported(env=env)

    @classmethod
    def check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        # Runtime readiness must be invoked through check_engine_ready_runtime(),
        # which runs this method inside the engine worker process. Calling this
        # directly from the main process can contaminate C-extension imports.
        return cls._check_ready_local(node_id=node_id)

    @classmethod
    def check_runtime_config(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return cls._validate_config_local(config=config)

    @classmethod
    def _check_ready_local(cls, *, node_id: str | None = None) -> dict[str, Any]:
        resolved_node_id = node_id or get_runtime_node_id()
        with engine_env_context(cls.engine_id or ""):
            debug_engine_install_flow(
                "base_engine.check_ready_local.bootstrap.begin",
                engine_id=cls.engine_id or "",
                node_id=resolved_node_id,
            )
            try:
                bootstrap_engine_env()
                isolate_engine_imports(cls.engine_id or "")
                debug_engine_install_flow(
                    "base_engine.check_ready_local.bootstrap.end",
                    engine_id=cls.engine_id or "",
                    node_id=resolved_node_id,
                    bootstrap_status="ok",
                )
            except RuntimeError as exc:
                debug_engine_install_flow(
                    "base_engine.check_ready_local.bootstrap.error",
                    engine_id=cls.engine_id or "",
                    node_id=resolved_node_id,
                    error=str(exc),
                )
                raise
            debug_engine_install_flow(
                "base_engine.check_ready_local.invoke_check.begin",
                engine_id=cls.engine_id or "",
                node_id=resolved_node_id,
            )
            result = cls._invoke_check_ready(node_id=resolved_node_id)
            debug_engine_install_flow(
                "base_engine.check_ready_local.invoke_check.end",
                engine_id=cls.engine_id or "",
                node_id=resolved_node_id,
                ready=result.get("ready"),
                message=result.get("message", ""),
                missing_shared=result.get("missing_shared", []),
                missing_local=result.get("missing_local", []),
            )
        payload = dict(result)
        payload.setdefault("engine_id", cls.engine_id or "")
        payload.setdefault("node_id", resolved_node_id)
        payload.setdefault("ready", False)
        payload.setdefault("missing_shared", [])
        payload.setdefault("missing_local", [])
        payload.setdefault("message", "")
        return payload

    @classmethod
    def _validate_config_local(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        result = cls._invoke_validate_config(config=config)
        payload = dict(result)
        if "ready" not in payload:
            raise RuntimeError("engine_validate_config_ready_required")
        payload.setdefault("engine_id", cls.engine_id or "")
        payload.setdefault("missing_config", [])
        payload.setdefault("message", "")
        return payload

    @classmethod
    def _check_supported(cls, env: dict[str, Any] | None = None) -> dict[str, Any]:
        return cls._build_supported_payload(
            supported=cls.is_supported(env),
            reason=cls.unsupported_reason(env),
        )

    @classmethod
    def install(
        cls,
        *,
        force: bool = False,
        node_id: str | None = None,
        event_id: str | None = None,
        source_node_id: str | None = None,
    ) -> dict[str, Any]:
        return cls._install_local(
            force=force,
            node_id=node_id,
            event_id=event_id,
            source_node_id=source_node_id,
        )

    @classmethod
    def _install_local(
        cls,
        *,
        force: bool = False,
        node_id: str | None = None,
        event_id: str | None = None,
        source_node_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_node_id = node_id or get_runtime_node_id()
        resolved_source_node_id = source_node_id or resolved_node_id

        engine_id = cls.engine_id or ""
        if force:
            clear_local_engine_env(engine_id)

        with engine_env_context(engine_id):
            emit_engine_install_output(
                "Installing engine dependencies", phase="install"
            )
            install_result = cls._invoke_install(
                force=force,
                node_id=resolved_node_id,
                source_node_id=resolved_source_node_id,
            )
            apply_engine_registry_config_updates(
                engine_id=cls.engine_id or "",
                updates=install_result.get("config_updates") or {},
            )

        emit_engine_install_output("Checking engine runtime", phase="check")
        ready_result = cls._check_ready_local(node_id=resolved_node_id)
        if not ready_result.get("ready"):
            raise RuntimeError(
                ready_result.get("message")
                or f"{cls.__name__} is not ready after install"
            )
        cls._mark_installed_in_registry()
        payload = install_result.copy()
        payload.setdefault("engine_id", cls.engine_id or "")
        payload.setdefault("node_id", resolved_node_id)
        payload.setdefault("status", "installed")
        payload.setdefault(
            "message", ready_result.get("message") or "Installation completed"
        )
        return payload

    @classmethod
    def _install(cls, force: bool = False) -> None:
        raise NotImplementedError(
            f"Engine {cls.__name__} does not implement install()."
        )

    @classmethod
    def _check_ready(cls, *, node_id: str | None = None) -> dict[str, Any]:
        return cls._build_ready_payload(
            missing_shared=cls._default_missing_shared(),
            missing_local=cls._default_missing_local(),
        )

    @classmethod
    def _validate_config(
        cls, *, config: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return {
            "ready": True,
            "missing_config": [],
            "message": "",
        }

    @classmethod
    def _invoke_install(
        cls,
        *,
        force: bool,
        node_id: str,
        source_node_id: str | None,
    ) -> dict[str, Any]:
        outcome = cls._install(
            force=force,
            node_id=node_id,
            source_node_id=source_node_id,
        )
        if isinstance(outcome, dict):
            return outcome
        return {}

    @classmethod
    def _invoke_check_ready(cls, *, node_id: str) -> dict[str, Any]:
        try:
            outcome = cls._check_ready(node_id=node_id)
        except Exception as exc:
            debug_engine_install_flow(
                "base_engine.invoke_check_ready.error",
                engine_id=cls.engine_id or "",
                node_id=node_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
            raise
        if isinstance(outcome, dict):
            return outcome
        raise RuntimeError("engine_check_ready_result_invalid")

    @classmethod
    def _invoke_validate_config(cls, *, config: dict[str, Any] | None) -> dict[str, Any]:
        outcome = cls._validate_config(config=config)
        if isinstance(outcome, dict):
            return outcome
        raise RuntimeError("engine_validate_config_result_invalid")

    @classmethod
    def _default_missing_shared(cls) -> list[str]:
        debug_engine_install_flow(
            "base_engine.default_missing_shared.begin",
            engine_id=cls.engine_id or "",
        )
        debug_engine_install_flow(
            "base_engine.default_missing_shared.end",
            engine_id=cls.engine_id or "",
            missing_shared=[],
        )
        return []

    @classmethod
    def _default_missing_local(cls) -> list[str]:
        manifest = cls.get_manifest()
        provider = manifest.get("provider") or {}
        dependencies = provider.get("dependencies") if isinstance(provider, dict) else []
        missing_local: list[str] = []
        for dep in dependencies or []:
            if not isinstance(dep, dict):
                continue
            module_name = dep.get("module", "")
            label = dep.get("label") or dep.get("dependency_key") or module_name
            check_type = dep.get("check_type", "")
            commands = dep.get("commands", "")
            if check_type == "command_any":
                command_names = [
                    item
                    for item in commands.split(",")
                    if item
                ]
                if command_names and not any(
                    cls._command_exists(command) for command in command_names
                ):
                    missing_local.append(label or " or ".join(command_names))
                continue
            if module_name and importlib.util.find_spec(module_name) is None:
                missing_local.append(label or module_name)
        return missing_local

    @classmethod
    def _missing_modules(cls, *module_pairs: tuple[str, str] | str) -> list[str]:
        missing_local: list[str] = []
        for item in module_pairs:
            if isinstance(item, tuple):
                module_name, label = item
            else:
                module_name, label = item, item
            if module_name and importlib.util.find_spec(module_name) is None:
                missing_local.append(label or module_name)
        return missing_local

    @classmethod
    def _missing_commands(cls, *command_pairs: tuple[str, str] | str) -> list[str]:
        debug_engine_install_flow(
            "base_engine.missing_commands.begin",
            engine_id=cls.engine_id or "",
            commands=[
                item[0] if isinstance(item, tuple) else item for item in command_pairs
            ],
        )
        missing_local: list[str] = []
        for item in command_pairs:
            if isinstance(item, tuple):
                command_name, label = item
            else:
                command_name, label = item, item
            debug_engine_install_flow(
                "base_engine.missing_commands.check.begin",
                engine_id=cls.engine_id or "",
                command=command_name,
                label=label,
            )
            exists = command_name and cls._command_exists(command_name)
            debug_engine_install_flow(
                "base_engine.missing_commands.check.end",
                engine_id=cls.engine_id or "",
                command=command_name,
                label=label,
                exists=exists,
            )
            if command_name and not exists:
                missing_local.append(label or command_name)
        debug_engine_install_flow(
            "base_engine.missing_commands.end",
            engine_id=cls.engine_id or "",
            missing_local=missing_local,
        )
        return missing_local

    @classmethod
    def _build_ready_payload(
        cls,
        *,
        missing_shared: list[str] | None = None,
        missing_local: list[str] | None = None,
        ok_message: str | None = None,
        error_message: str | None = None,
    ) -> dict[str, Any]:
        resolved_missing_shared = missing_shared or []
        resolved_missing_local = missing_local or []
        ready = not resolved_missing_shared and not resolved_missing_local
        return {
            "ready": ready,
            "missing_shared": resolved_missing_shared,
            "missing_local": resolved_missing_local,
            "message": (
                ok_message or "Engine ready"
                if ready
                else error_message or "Missing shared or local dependencies"
            ),
        }

    @classmethod
    def _build_supported_payload(
        cls,
        *,
        supported: bool,
        reason: str | None = None,
    ) -> dict[str, Any]:
        return {
            "engine_id": cls.engine_id or "",
            "supported": supported,
            "reason": "" if supported else reason or "",
        }

    @classmethod
    def _mark_installed_in_registry(cls) -> None:
        from democrai.core.infrastructure.database import SessionLocal
        from democrai.core.infrastructure.database.models import EngineRegistry
        from democrai.core.runtime.dependencies.installer_env import runtime_env

        engine_id = cls.engine_id
        if not engine_id:
            raise ValueError(
                f"Engine {cls.__name__} must define 'engine_id' to be installable."
            )
        is_supported = cls.is_supported(runtime_env())

        with SessionLocal() as session:
            rows = (
                session.query(EngineRegistry)
                .filter(EngineRegistry.provider == engine_id)
                .all()
            )
            if not rows:
                row = EngineRegistry(
                    name=engine_id,
                    provider=engine_id,
                    config={},
                    status="installed",
                    supported=is_supported,
                )
                session.add(row)
            else:
                for row in rows:
                    previous_status = row.status
                    row.status = (
                        "installed"
                        if previous_status == "installing"
                        else previous_status
                    )
                    row.supported = is_supported
            session.commit()
