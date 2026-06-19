from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
import re
from typing import Any, Callable

from democrai.core.application.knowledge.extractor.manifests import get_extractor_manifest
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.dependencies.extractor_env import (
    _extractor_env_root,
    get_extractor_local_env_path,
)


ProgressCallback = Callable[[dict[str, Any]], None]


class ExtractorInstallConfigError(ValueError):
    pass


@dataclass
class ExtractorInstallReport:
    installed: list[dict[str, Any]] = field(default_factory=list)
    activated: list[dict[str, Any]] = field(default_factory=list)
    mime_bindings: list[dict[str, Any]] = field(default_factory=list)
    skipped: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    def has_errors(self) -> bool:
        return bool(self.errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "partial_error" if self.has_errors() else "ok",
            "extractors": {
                "installed": self.installed,
                "activated": self.activated,
                "skipped": self.skipped,
                "errors": self.errors,
            },
            "mime_bindings": self.mime_bindings,
        }


@dataclass
class InstallProgress:
    phase: str
    extractor_id: str | None = None
    status: str = ""
    message: str = ""


@dataclass(frozen=True)
class ExtractorSpec:
    id: str
    name: str
    install_config: dict[str, Any]
    runtime_config: dict[str, Any]
    mime_bindings: list[str]


_ENV_PATTERN = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_DONE_STATUSES = {"installed", "active"}
_ERROR_STATUSES = {"error", "failed"}


async def install_extractors_from_config(
    sdk,
    config: dict[str, Any],
    *,
    reset_mode: str,
    yes: bool,
    progress: ProgressCallback | None = None,
) -> ExtractorInstallReport:
    specs = _validate_config(config)
    report = ExtractorInstallReport()
    _emit(progress, InstallProgress("reset", status=reset_mode))
    await _apply_reset(sdk, specs, reset_mode, yes, progress)

    for spec in specs:
        try:
            extractors_api = getattr(sdk, "extractors")
            manifest = _manifest_for(spec.id)
            _emit(progress, InstallProgress("extractor", spec.id, status="registry_ready"))
            row = _upsert_extractor_registry_row(sdk, spec, manifest)
            installed = await _install_extractor(sdk, row, spec, progress)
            if installed is not None:
                report.installed.append(installed)
            activated = _activate_extractor(sdk, row)
            report.activated.append(activated)
            for mime_type in spec.mime_bindings:
                result = extractors_api.set_mime_type_binding(
                    mime_type=mime_type,
                    extractor_id=spec.id,
                )
                report.mime_bindings.append(
                    result or {"mime_type": mime_type, "extractor_id": spec.id}
                )
                _emit(
                    progress,
                    InstallProgress(
                        "mime",
                        spec.id,
                        status="bound",
                        message=mime_type,
                    ),
                )
        except Exception as exc:
            report.errors.append(
                {
                    "kind": "extractor",
                    "extractor_id": spec.id,
                    "error": str(exc),
                }
            )
            _emit(
                progress,
                InstallProgress(
                    "extractor",
                    spec.id,
                    status="error",
                    message=str(exc),
                ),
            )

    extractors_api = getattr(sdk, "extractors")
    await extractors_api.sync_runtime()
    return report


def reset_full_extractor_state_before_runtime_start(
    *,
    yes: bool,
    args,
    progress: ProgressCallback | None = None,
) -> None:
    _confirm_full_reset(yes)
    _emit(
        progress,
        InstallProgress("reset", status="full", message="preparing extractor state reset"),
    )

    from democrai.core.infrastructure.observability.logger.manager import LoggerManager
    from democrai.core.runtime.bootstrap.bootstrap_pipeline import RuntimeBootstrapper
    from democrai.core.runtime.foundation.paths import configure_temp_environment, logs_dir

    ctx = app_ctx()
    ctx.logger = LoggerManager(log_dir=str(logs_dir()))
    bootstrapper = RuntimeBootstrapper()
    configure_temp_environment()
    bootstrapper.init_config(ctx)
    bootstrapper.configure_logging(ctx)
    bootstrapper.ensure_core_os_sandbox_relaunched(ctx, args)
    if bool(getattr(ctx, "setup_mode", False)):
        raise ExtractorInstallConfigError(
            "install-extractors requires an existing application configuration"
        )
    bootstrapper.init_storage(ctx)

    _emit(
        progress,
        InstallProgress("reset", status="full", message="deleting extractor database rows"),
    )
    _delete_full_extractor_database_state()

    env_root = _extractor_env_root()
    if env_root.exists():
        _emit(
            progress,
            InstallProgress("reset", status="full", message="deleting extractor env root"),
        )
        _remove_path(env_root)


def install_extractors_config_audit_metadata(config: dict[str, Any]) -> dict[str, Any]:
    specs = _validate_config(config)
    return {
        "extractors": [spec.id for spec in specs],
        "extractor_count": len(specs),
    }


