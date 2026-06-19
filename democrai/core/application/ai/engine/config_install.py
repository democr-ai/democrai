from __future__ import annotations

import asyncio
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from democrai.core.runtime.foundation.app import app_ctx
from democrai.sdk.ai_constants import AIModelSource, AIRegistryStatus


ProgressCallback = Callable[[dict[str, Any]], None]


class EngineInstallConfigError(ValueError):
    pass


@dataclass
class EngineInstallReport:
    installed_engines: list[dict[str, Any]] = field(default_factory=list)
    activated_engines: list[dict[str, Any]] = field(default_factory=list)
    downloaded_models: list[dict[str, Any]] = field(default_factory=list)
    activated_models: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "partial_error" if self.has_errors() else "ok",
            "engines": {
                "installed": self.installed_engines,
                "activated": self.activated_engines,
                "skipped": [
                    item for item in self.skipped if item.get("kind") == "engine"
                ],
                "errors": [
                    item for item in self.errors if item.get("kind") == "engine"
                ],
            },
            "models": {
                "downloaded": self.downloaded_models,
                "activated": self.activated_models,
                "skipped": [
                    item for item in self.skipped if item.get("kind") == "model"
                ],
                "errors": [
                    item for item in self.errors if item.get("kind") == "model"
                ],
            },
        }


@dataclass
class InstallProgress:
    phase: str
    provider: str | None = None
    engine_name: str | None = None
    model_id: str | None = None
    status: str = ""
    message: str = ""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    download: bool = False
    activate: bool = True


@dataclass(frozen=True)
class EngineInstanceSpec:
    provider: str
    name: str
    config: dict[str, Any]
    models: list[ModelSpec]


_ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_INSTALL_DONE_STATUSES = {"installed", "active", "ready"}
_INSTALL_ERROR_STATUSES = {"error", "failed"}


async def install_engines_from_config(
    sdk,
    config: dict[str, Any],
    *,
    reset_mode: str,
    yes: bool,
    progress: ProgressCallback | None = None,
) -> EngineInstallReport:
    specs = _validate_config(config)
    report = EngineInstallReport()
    installed_providers: set[str] = set()
    _emit(progress, InstallProgress("reset", status=reset_mode))
    await _apply_reset(sdk, specs, reset_mode, yes, progress)

    for spec in specs:
        engine_row: dict[str, Any] | None = None
        try:
            _emit(progress, InstallProgress("engine", spec.provider, spec.name, status="resolving_provider"))
            requirements = await sdk.engines.provider_requirements(provider_id=spec.provider)
            _validate_requirements(spec, requirements)
            if not requirements.get("configurable"):
                _cleanup_non_configurable_engine_duplicates(sdk, spec.provider)
            engine_row = await _upsert_engine_registry_row(sdk, spec, requirements)
            _emit(progress, InstallProgress("engine", spec.provider, spec.name, status="registry_ready"))

            await _check_runtime_config(sdk, spec)
            installed = await _install_engine(
                sdk,
                engine_row,
                progress,
                skip_provider_install=spec.provider in installed_providers,
            )
            installed_providers.add(spec.provider)
            if installed is not None:
                report.installed_engines.append(installed)
            activated = await _activate_engine(sdk, engine_row, progress)
            report.activated_engines.append(activated)

            model_report = await _install_models_for_engine(
                sdk,
                engine_row,
                spec.provider,
                spec.models,
                progress,
            )
            report.downloaded_models.extend(model_report.downloaded_models)
            report.activated_models.extend(model_report.activated_models)
            report.skipped.extend(model_report.skipped)
            report.errors.extend(model_report.errors)
        except Exception as exc:
            error = {
                "kind": "engine",
                "provider": spec.provider,
                "engine_name": spec.name,
                "error": str(exc),
            }
            report.errors.append(error)
            if engine_row is not None:
                await _delete_failed_engine_registry_row(sdk, engine_row)
            _emit(
                progress,
                InstallProgress(
                    "engine",
                    spec.provider,
                    spec.name,
                    status="error",
                    message=str(exc),
                ),
            )

    await sdk.engines.sync_runtime()
    return report


def install_engines_config_audit_metadata(config: dict[str, Any]) -> dict[str, Any]:
    specs = _validate_config(config)
    providers: list[str] = []
    for spec in specs:
        if spec.provider not in providers:
            providers.append(spec.provider)
    return {
        "providers": providers,
        "engine_count": len(specs),
    }


def reset_full_engine_state_before_runtime_start(
    *,
    yes: bool,
    args,
    progress: ProgressCallback | None = None,
) -> None:
    _confirm_full_reset(yes)
    _emit(
        progress,
        InstallProgress("reset", status="full", message="preparing engine state reset"),
    )

    from democrai.core.infrastructure.observability.logger.manager import LoggerManager
    from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper
    from democrai.core.runtime.dependencies.engine_env import _engine_env_root, _rmtree_long_path
    from democrai.core.runtime.foundation.paths import configure_temp_environment, logs_dir

    ctx = app_ctx()
    ctx.logger = LoggerManager(log_dir=str(logs_dir()))
    bootstrapper = RuntimeBootstrapper()
    configure_temp_environment()
    bootstrapper.init_config(ctx)
    bootstrapper.configure_logging(ctx)
    bootstrapper.ensure_core_os_sandbox_relaunched(ctx, args)
    if bool(getattr(ctx, "setup_mode", False)):
        raise EngineInstallConfigError(
            "install-engines requires an existing application configuration"
        )
    bootstrapper.init_storage(ctx)

    _emit(
        progress,
        InstallProgress("reset", status="full", message="deleting engine database rows"),
    )
    _delete_full_engine_database_state()

    env_root = _engine_env_root()
    if env_root.exists():
        _emit(
            progress,
            InstallProgress("reset", status="full", message="deleting engine env root"),
        )
        _rmtree_long_path(env_root)


def _validate_config(config: dict[str, Any]) -> list[EngineInstanceSpec]:
    if not isinstance(config, dict):
        raise EngineInstallConfigError("config_must_be_mapping")
    engines = config.get("engines")
    if not isinstance(engines, list):
        raise EngineInstallConfigError("engines_must_be_non_empty_list")
    if not engines:
        raise EngineInstallConfigError("engines_must_be_non_empty_list")

    specs: list[EngineInstanceSpec] = []
    for index, raw_engine in enumerate(engines):
        if not isinstance(raw_engine, dict):
            raise EngineInstallConfigError(f"engines[{index}]_must_be_mapping")
        provider = _required_text(raw_engine.get("provider"), f"engines[{index}].provider")
        has_instances = "instances" in raw_engine
        if has_instances:
            if "config" in raw_engine:
                raise EngineInstallConfigError(
                    f"engines[{index}].config_cannot_be_used_with_instances"
                )
            if "models" in raw_engine:
                raise EngineInstallConfigError(
                    f"engines[{index}].models_cannot_be_used_with_instances"
                )
            instances = raw_engine.get("instances")
            if not isinstance(instances, list):
                raise EngineInstallConfigError(f"engines[{index}].instances_must_be_list")
            if not instances:
                raise EngineInstallConfigError(f"engines[{index}].instances_must_be_non_empty")
            for instance_index, raw_instance in enumerate(instances):
                if not isinstance(raw_instance, dict):
                    raise EngineInstallConfigError(
                        f"engines[{index}].instances[{instance_index}]_must_be_mapping"
                    )
                name = _required_text(
                    raw_instance.get("name"),
                    f"engines[{index}].instances[{instance_index}].name",
                )
                specs.append(
                    EngineInstanceSpec(
                        provider=provider,
                        name=name,
                        config=_config_dict(
                            raw_instance.get("config", {}),
                            f"engines[{index}].instances[{instance_index}].config",
                        ),
                        models=_model_specs(
                            raw_instance.get("models", []),
                            f"engines[{index}].instances[{instance_index}].models",
                        ),
                    )
                )
            continue

        name = _required_text(raw_engine.get("name") or provider, f"engines[{index}].name")
        specs.append(
            EngineInstanceSpec(
                provider=provider,
                name=name,
                config=_config_dict(raw_engine.get("config", {}), f"engines[{index}].config"),
                models=_model_specs(raw_engine.get("models", []), f"engines[{index}].models"),
            )
        )
    return specs


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EngineInstallConfigError(f"{field_name}_required")
    return text


def _config_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise EngineInstallConfigError(f"{field_name}_must_be_mapping")
    return _expand_env_values(value, field_name)


def _model_specs(value: Any, field_name: str) -> list[ModelSpec]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise EngineInstallConfigError(f"{field_name}_must_be_list")
    specs: list[ModelSpec] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise EngineInstallConfigError(f"{field_name}[{index}]_must_be_mapping")
        if "catalog_model_id" in item:
            raise EngineInstallConfigError(f"{field_name}[{index}].catalog_model_id_not_allowed")
        model_id = _required_text(item.get("id"), f"{field_name}[{index}].id")
        specs.append(
            ModelSpec(
                id=model_id,
                download=bool(item.get("download", False)),
                activate=bool(item.get("activate", True)),
            )
        )
    return specs