def _validate_config(config: dict[str, Any]) -> list[ExtractorSpec]:
    if not isinstance(config, dict):
        raise ExtractorInstallConfigError("config_must_be_mapping")
    extractors = config.get("extractors")
    if not isinstance(extractors, list) or not extractors:
        raise ExtractorInstallConfigError("extractors_must_be_non_empty_list")

    specs: list[ExtractorSpec] = []
    seen: set[str] = set()
    for index, raw in enumerate(extractors):
        if not isinstance(raw, dict):
            raise ExtractorInstallConfigError(f"extractors[{index}]_must_be_mapping")
        extractor_id = _required_text(raw.get("id"), f"extractors[{index}].id").lower()
        if extractor_id in seen:
            raise ExtractorInstallConfigError(f"extractors[{index}].duplicate_id:{extractor_id}")
        seen.add(extractor_id)
        manifest = get_extractor_manifest(extractor_id)
        if not isinstance(manifest, dict):
            manifest = {"id": extractor_id, "name": extractor_id, "mime_types": []}
        name = str(raw.get("name") or manifest.get("name") or extractor_id).strip()
        install_config = _config_dict(raw.get("install_config", {}), f"extractors[{index}].install_config")
        runtime_config = _config_dict(raw.get("runtime_config", {}), f"extractors[{index}].runtime_config")
        mime_bindings = _mime_bindings(raw.get("mime_bindings", []), f"extractors[{index}].mime_bindings")
        _validate_mime_bindings(manifest, mime_bindings, f"extractors[{index}].mime_bindings")
        specs.append(
            ExtractorSpec(
                id=extractor_id,
                name=name or extractor_id,
                install_config=install_config,
                runtime_config=runtime_config,
                mime_bindings=mime_bindings,
            )
        )
    return specs


def _manifest_for(extractor_id: str) -> dict[str, Any]:
    manifest = get_extractor_manifest(extractor_id)
    if not isinstance(manifest, dict):
        raise ExtractorInstallConfigError(f"extractor_manifest_not_found:{extractor_id}")
    return manifest