def _expand_env_values(value: Any, field_name: str) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _expand_env_values(item, f"{field_name}.{key}")
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _expand_env_values(item, f"{field_name}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, str):
        match = _ENV_PATTERN.match(value.strip())
        if match is None:
            return value
        env_name = match.group(1)
        if env_name not in os.environ:
            raise EngineInstallConfigError(f"{field_name}_env_missing:{env_name}")
        return os.environ[env_name]
    return value


async def _apply_reset(
    sdk,
    specs: list[EngineInstanceSpec],
    reset_mode: str,
    yes: bool,
    progress: ProgressCallback | None,
) -> None:
    if reset_mode == "keep":
        return
    if reset_mode == "full":
        _confirm_full_reset(yes)
        await _reset_full(sdk, progress)
        return
    if reset_mode == "selected":
        await _reset_selected(sdk, specs, progress)
        return
    raise EngineInstallConfigError(f"invalid_reset_mode:{reset_mode}")


def _confirm_full_reset(yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise EngineInstallConfigError("full_reset_requires_yes")
    answer = input("Type 'yes' to reset all engines and models: ").strip().lower()
    if answer != "yes":
        raise EngineInstallConfigError("full_reset_cancelled")


async def _reset_full(sdk, progress: ProgressCallback | None) -> None:
    engine_rows = _all_rows(sdk.models.engine_registry)
    _emit(progress, InstallProgress("reset", status="full", message="stopping engines"))
    for engine in engine_rows:
        engine_id = engine.get("id")
        if engine_id is not None:
            await _ignore_runtime_error(sdk.engines.stop_engine(engine_registry_id=engine_id))

    _emit(progress, InstallProgress("reset", status="full", message="deleting available models"))
    for row in _all_rows(sdk.models.available_model_registry):
        row_id = row.get("id")
        if row_id is not None:
            await sdk.engines.delete_available_model(available_model_id=row_id)

    _emit(progress, InstallProgress("reset", status="full", message="deleting model bindings"))
    for row in _all_rows(sdk.models.model_registry):
        row_id = row.get("id")
        if row_id is not None:
            sdk.models.model_registry.delete(row_id)

    _emit(progress, InstallProgress("reset", status="full", message="deleting engine registry"))
    for row in engine_rows:
        row_id = row.get("id")
        if row_id is not None:
            sdk.models.engine_registry.delete(row_id)


def _delete_full_engine_database_state() -> None:
    from democrai.core.infrastructure.database import SessionLocal
    from democrai.core.infrastructure.database.models import (
        AgentModelConfig,
        EngineNodeInstallRegistry,
        EngineNodeInstanceRegistry,
        EngineRegistry,
        KnowledgeRuntimeConfig,
        ModelCapabilityPriority,
        ModelRegistry,
        ObjectiveMapping,
    )
    from democrai.core.infrastructure.database.models_engine_quota import EngineQuotaLimit

    with SessionLocal() as session:
        session.query(AgentModelConfig).update(
            {AgentModelConfig.model_registry_id: None},
            synchronize_session=False,
        )
        session.query(KnowledgeRuntimeConfig).update(
            {
                KnowledgeRuntimeConfig.embedding_model_registry_id: None,
                KnowledgeRuntimeConfig.rerank_model_registry_id: None,
                KnowledgeRuntimeConfig.classification_model_registry_id: None,
                KnowledgeRuntimeConfig.triple_extractor_model_registry_id: None,
            },
            synchronize_session=False,
        )
        session.query(ObjectiveMapping).delete(synchronize_session=False)
        session.query(ModelCapabilityPriority).delete(synchronize_session=False)
        session.query(ModelRegistry).delete(synchronize_session=False)
        session.query(EngineQuotaLimit).delete(synchronize_session=False)
        session.query(EngineNodeInstanceRegistry).delete(synchronize_session=False)
        session.query(EngineNodeInstallRegistry).delete(synchronize_session=False)
        session.query(EngineRegistry).delete(synchronize_session=False)
        session.commit()


async def _reset_selected(
    sdk,
    specs: list[EngineInstanceSpec],
    progress: ProgressCallback | None,
) -> None:
    names = {spec.name for spec in specs}
    non_configurable_providers = set()
    for provider in {spec.provider for spec in specs}:
        requirements = await sdk.engines.provider_requirements(provider_id=provider)
        if not requirements.get("configurable"):
            non_configurable_providers.add(provider)
    selected = [
        row
        for row in _all_rows(sdk.models.engine_registry)
        if str(row.get("name") or "") in names
        or str(row.get("provider") or "") in non_configurable_providers
    ]
    selected_ids = {int(row["id"]) for row in selected if row.get("id") is not None}
    for engine in selected:
        engine_id = engine.get("id")
        if engine_id is None:
            continue
        _emit(
            progress,
            InstallProgress(
                "reset",
                provider=str(engine.get("provider") or ""),
                engine_name=str(engine.get("name") or ""),
                status="selected",
                message="stopping engine",
            ),
        )
        await _ignore_runtime_error(sdk.engines.stop_engine(engine_registry_id=engine_id))

    for binding in _all_rows(sdk.models.model_registry):
        engine_id = binding.get("engine_id")
        if engine_id is not None and int(engine_id) in selected_ids:
            sdk.models.model_registry.delete(binding["id"])

    requested_models = {model.id for spec in specs for model in spec.models}
    for row in _all_rows(sdk.models.available_model_registry):
        if _row_matches_model_ids(row, requested_models) and _is_downloaded_available(row):
            await sdk.engines.delete_available_model(available_model_id=row["id"])

    selected_providers = {
        str(engine.get("provider") or "").strip()
        for engine in selected
        if str(engine.get("provider") or "").strip()
    }
    for provider in selected_providers:
        _clear_engine_env_cache(provider, progress)

    for engine in selected:
        engine_id = engine.get("id")
        if engine_id is not None:
            sdk.models.engine_registry.update(engine_id, {"status": "uninstalled"})


async def _ignore_runtime_error(awaitable) -> None:
    try:
        await awaitable
    except Exception:
        return


async def _delete_failed_engine_registry_row(sdk, engine_row: dict[str, Any]) -> None:
    engine_id = engine_row.get("id")
    if engine_id is None:
        return
    await _ignore_runtime_error(sdk.engines.stop_engine(engine_registry_id=engine_id))
    for binding in _all_rows(sdk.models.model_registry):
        if binding.get("engine_id") is not None and int(binding["engine_id"]) == int(engine_id):
            sdk.models.model_registry.delete(binding["id"])
    sdk.models.engine_registry.delete(engine_id)


def _clear_engine_env_cache(provider: str, progress: ProgressCallback | None) -> None:
    resolved = str(provider or "").strip()
    if not resolved:
        return
    from democrai.core.runtime.dependencies.engine_env import (
        clear_local_engine_env,
        get_engine_local_env_path,
    )

    env_path = get_engine_local_env_path(resolved, create=False)
    if not env_path.exists():
        return
    _emit(
        progress,
        InstallProgress(
            "engine",
            provider=resolved,
            engine_name=resolved,
            status="env_cache_deleted",
            message=str(env_path),
        ),
    )
    clear_local_engine_env(resolved)


def _all_rows(model_proxy) -> list[dict[str, Any]]:
    payload = model_proxy.all()
    if isinstance(payload, dict):
        rows = payload.get("rows")
    else:
        rows = payload
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _validate_requirements(spec: EngineInstanceSpec, requirements: dict[str, Any]) -> None:
    if not requirements.get("provider"):
        raise EngineInstallConfigError(f"provider_not_found:{spec.provider}")
    if requirements.get("support_reason") == "provider_definition_not_found":
        raise EngineInstallConfigError(f"provider_not_found:{spec.provider}")
    if not requirements.get("supported"):
        reason = requirements.get("support_reason") or "unsupported"
        raise EngineInstallConfigError(f"provider_not_supported:{spec.provider}:{reason}")


async def _check_runtime_config(sdk, spec: EngineInstanceSpec) -> None:
    result = await sdk.engines.check_runtime_config(
        engine_id=spec.provider,
        config=spec.config,
    )
    if isinstance(result, dict) and result.get("valid") is False:
        error = result.get("error") or result.get("message") or "runtime_config_invalid"
        raise EngineInstallConfigError(f"runtime_config_invalid:{error}")


async def _upsert_engine_registry_row(
    sdk,
    spec: EngineInstanceSpec,
    requirements: dict[str, Any],
) -> dict[str, Any]:
    existing_rows = _all_rows(sdk.models.engine_registry)
    if requirements.get("configurable"):
        existing = _find_row_by_name(existing_rows, spec.name)
        name = spec.name
    else:
        existing = _find_row_by_provider(existing_rows, spec.provider)
        name = (
            str(existing.get("name") or "").strip()
            if existing is not None
            else str(requirements.get("provider_label") or spec.name).strip()
        )
    payload = {
        "name": name,
        "provider": spec.provider,
        "config": spec.config,
        "supported": bool(requirements.get("supported")),
    }
    if existing is not None:
        updated = sdk.models.engine_registry.update(existing["id"], payload)
        return _as_dict(updated) or {**existing, **payload}
    created = sdk.models.engine_registry.create(
        {
            **payload,
            "status": "uninstalled",
        }
    )
    return _as_dict(created) or payload


def _cleanup_non_configurable_engine_duplicates(sdk, provider: str) -> None:
    rows = [
        row
        for row in _all_rows(sdk.models.engine_registry)
        if str(row.get("provider") or "") == provider and row.get("id") is not None
    ]
    if len(rows) <= 1:
        return

    rows = sorted(rows, key=lambda item: int(item["id"]))
    canonical = rows[0]
    duplicate_ids = {int(row["id"]) for row in rows[1:]}
    canonical_id = int(canonical["id"])
    duplicate_active = any(
        str(row.get("status") or "").strip().lower() == AIRegistryStatus.ACTIVE
        for row in rows[1:]
    )

    for binding in _all_rows(sdk.models.model_registry):
        engine_id = binding.get("engine_id")
        if engine_id is not None and int(engine_id) in duplicate_ids:
            sdk.models.model_registry.update(binding["id"], {"engine_id": canonical_id})

    if duplicate_active and str(canonical.get("status") or "").strip().lower() != AIRegistryStatus.ACTIVE:
        sdk.models.engine_registry.update(canonical_id, {"status": AIRegistryStatus.ACTIVE})

    for row in rows[1:]:
        sdk.models.engine_registry.delete(row["id"])


async def _install_engine(
    sdk,
    engine_row: dict[str, Any],
    progress: ProgressCallback | None,
    *,
    skip_provider_install: bool = False,
) -> dict[str, Any] | None:
    engine_id = int(engine_row["id"])
    name = str(engine_row.get("name") or engine_id)
    provider = str(engine_row.get("provider") or "")
    if skip_provider_install:
        _emit(progress, InstallProgress("engine", provider, name, status="install_skipped", message="provider_already_installed"))
        return None
    if str(engine_row.get("status") or "").lower() in _INSTALL_DONE_STATUSES:
        _emit(progress, InstallProgress("engine", provider, name, status="install_skipped", message="already_installed"))
        return None

    _clear_engine_env_cache(provider, progress)
    _emit(progress, InstallProgress("engine", provider, name, status="install_started"))
    await sdk.engines.begin_install(
        engine_registry_id=engine_id,
        force=False,
        requested_by=None,
        task_id=None,
    )
    status_payload = await _poll_install_status(sdk, engine_id, provider, name, progress)
    installed = {
        "id": engine_id,
        "name": name,
        "provider": provider,
        "status": _status_from_payload(status_payload),
    }
    _emit(progress, InstallProgress("engine", provider, name, status="installed"))
    return installed


async def _poll_install_status(
    sdk,
    engine_id: int,
    provider: str,
    name: str,
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + 600.0
    last_status = ""
    while True:
        payload = await sdk.engines.install_status(engine_registry_id=engine_id)
        status = _status_from_payload(payload)
        if status and status != last_status:
            last_status = status
            _emit(progress, InstallProgress("engine", provider, name, status=status))
        if status in _INSTALL_DONE_STATUSES:
            return payload
        if status in _INSTALL_ERROR_STATUSES:
            raise RuntimeError(_install_failure_message(payload, status))
        summary = payload.get("summary") if isinstance(payload, dict) else {}
        if isinstance(summary, dict) and int(summary.get("errors") or 0) > 0:
            raise RuntimeError(_install_failure_message(payload, status or "error"))
        if asyncio.get_running_loop().time() >= deadline:
            raise RuntimeError("install_timeout")
        await asyncio.sleep(0.5)


def _status_from_payload(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    status = str(payload.get("status") or "").strip().lower()
    if status:
        return status
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    if summary.get("active"):
        return "active"
    if summary.get("installed"):
        return "installed"
    if summary.get("errors"):
        return "error"
    return ""


def _install_failure_message(payload: dict[str, Any], status: str) -> str:
    if not isinstance(payload, dict):
        return f"install_failed:{status}"
    for key in ("last_error", "error", "message"):
        value = str(payload.get(key) or "").strip()
        if value:
            return f"install_failed:{value}"
    nodes = payload.get("nodes")
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            value = str(node.get("last_error") or node.get("error") or "").strip()
            if value:
                return f"install_failed:{value}"
    return f"install_failed:{status}"


async def _activate_engine(
    sdk,
    engine_row: dict[str, Any],
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    engine_id = int(engine_row["id"])
    name = str(engine_row.get("name") or engine_id)
    provider = str(engine_row.get("provider") or "")
    result = await sdk.engines.activate_instance(engine_registry_id=engine_id)
    if isinstance(result, dict) and result.get("activation_ready") is False:
        reason = result.get("reason") or result.get("activation_message") or "activation_failed"
        raise RuntimeError(f"activation_failed:{reason}")
    row = _as_dict(sdk.models.engine_registry.view(engine_id)) or {}
    if str(row.get("status") or "").strip().lower() != AIRegistryStatus.ACTIVE:
        raise RuntimeError("activation_failed:not_active")
    _emit(progress, InstallProgress("engine", provider, name, status="active"))
    return {
        "id": engine_id,
        "name": row.get("name") or name,
        "provider": provider,
        "result": result,
    }


async def _install_models_for_engine(
    sdk,
    engine_row: dict[str, Any],
    provider: str,
    models: list[ModelSpec],
    progress: ProgressCallback | None,
) -> EngineInstallReport:
    report = EngineInstallReport()
    for model in models:
        try:
            if not model.activate and not model.download:
                report.skipped.append(
                    {
                        "kind": "model",
                        "engine_id": engine_row.get("id"),
                        "model_id": model.id,
                        "reason": "not_requested",
                    }
                )
                continue
            candidate = await _resolve_model_candidate(sdk, engine_row, provider, model)
            if candidate is None:
                raise RuntimeError(f"model_not_found:{model.id}")

            if model.download:
                downloaded = await _download_model_if_needed(sdk, candidate, provider, model, progress)
                if downloaded is None:
                    report.skipped.append(
                        {
                            "kind": "model",
                            "engine_id": engine_row.get("id"),
                            "model_id": model.id,
                            "reason": "already_available",
                        }
                    )
                else:
                    report.downloaded_models.append(downloaded)
                    candidate = {
                        **candidate,
                        **downloaded,
                    }

            if model.activate:
                activated = await _activate_model_binding(sdk, engine_row, candidate, model)
                report.activated_models.append(activated)
                _emit(
                    progress,
                    InstallProgress(
                        "model",
                        provider=provider,
                        engine_name=str(engine_row.get("name") or ""),
                        model_id=model.id,
                        status="active",
                    ),
                )
        except Exception as exc:
            error = {
                "kind": "model",
                "engine_id": engine_row.get("id"),
                "engine_name": engine_row.get("name"),
                "model_id": model.id,
                "error": str(exc),
            }
            report.errors.append(error)
            _emit(
                progress,
                InstallProgress(
                    "model",
                    provider=provider,
                    engine_name=str(engine_row.get("name") or ""),
                    model_id=model.id,
                    status="error",
                    message=str(exc),
                ),
            )
    return report


async def _resolve_model_candidate(
    sdk,
    engine_row: dict[str, Any],
    provider: str,
    model_spec: ModelSpec,
) -> dict[str, Any] | None:
    engine_id = str(engine_row["id"])
    available = await sdk.engines.list_available_models(engine_id=engine_id)
    candidate = _find_model_row(available, model_spec.id)
    if candidate is not None:
        return dict(candidate)
    catalog = await sdk.engines.list_catalog_models(engine_id=provider)
    candidate = _find_model_row(catalog, model_spec.id)
    if candidate is None:
        return None
    return dict(candidate)


async def _download_model_if_needed(
    sdk,
    candidate: dict[str, Any],
    provider: str,
    model_spec: ModelSpec,
    progress: ProgressCallback | None,
) -> dict[str, Any] | None:
    if candidate.get("available_model_id") or candidate.get("storage_ref"):
        return None
    provisioning = candidate.get("provisioning")
    if isinstance(provisioning, dict) and str(provisioning.get("mode") or "").strip() == "artifact":
        raise RuntimeError(f"model_requires_artifact_upload:{model_spec.id}")
    catalog_id = _catalog_id(candidate, provider=provider, requested_model_id=model_spec.id)
    if not catalog_id:
        raise RuntimeError(f"model_not_downloadable:{model_spec.id}")

    preflight = await sdk.engines.download_model(
        catalog_id=catalog_id,
        confirmed_resource_warning=True,
    )
    preflight_row = _download_result_row(preflight)
    if (
        isinstance(preflight, dict)
        and preflight_row
        and preflight_row.get("id")
        and preflight_row.get("storage_ref")
    ):
        return _downloaded_payload(preflight, model_spec.id)

    task_manager = app_ctx().task_manager
    task_id, _created = task_manager.submit_external_sync(
        user_id=0,
        label=f"Download model {model_spec.id}",
        module="core",
        task_key=f"core.install-engines.model-download.{catalog_id}",
    )
    _emit(
        progress,
        InstallProgress("model", model_id=model_spec.id, status="download_started"),
    )
    try:
        result = await sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=True,
            task_id=task_id,
        )
        task_manager.complete_external_sync(task_id, result=result)
    except Exception as exc:
        task_manager.fail_external_sync(task_id, str(exc))
        raise
    task = task_manager.get_task(task_id)
    if task is not None:
        _emit(
            progress,
            InstallProgress(
                "model",
                model_id=model_spec.id,
                status="download_progress",
                message=str(getattr(task, "progress", "")),
            ),
        )
    downloaded = _downloaded_payload(result, model_spec.id)
    _emit(progress, InstallProgress("model", model_id=model_spec.id, status="downloaded"))
    return downloaded


def _downloaded_payload(result: dict[str, Any], requested_model_id: str) -> dict[str, Any]:
    row = _download_result_row(result)
    return {
        "model_id": requested_model_id,
        "available_model_id": row.get("id") or row.get("available_model_id"),
        "name": row.get("name") or row.get("model_id") or requested_model_id,
        "label": row.get("label"),
        "storage_ref": row.get("storage_ref") or row.get("model_path"),
        "remote_url": row.get("remote_url"),
        "catalog_model_id": row.get("catalog_model_id"),
        "source_kind": row.get("source_kind"),
        "format": row.get("format"),
        "version": row.get("version"),
        "capabilities": row.get("capabilities") or [],
        "extra_config": (
            row.get("extra_config") if isinstance(row.get("extra_config"), dict) else {}
        ),
        "raw": result,
    }


def _download_result_row(result: dict[str, Any]) -> dict[str, Any]:
    row = result.get("available_model") if isinstance(result, dict) else {}
    if not isinstance(row, dict):
        row = result.get("row") if isinstance(result, dict) else {}
    if not isinstance(row, dict):
        row = result if isinstance(result, dict) else {}
    return row if isinstance(row, dict) else {}


async def _activate_model_binding(
    sdk,
    engine_row: dict[str, Any],
    candidate: dict[str, Any],
    model_spec: ModelSpec,
) -> dict[str, Any]:
    engine_id = int(engine_row["id"])
    bindings = await sdk.engines.list_models(engine_id=str(engine_id))
    existing = _find_existing_binding(bindings, engine_id, candidate, model_spec.id)
    payload = _model_binding_payload(engine_id, engine_row, candidate, model_spec)
    if existing is not None:
        row = sdk.models.model_registry.update(existing["id"], payload)
    else:
        row = sdk.models.model_registry.create(payload)
    binding = _as_dict(row) or payload
    return {
        "id": binding.get("id"),
        "engine_id": engine_id,
        "model_id": model_spec.id,
        "name": binding.get("name") or payload["name"],
    }


def _model_binding_payload(
    engine_id: int,
    engine_row: dict[str, Any],
    candidate: dict[str, Any],
    model_spec: ModelSpec,
) -> dict[str, Any]:
    available_model_id = candidate.get("available_model_id")
    storage_ref = candidate.get("storage_ref") or candidate.get("model_path")
    source_kind = candidate.get("source_kind")
    available_extra_config = (
        candidate.get("extra_config")
        if isinstance(candidate.get("extra_config"), dict)
        else {}
    )
    available_defaults = (
        available_extra_config.get("defaults")
        if isinstance(available_extra_config.get("defaults"), dict)
        else {}
    )
    runtime = candidate.get("runtime") if isinstance(candidate.get("runtime"), dict) else {}
    runtime_model_ref = (
        available_extra_config.get("runtime_model_ref")
        or runtime.get("model_ref")
        or candidate.get("model_id")
        or candidate.get("id")
        or candidate.get("name")
        or model_spec.id
    )
    label = candidate.get("label") or candidate.get("name") or model_spec.id
    remote_url = candidate.get("remote_url")
    generation_defaults = (
        available_defaults.get("generation")
        if isinstance(available_defaults.get("generation"), dict)
        else {}
    )
    runtime_defaults = (
        available_defaults.get("runtime")
        if isinstance(available_defaults.get("runtime"), dict)
        else {}
    )
    options_schema = (
        available_extra_config.get("options_schema")
        if isinstance(available_extra_config.get("options_schema"), dict)
        else candidate.get("options_schema") or {}
    )
    features = (
        available_extra_config.get("features")
        if isinstance(available_extra_config.get("features"), dict)
        else candidate.get("features") or {}
    )
    model_path = None
    if source_kind not in {AIModelSource.ENGINE_CATALOG, AIModelSource.PROVIDER_API}:
        model_path = storage_ref or runtime_model_ref
    if storage_ref:
        model_path = storage_ref
    extra_config = {
        "binding_label": label,
        "runtime_model_ref": runtime_model_ref,
        "defaults": {
            "generation": generation_defaults
            or candidate.get("generation_defaults")
            or candidate.get("defaults")
            or {},
            "runtime": runtime_defaults or runtime.get("defaults") or {},
        },
        "options_schema": options_schema,
        "features": features,
        "available_model": {
            "id": available_model_id,
            "name": candidate.get("name") or runtime_model_ref,
            "label": label,
            "format": candidate.get("format"),
            "source_kind": source_kind,
            "features": features,
        },
    }
    for key in ("runtime_entrypoint", "auxiliary_artifacts"):
        if key in available_extra_config:
            extra_config[key] = available_extra_config[key]
    return {
        "name": _binding_name(engine_row, model_spec.id),
        "engine_id": engine_id,
        "available_model_id": available_model_id,
        "model_path": model_path,
        "remote_url": remote_url,
        "version": candidate.get("version"),
        "capabilities": candidate.get("capabilities") or [],
        "status": AIRegistryStatus.ACTIVE,
        "is_downloaded": 1 if storage_ref else 0,
        "extra_config": extra_config,
    }


def _find_existing_binding(
    bindings: list[dict[str, Any]],
    engine_id: int,
    candidate: dict[str, Any],
    requested_model_id: str,
) -> dict[str, Any] | None:
    available_model_id = candidate.get("available_model_id")
    runtime_model_ref = (
        candidate.get("model_id")
        or candidate.get("id")
        or candidate.get("name")
        or requested_model_id
    )
    for binding in bindings:
        if int(binding.get("engine_id") or 0) != engine_id:
            continue
        if available_model_id and binding.get("available_model_id") == available_model_id:
            return binding
        if str(binding.get("model_id") or binding.get("name") or "") == str(runtime_model_ref):
            return binding
    return None


def _find_row_by_name(rows: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("name") or "") == name:
            return row
    return None


def _find_row_by_provider(rows: list[dict[str, Any]], provider: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get("provider") or "") == provider:
            return row
    return None


def _find_model_row(rows: list[dict[str, Any]], model_id: str) -> dict[str, Any] | None:
    for row in rows:
        if _row_matches_model_ids(row, {model_id}):
            return row
    return None


def _row_matches_model_ids(row: dict[str, Any], model_ids: set[str]) -> bool:
    values = {
        str(row.get("model_id") or ""),
        str(row.get("id") or ""),
        str(row.get("name") or ""),
    }
    values.discard("")
    return bool(values.intersection(model_ids))


def _is_downloaded_available(row: dict[str, Any]) -> bool:
    return bool(row.get("storage_ref") or row.get("is_downloaded"))


def _catalog_id(candidate: dict[str, Any], *, provider: str, requested_model_id: str) -> str:
    explicit = str(candidate.get("catalog_id") or "").strip()
    if explicit:
        return explicit
    model_id = str(
        candidate.get("model_id")
        or candidate.get("id")
        or candidate.get("name")
        or requested_model_id
        or ""
    ).strip()
    for entry in _static_catalog_entries():
        if not isinstance(entry, dict):
            continue
        source_engines = {
            str(item or "").strip()
            for item in (entry.get("source_engines") or [])
            if str(item or "").strip()
        }
        if source_engines and provider not in source_engines:
            continue
        if str(entry.get("legacy_model_id") or "").strip() == model_id:
            return str(entry.get("catalog_id") or "").strip()
    return ""


def _static_catalog_entries() -> list[dict[str, Any]]:
    from democrai.core.application.ai.models.catalog_download import (
        load_static_model_catalog,
    )

    return list(load_static_model_catalog())


def _binding_name(engine_row: dict[str, Any], model_id: str) -> str:
    return f"{_slug(str(engine_row.get('name') or engine_row.get('id') or 'engine'))}_{_slug(model_id)}"


def _slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9]+", "_", value.strip()).strip("_").lower()
    return text or "model"


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return dict(value)
    if value is None:
        return None
    if hasattr(value, "to_dict"):
        resolved = value.to_dict()
        return dict(resolved) if isinstance(resolved, dict) else None
    try:
        return asdict(value)
    except TypeError:
        return None


def _emit(progress: ProgressCallback | None, event: InstallProgress) -> None:
    if progress is not None:
        progress(asdict(event))