def _required_text(value: Any, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ExtractorInstallConfigError(f"{field_name}_required")
    return text


def _config_dict(value: Any, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ExtractorInstallConfigError(f"{field_name}_must_be_mapping")
    return _expand_env_values(value, field_name)


def _mime_bindings(value: Any, field_name: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ExtractorInstallConfigError(f"{field_name}_must_be_list")
    result: list[str] = []
    for index, item in enumerate(value):
        text = str(item or "").strip().lower()
        if not text:
            raise ExtractorInstallConfigError(f"{field_name}[{index}]_required")
        if text not in result:
            result.append(text)
    return result


def _validate_mime_bindings(
    manifest: dict[str, Any],
    mime_bindings: list[str],
    field_name: str,
) -> None:
    supported = {
        str(item or "").strip().lower()
        for item in list(manifest.get("mime_types") or [])
        if str(item or "").strip()
    }
    for mime_type in mime_bindings:
        if mime_type not in supported:
            extractor_id = str(manifest.get("id") or "")
            raise ExtractorInstallConfigError(
                f"{field_name}.unsupported:{extractor_id}:{mime_type}"
            )


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
            raise ExtractorInstallConfigError(f"{field_name}_env_missing:{env_name}")
        return os.environ[env_name]
    return value


async def _apply_reset(
    sdk,
    specs: list[ExtractorSpec],
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
    raise ExtractorInstallConfigError(f"invalid_reset_mode:{reset_mode}")


def _confirm_full_reset(yes: bool) -> None:
    if yes:
        return
    if not sys.stdin.isatty():
        raise ExtractorInstallConfigError("full_reset_requires_yes")
    answer = input("Type 'yes' to reset all extractors: ").strip().lower()
    if answer != "yes":
        raise ExtractorInstallConfigError("full_reset_cancelled")


async def _reset_full(sdk, progress: ProgressCallback | None) -> None:
    _emit(progress, InstallProgress("reset", status="full", message="deleting mime bindings"))
    for row in _all_rows(sdk.models.extractor_mime_type_binding):
        row_id = row.get("id")
        if row_id is not None:
            sdk.models.extractor_mime_type_binding.delete(row_id)
    _emit(progress, InstallProgress("reset", status="full", message="deleting extractor registry"))
    for row in _all_rows(sdk.models.extractor_registry):
        row_id = row.get("id")
        if row_id is not None:
            sdk.models.extractor_registry.delete(row_id)
    extractors_api = getattr(sdk, "extractors")
    await extractors_api.sync_runtime()
    _remove_path(_extractor_env_root())


async def _reset_selected(
    sdk,
    specs: list[ExtractorSpec],
    progress: ProgressCallback | None,
) -> None:
    selected = {spec.id for spec in specs}
    _emit(progress, InstallProgress("reset", status="selected", message="deleting mime bindings"))
    for row in _all_rows(sdk.models.extractor_mime_type_binding):
        if str(row.get("extractor_id") or "").strip().lower() in selected:
            sdk.models.extractor_mime_type_binding.delete(row["id"])
    for row in _all_rows(sdk.models.extractor_registry):
        extractor_id = str(row.get("extractor_id") or "").strip().lower()
        if extractor_id in selected and row.get("id") is not None:
            sdk.models.extractor_registry.delete(row["id"])
    extractors_api = getattr(sdk, "extractors")
    await extractors_api.sync_runtime()
    for extractor_id in selected:
        _remove_path(get_extractor_local_env_path(extractor_id))


def _remove_path(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def _all_rows(model_proxy) -> list[dict[str, Any]]:
    payload = model_proxy.all()
    if isinstance(payload, dict):
        rows = payload.get("rows")
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
        return []
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    return []


def _delete_full_extractor_database_state() -> None:
    from democrai.core.infrastructure.database import SessionLocal
    from democrai.core.infrastructure.database.models import (
        ExtractorMimeTypeBinding,
        ExtractorNodeInstallRegistry,
        ExtractorRegistry,
    )

    with SessionLocal() as session:
        session.query(ExtractorMimeTypeBinding).delete(synchronize_session=False)
        session.query(ExtractorNodeInstallRegistry).delete(synchronize_session=False)
        session.query(ExtractorRegistry).delete(synchronize_session=False)
        session.commit()


def _upsert_extractor_registry_row(
    sdk,
    spec: ExtractorSpec,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    existing = _find_registry_row(sdk, spec.id)
    payload = {
        "name": spec.name,
        "extractor_id": spec.id,
        "config": spec.runtime_config,
        "install_config": spec.install_config,
        "file_extensions": list(manifest.get("file_extensions") or []),
        "mime_types": list(manifest.get("mime_types") or []),
        "priority": int(manifest.get("priority") or 0),
        "supported": True,
    }
    if existing is not None:
        row = sdk.models.extractor_registry.update(existing["id"], payload)
        return row if isinstance(row, dict) else {**existing, **payload}
    row = sdk.models.extractor_registry.create({**payload, "status": "uninstalled"})
    return row if isinstance(row, dict) else {**payload, "status": "uninstalled"}


def _find_registry_row(sdk, extractor_id: str) -> dict[str, Any] | None:
    for row in _all_rows(sdk.models.extractor_registry):
        if str(row.get("extractor_id") or "").strip().lower() == extractor_id:
            return row
    return None


async def _install_extractor(
    sdk,
    row: dict[str, Any],
    spec: ExtractorSpec,
    progress: ProgressCallback | None,
) -> dict[str, Any] | None:
    row_id = int(row["id"])
    status = str(row.get("status") or "").strip().lower()
    if status in _DONE_STATUSES:
        _emit(progress, InstallProgress("extractor", spec.id, status="install_skipped", message="already_installed"))
        return None
    _emit(progress, InstallProgress("extractor", spec.id, status="install_started"))
    extractors_api = getattr(sdk, "extractors")
    event = await extractors_api.request_install(
        extractor_id=spec.id,
        force=False,
        install_config=spec.install_config,
        requested_by=None,
        task_id=None,
    )
    event_id = str((event or {}).get("event_id") or "").strip()
    await _poll_install_status(sdk, spec.id, event_id, progress)
    sdk.models.extractor_registry.update(row_id, {"status": "installed", "supported": True})
    _emit(progress, InstallProgress("extractor", spec.id, status="installed"))
    return {"id": row_id, "extractor_id": spec.id, "status": "installed"}


async def _poll_install_status(
    sdk,
    extractor_id: str,
    event_id: str,
    progress: ProgressCallback | None,
) -> None:
    deadline = asyncio.get_running_loop().time() + 1800.0
    last_status = ""
    while True:
        filters = {"extractor_id": extractor_id}
        if event_id:
            filters["last_event_id"] = event_id
        rows = sdk.models.extractor_node_install_registry.list(
            page=0,
            page_size=20,
            filters=filters,
            sort={"field": "updated_at", "direction": "desc"},
        ).get("rows") or []
        row = rows[0] if rows else {}
        status = str(row.get("status") or "").strip().lower()
        if status and status != last_status:
            _emit(progress, InstallProgress("extractor", extractor_id, status=status))
            last_status = status
        if status == "installed":
            return
        if status in _ERROR_STATUSES:
            raise RuntimeError(row.get("last_error") or f"extractor_install_failed:{extractor_id}")
        if asyncio.get_running_loop().time() >= deadline:
            raise TimeoutError(f"extractor_install_timeout:{extractor_id}")
        await asyncio.sleep(0.5)


def _activate_extractor(sdk, row: dict[str, Any]) -> dict[str, Any]:
    row_id = int(row["id"])
    extractor_id = str(row.get("extractor_id") or "").strip().lower()
    sdk.models.extractor_registry.update(
        row_id,
        {"status": "active", "supported": True},
    )
    updated = sdk.models.extractor_registry.view(row_id)
    if not isinstance(updated, dict):
        raise RuntimeError(f"extractor_activation_not_found:{extractor_id}")
    status = str(updated.get("status") or "").strip().lower()
    if status != "active":
        raise RuntimeError(f"extractor_activation_failed:{extractor_id}:{status or 'unknown'}")
    return {
        "id": row_id,
        "extractor_id": extractor_id,
        "status": "active",
        "row": updated,
    }


def _emit(progress: ProgressCallback | None, event: InstallProgress) -> None:
    if progress is not None:
        progress(asdict(event))
