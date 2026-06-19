from __future__ import annotations

import asyncio
import hashlib
import json
import os
import shutil
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from democrai.core.application.ai.constants import (
    AIModelSource,
    AIModelSourceKind,
    normalize_capabilities,
    normalize_token,
    runtime_config_schema_for_capabilities,
)
from democrai.core.application.access_policy import (
    AccessManifestRule,
    AccessResource,
    AccessSubject,
)
from democrai.core.application.ai.engine.manifests import list_provider_definitions
from democrai.core.application.ai.models.catalog import list_engine_models
from democrai.core.infrastructure.network.policy_guard import network_policy_context
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    AgentModelConfig,
    AvailableModelRegistry,
    EngineRegistry,
    ModelRegistry,
    ModelCapabilityPriority,
    ObjectiveMapping,
)
from democrai.core.runtime.foundation.app import app_ctx, req_ctx
from democrai.core.runtime.foundation.paths import get_data_dir


MODEL_MANIFEST_NAME = ".democrai-model-manifest.json"
ProgressCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class ModelStorageOps:
    add_model: Callable[..., str]
    add_model_from_source: Callable[..., str]
    view: Callable[[str], bytes]
    delete: Callable[[str], None]


async def download_model(
    catalog_id: str,
    *,
    storage: ModelStorageOps,
    confirmed_resource_warning: bool = False,
    task_id: str | None = None,
) -> dict[str, Any]:
    entry = catalog_entry_by_id(catalog_id)
    if not isinstance(entry, dict):
        raise ValueError("catalog_entry_not_found")
    row = _available_row_by_catalog_id(catalog_id)
    status = row.status if row is not None else ""
    if status == "available":
        raise ValueError("catalog_already_added")

    warning = _catalog_resource_warning(entry)
    if warning.get("warnings") and not confirmed_resource_warning:
        return {
            "status": "requires_confirmation",
            "catalog_id": catalog_id,
            "entry": entry,
            "available_model": _serialize_available_row(row) if row is not None else None,
            "resource_warning": warning,
        }
    if not task_id:
        return {
            "status": "ready",
            "catalog_id": catalog_id,
            "entry": entry,
            "available_model": _serialize_available_row(row) if row is not None else None,
            "resource_warning": warning,
        }

    row_id = _create_or_reset_catalog_available_row(entry, catalog_id)
    try:
        storage_ref = await _download_catalog_to_storage(
            storage,
            name=entry.get("legacy_model_id") or entry.get("catalog_id") or "model",
            entry=entry,
            task_id=task_id,
        )
        updated = _update_available_row(
            row_id,
            {
                "storage_ref": storage_ref,
                "status": "available",
                "extra_config": _catalog_inventory_extra_config(entry, storage_ref),
            },
        )
        await _update_task_progress(task_id, 1.0, entry.get("label") or "Model ready")
        return {
            "status": "available",
            "row": updated,
            "storage_ref": storage_ref,
            "resource_warning": warning,
        }
    except Exception as exc:
        _update_available_row(
            row_id,
            {
                "status": "failed",
                "extra_config": {"error": str(exc)},
            },
        )
        raise


def import_model_from_source(
    *,
    source: dict[str, Any],
    model: dict[str, Any],
    storage: ModelStorageOps,
) -> dict[str, Any]:
    resolved_source = source if isinstance(source, dict) else {}
    if str(resolved_source.get("kind") or "").strip().lower() != "uploaded_media":
        raise ValueError("unsupported_model_import_source")
    source_path = str(resolved_source.get("storage_path") or "").strip()
    if not source_path:
        raise ValueError("model_import_storage_path_required")

    payload = _manual_inventory_payload(model, resolved_source, status="importing")
    row_id = _create_manual_available_row(payload)
    try:
        storage_ref = storage.add_model(
            payload["name"],
            source_path=source_path,
            filename=str(resolved_source.get("filename") or "").strip() or None,
        )
        updated = _update_available_row(
            row_id,
            {
                "storage_ref": storage_ref,
                "status": "available",
                "extra_config": _manual_inventory_extra_config(
                    payload["name"],
                    storage_ref,
                ),
            },
        )
        return {"status": "available", "row": updated, "storage_ref": storage_ref}
    except Exception as exc:
        _update_available_row(
            row_id,
            {
                "status": "failed",
                "extra_config": {"error": str(exc)},
            },
        )
        raise


async def download_model_from_source(
    *,
    source: dict[str, Any],
    model: dict[str, Any],
    storage: ModelStorageOps,
    task_id: str | None = None,
) -> dict[str, Any]:
    resolved_source = source if isinstance(source, dict) else {}
    artifact = _manual_source_artifact(resolved_source)
    payload = _manual_inventory_payload(
        model,
        resolved_source,
        status="downloading",
        source_kind=normalize_token(resolved_source.get("kind")),
    )
    row_id = _create_manual_available_row(payload)
    try:
        storage_ref = await _store_catalog_artifact(
            storage,
            task_id=task_id,
            model_id=payload["name"],
            artifact=artifact,
            progress_start=0.10,
            progress_end=0.90,
        )
        updated = _update_available_row(
            row_id,
            {
                "storage_ref": storage_ref,
                "status": "available",
                "extra_config": _manual_inventory_extra_config(
                    payload["name"],
                    storage_ref,
                ),
            },
        )
        await _update_task_progress(task_id, 1.0, payload["label"])
        return {"status": "available", "row": updated, "storage_ref": storage_ref}
    except Exception as exc:
        _update_available_row(
            row_id,
            {
                "status": "failed",
                "extra_config": {"error": str(exc)},
            },
        )
        raise


def delete_available_model(
    available_model_id: int,
    *,
    storage: ModelStorageOps,
) -> dict[str, Any]:
    row_id = available_model_id
    with SessionLocal() as session:
        row = session.query(AvailableModelRegistry).filter(AvailableModelRegistry.id == row_id).first()
        if row is None:
            raise ValueError("available_model_not_found")
        storage_ref = row.storage_ref
        binding_ids = [
            item.id
            for item in session.query(ModelRegistry.id)
            .filter(ModelRegistry.available_model_id == row_id)
            .all()
        ]

    if storage_ref:
        delete_available_model_storage(storage, storage_ref)

    with SessionLocal() as session:
        row = session.query(AvailableModelRegistry).filter(AvailableModelRegistry.id == row_id).first()
        if row is None:
            return {
                "status": "deleted",
                "available_model_id": row_id,
                "deleted_bindings": len(binding_ids),
            }
        if binding_ids:
            (
                session.query(AgentModelConfig)
                .filter(AgentModelConfig.model_registry_id.in_(binding_ids))
                .update(
                    {AgentModelConfig.model_registry_id: None},
                    synchronize_session=False,
                )
            )
            (
                session.query(ObjectiveMapping)
                .filter(ObjectiveMapping.model_id.in_(binding_ids))
                .delete(synchronize_session=False)
            )
            (
                session.query(ModelCapabilityPriority)
                .filter(ModelCapabilityPriority.model_id.in_(binding_ids))
                .delete(synchronize_session=False)
            )
            (
                session.query(ModelRegistry)
                .filter(ModelRegistry.id.in_(binding_ids))
                .delete(synchronize_session=False)
            )
        session.delete(row)
        session.commit()
    return {
        "status": "deleted",
        "available_model_id": row_id,
        "deleted_bindings": len(binding_ids),
    }


def delete_available_model_storage(storage: ModelStorageOps, storage_ref: str) -> None:
    if not storage_ref:
        return
    manifest_path = f"{storage_ref.rstrip('/')}/{MODEL_MANIFEST_NAME}"
    try:
        manifest = json.loads(storage.view(manifest_path).decode("utf-8"))
    except Exception:
        storage.delete(storage_ref)
        return

    files = manifest.get("files") if isinstance(manifest, dict) else []
    if not isinstance(files, list):
        storage.delete(storage_ref)
        return
    for item in files:
        relative_path = str(item or "").strip().lstrip("/")
        if relative_path:
            storage.delete(f"{storage_ref.rstrip('/')}/{relative_path}")
    storage.delete(manifest_path)


def catalog_entry_by_id(catalog_id: str) -> dict[str, Any] | None:
    if not catalog_id:
        return None
    for entry in load_static_model_catalog():
        if entry.get("catalog_id") == catalog_id:
            return entry
    return None


def load_static_model_catalog() -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    installed_engine_ids = _installed_engine_ids()
    for definition in list_provider_definitions() or []:
        if not isinstance(definition, dict):
            continue
        if normalize_token(definition.get("model_source")) == AIModelSource.PROVIDER_API:
            continue
        engine_id = normalize_token(definition.get("id"))
        if not engine_id or engine_id not in installed_engine_ids:
            continue
        try:
            models = list_engine_models(engine_id)
        except Exception:
            models = []
        for model in models:
            if not isinstance(model, dict):
                continue
            if _source_type(model) == "local_upload":
                continue
            model_format = _primary_format(model)
            if not model_format:
                continue
            entry = _normalize_catalog_entry(model, source_engine=engine_id)
            key = entry["catalog_id"]
            if key not in entries:
                entries[key] = entry
                entries[key]["source_engines"] = [engine_id]
                continue
            current = entries[key]
            current["compatible_engines"] = _merge_unique_strings(
                current.get("compatible_engines") or [],
                entry.get("compatible_engines") or [],
            )
            current["source_engines"] = _merge_unique_strings(
                current.get("source_engines") or [],
                [engine_id],
            )
    return sorted(entries.values(), key=lambda item: item.get("label", "").lower())


def _available_row_by_catalog_id(catalog_id: str) -> AvailableModelRegistry | None:
    with SessionLocal() as session:
        return (
            session.query(AvailableModelRegistry)
            .filter(AvailableModelRegistry.catalog_model_id == catalog_id)
            .first()
        )


def _create_or_reset_catalog_available_row(entry: dict[str, Any], catalog_id: str) -> int:
    payload = _catalog_inventory_payload(entry, catalog_id, status="downloading")
    with SessionLocal() as session:
        row = (
            session.query(AvailableModelRegistry)
            .filter(AvailableModelRegistry.catalog_model_id == catalog_id)
            .first()
        )
        if row is not None:
            if row.status == "available":
                raise ValueError("catalog_already_added")
            _assign_available_payload(row, payload)
            row.storage_ref = None
            row.extra_config = {}
        else:
            row = AvailableModelRegistry()
            _assign_available_payload(row, payload)
            session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _create_manual_available_row(payload: dict[str, Any]) -> int:
    with SessionLocal() as session:
        name = payload.get("name") or ""
        if not name:
            raise ValueError("model_name_required")
        existing = (
            session.query(AvailableModelRegistry)
            .filter(AvailableModelRegistry.name == name)
            .first()
        )
        if existing is not None:
            raise ValueError("available_model_name_already_in_use")
        row = AvailableModelRegistry()
        _assign_available_payload(row, payload)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row.id


def _update_available_row(row_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    with SessionLocal() as session:
        row = session.query(AvailableModelRegistry).filter(AvailableModelRegistry.id == row_id).first()
        if row is None:
            raise ValueError("available_model_not_found")
        if "storage_ref" in payload:
            row.storage_ref = payload.get("storage_ref") or None
        if "status" in payload:
            row.status = payload.get("status") or None
        if "extra_config" in payload:
            value = payload.get("extra_config")
            row.extra_config = value if isinstance(value, dict) else None
        session.commit()
        session.refresh(row)
        return _serialize_available_row(row)


def _manual_inventory_payload(
    model: dict[str, Any],
    source: dict[str, Any],
    *,
    status: str,
    source_kind: str = AIModelSourceKind.UPLOAD,
) -> dict[str, Any]:
    name = model.get("name")
    label = model.get("label") or name
    model_format = model.get("format")
    if not name or not label or not model_format:
        raise ValueError("invalid_model_import_payload")
    return {
        "name": name,
        "label": label,
        "catalog_model_id": "",
        "source_kind": source_kind,
        "provider_hint": model.get("provider_hint") or "",
        "format": model_format,
        "family": model.get("family") or "",
        "summary": model.get("summary") or "",
        "capabilities": model.get("capabilities") or [],
        "extended_capabilities": model.get("extended_capabilities") or [],
        "interfaces": model.get("interfaces") or [],
        "requirements": model.get("requirements") or {},
        "artifacts": model.get("artifacts") or [],
        "metadata": model.get("metadata") or {},
        "source_payload": source,
        "status": status,
    }


def _manual_source_artifact(source: dict[str, Any]) -> dict[str, Any]:
    source_kind = normalize_token(source.get("kind"))
    if source_kind == AIModelSourceKind.URL:
        url = str(source.get("url") or "").strip()
        if not url:
            raise ValueError("url_source_required")
        return {
            "source": {
                "type": AIModelSourceKind.URL,
                "url": url,
            },
            "filename": str(source.get("filename") or "").strip(),
        }
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        repo = str(source.get("repo") or "").strip()
        if not repo:
            raise ValueError("huggingface_repo_required")
        files = [
            str(item or "").strip()
            for item in list(source.get("files") or [])
            if str(item or "").strip()
        ]
        return {
            "source": {
                "type": AIModelSourceKind.HUGGINGFACE,
                "repo": repo,
                "revision": str(source.get("revision") or "main").strip() or "main",
                "files": files,
                "snapshot": bool(source.get("snapshot")) or len(files) != 1,
            },
            "filename": str(source.get("filename") or "").strip(),
        }
    raise ValueError("unsupported_model_download_source")


def _assign_available_payload(row: AvailableModelRegistry, payload: dict[str, Any]) -> None:
    row.name = payload.get("name")
    row.label = payload.get("label") or row.name
    row.catalog_model_id = payload.get("catalog_model_id") or None
    row.source_kind = payload.get("source_kind") or AIModelSourceKind.CATALOG
    row.provider_hint = payload.get("provider_hint") or None
    row.format = payload.get("format") or None
    row.family = payload.get("family") or None
    row.summary = payload.get("summary") or None
    row.version = payload.get("version") or None
    row.capabilities = _normalize_csv(payload.get("capabilities")) or None
    row.extended_capabilities = _normalize_csv(payload.get("extended_capabilities")) or None
    row.interfaces = _normalize_csv(payload.get("interfaces")) or None
    row.tags = _normalize_csv(payload.get("tags")) or None
    row.requirements = payload.get("requirements") if isinstance(payload.get("requirements"), dict) else None
    row.artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else None
    row.metadata_json = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None
    row.source_payload = payload.get("source_payload") if isinstance(payload.get("source_payload"), dict) else None
    row.status = payload.get("status") or "available"


def _catalog_inventory_payload(entry: dict[str, Any], catalog_id: str, *, status: str) -> dict[str, Any]:
    return {
        "name": entry.get("legacy_model_id") or entry.get("catalog_id") or "model",
        "label": entry.get("label") or entry.get("legacy_model_id") or "model",
        "catalog_model_id": catalog_id,
        "source_kind": AIModelSourceKind.CATALOG,
        "provider_hint": (entry.get("source_engines") or [entry.get("source_engine")])[0] or "",
        "format": entry.get("format") or "",
        "family": entry.get("family") or "",
        "summary": entry.get("summary") or "",
        "capabilities": entry.get("capabilities") or [],
        "extended_capabilities": entry.get("extended_capabilities") or [],
        "interfaces": entry.get("interfaces") or [],
        "requirements": entry.get("requirements") or {},
        "artifacts": entry.get("artifacts") or [],
        "metadata": entry.get("metadata") or {},
        "source_payload": {
            "catalog_id": catalog_id,
            "features": entry.get("features") or {},
            "source_engines": entry.get("source_engines") or [],
            "compatible_engines": entry.get("compatible_engines") or [],
        },
        "status": status,
    }


async def _download_catalog_to_storage(
    storage: ModelStorageOps,
    *,
    name: str,
    entry: dict[str, Any],
    task_id: str | None,
) -> str:
    if _catalog_download_disabled(entry):
        await _update_task_progress(task_id, 0.90, name)
        return ""

    artifacts = _required_catalog_artifacts(entry)
    if not artifacts:
        raise ValueError("catalog_artifact_not_found")

    await _update_task_progress(task_id, 0.05, name)
    if len(artifacts) == 1:
        return await _store_catalog_artifact(
            storage,
            task_id=task_id,
            model_id=name,
            artifact=artifacts[0],
            progress_start=0.10,
            progress_end=0.90,
        )

    storage_ref = ""
    manifest_files: list[str] = []
    for index, artifact in enumerate(artifacts):
        start, end = _artifact_progress_range(index, len(artifacts))
        storage_ref = await _store_catalog_artifact(
            storage,
            task_id=task_id,
            model_id=name,
            artifact=artifact,
            progress_start=start,
            progress_end=end,
            preserve_target=True,
        )
        manifest_files.extend(_catalog_artifact_manifest_files(artifact))
    if manifest_files:
        storage.add_model(
            name,
            payload=json.dumps(
                {"kind": "directory", "files": sorted(set(manifest_files))}
            ).encode("utf-8"),
            filename=MODEL_MANIFEST_NAME,
        )
    return storage_ref


async def _store_catalog_artifact(
    storage: ModelStorageOps,
    *,
    task_id: str | None,
    model_id: str,
    artifact: dict[str, Any],
    progress_start: float,
    progress_end: float,
    preserve_target: bool = False,
) -> str:
    await _update_task_progress(task_id, progress_start, "Downloading model artifact")
    loop = asyncio.get_running_loop()
    progress_span = max(0.0, progress_end - progress_start)

    def _progress_callback(event: dict[str, Any]) -> None:
        total_files = int(event.get("total_files") or 1)
        file_index = int(event.get("file_index") or 1)
        total_bytes = int(event.get("total_bytes") or 0)
        downloaded_bytes = int(event.get("downloaded_bytes") or 0)
        file_fraction = min(1.0, downloaded_bytes / total_bytes) if total_bytes > 0 else 0.0
        completed_files = max(0, file_index - 1)
        overall_fraction = min(1.0, (completed_files + file_fraction) / max(1, total_files))
        progress = progress_start + (progress_span * overall_fraction)
        label = str(event.get("label") or "Downloading model artifact")
        if total_files > 1:
            label = f"Downloading {label} ({file_index}/{total_files})"
        else:
            label = f"Downloading {label}"
        if task_id:
            asyncio.run_coroutine_threadsafe(
                _emit_task_progress(task_id, progress, label),
                loop,
            )

    source = _catalog_artifact_source(artifact, preserve_target=preserve_target)
    subject = _current_module_network_subject()
    access = _catalog_artifact_network_access(artifact, subject=subject)
    with network_policy_context(
        subject_name=subject.subject_name,
        subject_type=subject.subject_type,
        access=access,
    ), _catalog_artifact_os_network_proxy_scope(access):
        storage_ref = await asyncio.to_thread(
            storage.add_model_from_source,
            model_id,
            source=source,
            filename=_catalog_artifact_filename(artifact),
            progress_callback=_progress_callback,
        )
    await _update_task_progress(task_id, progress_end, "Stored model artifact")
    return storage_ref


@contextmanager
def _catalog_artifact_os_network_proxy_scope(
    access: tuple[AccessManifestRule, ...],
):
    from democrai.core.infrastructure.sandbox.os.core_relaunch import (
        update_core_os_sandbox_proxy_session,
    )
    from democrai.core.infrastructure.sandbox.os.models import (
        ApplicationNetworkAllowlist,
    )
    from democrai.core.infrastructure.sandbox.os.normalize import (
        dedupe_endpoints,
        endpoint_from_target,
    )
    from democrai.core.infrastructure.sandbox.os.state import (
        get_current_application_network_allowlist,
        is_application_network_allowlist_active,
    )
    from democrai.core.infrastructure.sandbox.process_guard import (
        process_guard_bypass_context,
    )

    if not is_application_network_allowlist_active():
        yield
        return

    current_allowlist = get_current_application_network_allowlist()
    if current_allowlist is None:
        yield
        return

    extra_endpoints = []
    for rule in access:
        resource = rule.resource
        resource_type = getattr(resource.resource_type, "value", resource.resource_type)
        operation = getattr(resource.operation, "value", resource.operation)
        if resource_type != "network" or operation != "connect":
            continue
        endpoint = endpoint_from_target(
            resource.normalized_target,
            source=f"{rule.subject.subject_type}:{rule.subject.subject_name}",
            purpose="catalog_artifact_download",
        )
        if endpoint is not None:
            extra_endpoints.append(endpoint)

    if not extra_endpoints:
        yield
        return

    merged_allowlist = ApplicationNetworkAllowlist(
        endpoints=dedupe_endpoints(
            [*list(current_allowlist.endpoints or []), *extra_endpoints]
        )
    )
    with process_guard_bypass_context():
        applied = update_core_os_sandbox_proxy_session(
            merged_allowlist,
            config=getattr(app_ctx(), "config", None),
        )
    if not applied:
        yield
        return

    try:
        yield
    finally:
        with process_guard_bypass_context():
            update_core_os_sandbox_proxy_session(
                current_allowlist,
                config=getattr(app_ctx(), "config", None),
            )


async def _update_task_progress(task_id: str | None, progress: float, label: str) -> None:
    if not task_id:
        return
    task_manager = app_ctx().task_manager
    if task_manager is not None:
        await task_manager.update_progress(task_id, progress, label=label)


async def _emit_task_progress(task_id: str, progress: float, label: str) -> None:
    task_manager = app_ctx().task_manager
    if task_manager is not None:
        await task_manager.emit_progress(task_id, progress, label=label)


def _catalog_resource_warning(entry: dict[str, Any]) -> dict[str, Any]:
    requirements = entry.get("requirements") if isinstance(entry.get("requirements"), dict) else {}
    resources = _resource_snapshot()
    storage_free_mb = _storage_free_mb()
    warnings: list[dict[str, Any]] = []

    ram_required_mb = _gb_to_mb(requirements.get("ram_gb"))
    vram_required_mb = _gb_to_mb(requirements.get("vram_gb"))
    storage_required_mb = _gb_to_mb(requirements.get("storage_gb"))
    ram_total_mb = resources.get("ram_total_mb") or 0
    vram_total_mb = resources.get("vram_total_mb") or 0

    if ram_required_mb and ram_total_mb and ram_required_mb > ram_total_mb:
        warnings.append({"resource": "ram", "required_mb": ram_required_mb, "available_mb": ram_total_mb})
    if vram_required_mb and vram_total_mb <= 0:
        warnings.append({"resource": "vram", "required_mb": vram_required_mb, "available_mb": 0})
    elif vram_required_mb and vram_total_mb and vram_required_mb > vram_total_mb:
        warnings.append({"resource": "vram", "required_mb": vram_required_mb, "available_mb": vram_total_mb})
    if storage_required_mb and storage_free_mb and storage_required_mb > storage_free_mb:
        warnings.append({"resource": "storage", "required_mb": storage_required_mb, "available_mb": storage_free_mb})

    return {
        "warnings": warnings,
        "requirements": {
            "ram_required_mb": ram_required_mb,
            "vram_required_mb": vram_required_mb,
            "storage_required_mb": storage_required_mb,
        },
        "resources": {
            **resources,
            "storage_free_mb": storage_free_mb,
        },
    }


def _resource_snapshot() -> dict[str, Any]:
    try:
        from democrai.core.application.ai.engine.runtime import resource_snapshot

        return resource_snapshot()
    except Exception:
        return {
            "ram_total_mb": 0,
            "ram_free_mb": 0,
            "ram_used_mb": 0,
            "vram_total_mb": 0,
            "vram_free_mb": 0,
            "vram_used_mb": 0,
            "has_nvidia_gpu": False,
        }


def _storage_free_mb() -> int:
    try:
        usage = shutil.disk_usage(get_data_dir())
    except Exception:
        return 0
    return int(usage.free / (1024 * 1024))


def _gb_to_mb(value: Any) -> int:
    try:
        return int(float(value or 0) * 1024)
    except Exception:
        return 0


def _generation_defaults(source: dict[str, Any] | None = None) -> dict[str, Any]:
    defaults = source if isinstance(source, dict) else {}
    return {
        "temperature": defaults.get("temperature", 0.7),
        "top_p": defaults.get("top_p", 0.9),
        "top_k": defaults.get("top_k"),
        "max_tokens": defaults.get("max_tokens"),
    }


def _catalog_inventory_extra_config(entry: dict[str, Any], storage_ref: str) -> dict[str, Any]:
    runtime = entry.get("runtime") if isinstance(entry.get("runtime"), dict) else {}
    runtime_defaults = runtime.get("defaults") if isinstance(runtime.get("defaults"), dict) else {}
    runtime_options_schema = runtime.get("options_schema") if isinstance(runtime.get("options_schema"), dict) else {}
    standard_schema = runtime_config_schema_for_capabilities(
        entry.get("capabilities") or []
    )
    standard_defaults = (
        standard_schema.get("defaults")
        if isinstance(standard_schema.get("defaults"), dict)
        else {}
    )
    standard_generation = (
        standard_defaults.get("generation")
        if isinstance(standard_defaults.get("generation"), dict)
        else {}
    )
    standard_runtime = (
        standard_defaults.get("runtime")
        if isinstance(standard_defaults.get("runtime"), dict)
        else {}
    )
    runtime_default_values = (
        runtime_defaults.get("runtime")
        if isinstance(runtime_defaults.get("runtime"), dict)
        else (
            runtime_defaults
            if not isinstance(runtime_defaults.get("generation"), dict)
            else {}
        )
    )
    generation_default_values = (
        _generation_defaults(runtime_defaults.get("generation"))
        if isinstance(runtime_defaults.get("generation"), dict)
        else {}
    )
    auxiliary_artifacts = (
        runtime.get("auxiliary_artifacts")
        if isinstance(runtime.get("auxiliary_artifacts"), dict)
        else {}
    )
    features = entry.get("features") if isinstance(entry.get("features"), dict) else {}
    requirements = entry.get("requirements") if isinstance(entry.get("requirements"), dict) else {}
    runtime_entrypoint = _runtime_entrypoint_from_catalog(entry, storage_ref)
    return {
        "storage_prefix": storage_ref if runtime_entrypoint else _storage_prefix_from_ref(storage_ref),
        "runtime_entrypoint": runtime_entrypoint,
        "runtime_model_ref": entry.get("legacy_model_id") or entry.get("catalog_id") or "",
        "auxiliary_artifacts": auxiliary_artifacts,
        "defaults": {
            "generation": {
                **standard_generation,
                **generation_default_values,
            },
            "runtime": {
                **standard_runtime,
                **runtime_default_values,
            },
        },
        "options_schema": runtime_options_schema,
        "features": features,
        "requirements": requirements,
    }


def _manual_inventory_extra_config(name: str, storage_ref: str) -> dict[str, Any]:
    return {
        "storage_prefix": _storage_prefix_from_ref(storage_ref),
        "runtime_model_ref": name,
        "defaults": {
            "generation": {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": None,
            },
            "runtime": {},
        },
    }


def _catalog_download_disabled(entry: dict[str, Any]) -> bool:
    provisioning = entry.get("provisioning") if isinstance(entry.get("provisioning"), dict) else {}
    download = provisioning.get("download") if isinstance(provisioning.get("download"), dict) else {}
    return normalize_token(download.get("strategy")) == "none"


def _required_catalog_artifacts(entry: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        artifact
        for artifact in entry.get("artifacts") or []
        if isinstance(artifact, dict) and bool(artifact.get("required", True))
    ]


def _artifact_progress_range(index: int, total: int) -> tuple[float, float]:
    return (
        0.10 + (0.75 * index / total),
        0.10 + (0.75 * (index + 1) / total),
    )


def _catalog_artifact_source(
    artifact: dict[str, Any],
    *,
    preserve_target: bool = False,
) -> dict[str, Any]:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    source_type = str(source.get("type") or "").strip().lower()
    if source_type == AIModelSourceKind.HUGGINGFACE:
        repo = str(source.get("repo") or "").strip()
        revision = str(source.get("revision") or "main").strip() or "main"
        files = [
            str(item or "").strip()
            for item in list(source.get("files") or [])
            if str(item or "").strip()
        ]
        if not repo:
            raise ValueError("huggingface_file_source_required")
        payload = {
            "type": AIModelSourceKind.HUGGINGFACE,
            "repo": repo,
            "revision": revision,
            "files": files,
            "snapshot": bool(source.get("snapshot")) or len(files) != 1,
        }
        if preserve_target:
            payload["target"] = _catalog_artifact_storage_target(artifact)
        return payload
    if source_type in {"http", "https", AIModelSourceKind.URL}:
        url = str(source.get("url") or "").strip()
        if not url:
            raise ValueError("url_source_required")
        payload = {"type": AIModelSourceKind.URL, "url": url}
        if preserve_target:
            payload["target"] = _catalog_artifact_storage_target(artifact)
        return payload
    raise ValueError(f"unsupported_catalog_source:{source_type or 'unknown'}")


def _current_module_network_subject() -> AccessSubject:
    try:
        current = req_ctx()
    except LookupError as exc:
        raise RuntimeError("catalog_download_request_context_required") from exc
    module_name = str(current.module_name or "").strip()
    if not module_name:
        raise RuntimeError("catalog_download_module_context_required")
    if module_name == "core":
        return AccessSubject.create("core", "core")
    return AccessSubject.create("module", module_name)


def _catalog_artifact_network_access(
    artifact: dict[str, Any],
    *,
    subject: AccessSubject,
) -> tuple[AccessManifestRule, ...]:
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    source_type = str(source.get("type") or "").strip().lower()
    targets: list[str] = []
    if source_type in {"http", "https", AIModelSourceKind.URL}:
        url = str(source.get("url") or "").strip()
        if url:
            targets.append(url)
            parsed = urlparse(url)
            if (
                parsed.netloc.lower() == "github.com"
                and "/releases/download/" in parsed.path
            ):
                targets.append("https://release-assets.githubusercontent.com")
    elif source_type == AIModelSourceKind.HUGGINGFACE:
        repo = str(source.get("repo") or "").strip()
        if repo:
            targets.append(f"https://huggingface.co/{repo}")
            targets.append("https://*.hf.co")
            targets.append("https://cas-bridge.xethub.hf.co")
            targets.append("https://transfer.xethub.hf.co")
            targets.append("https://*.cdn.hf.co")
    return tuple(
        AccessManifestRule(
            subject=subject,
            resource=AccessResource.create(
                resource_type="network",
                operation=operation,
                target=target,
            ),
        )
        for target in targets
        for operation in ("connect", "receive")
    )


def _catalog_artifact_storage_target(artifact: dict[str, Any]) -> str:
    target = str(artifact.get("target") or "").strip().replace("\\", "/").strip("/")
    if target.startswith("models/"):
        target = target[len("models/") :]
    if target:
        return target
    filename = _catalog_artifact_filename(artifact)
    if not filename:
        raise ValueError("catalog_artifact_target_missing")
    return filename


def _catalog_artifact_manifest_files(artifact: dict[str, Any]) -> list[str]:
    target = _catalog_artifact_storage_target(artifact)
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    files = [
        str(item or "").strip().lstrip("/")
        for item in list(source.get("files") or [])
        if str(item or "").strip()
    ]
    if not files or len(files) == 1:
        return [target]
    return [
        f"{target.rstrip('/')}/{remote_path}"
        for remote_path in files
        if remote_path
    ]


def _catalog_artifact_filename(artifact: dict[str, Any]) -> str | None:
    filename = str(artifact.get("filename") or artifact.get("name") or "").strip()
    if filename:
        return filename
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    files = [
        str(item or "").strip()
        for item in list(source.get("files") or [])
        if str(item or "").strip()
    ]
    if len(files) == 1:
        return os.path.basename(files[0]) or None
    url = str(source.get("url") or "").strip()
    if url:
        return os.path.basename(url.split("?", 1)[0]) or None
    return None


def _runtime_entrypoint_from_catalog(entry: dict[str, Any], storage_ref: str) -> str:
    runtime = entry.get("runtime") if isinstance(entry.get("runtime"), dict) else {}
    entrypoint = str(runtime.get("entrypoint") or "").strip().lstrip("/")
    if entrypoint:
        return entrypoint
    if Path(storage_ref).suffix:
        return ""
    return ""


def _storage_prefix_from_ref(storage_ref: str) -> str:
    if not storage_ref:
        return ""
    path = Path(storage_ref)
    if path.suffix:
        return path.parent.as_posix()
    return path.as_posix()


def _first_artifact(model: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = model.get("artifacts")
    if not isinstance(artifacts, list):
        return None
    for artifact in artifacts:
        if isinstance(artifact, dict) and bool(artifact.get("required", True)):
            return artifact
    for artifact in artifacts:
        if isinstance(artifact, dict):
            return artifact
    return None


def _primary_format(model: dict[str, Any]) -> str:
    artifact = _first_artifact(model)
    if artifact is None:
        return normalize_token(model.get("format"))
    return normalize_token(artifact.get("format") or model.get("format"))


def _source_type(model: dict[str, Any]) -> str:
    artifact = _first_artifact(model)
    if artifact is None:
        provisioning = model.get("provisioning") if isinstance(model.get("provisioning"), dict) else {}
        download = provisioning.get("download") if isinstance(provisioning.get("download"), dict) else {}
        if normalize_token(download.get("strategy")) == "none":
            return "none"
        return ""
    source = artifact.get("source") if isinstance((artifact or {}).get("source"), dict) else {}
    return normalize_token(source.get("type"))


def _catalog_signature(model: dict[str, Any], *, source_engine: str) -> str:
    artifact = _first_artifact(model) or {}
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    model_format = _primary_format(model)
    source_kind = normalize_token(source.get("type"))
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        repo = str(source.get("repo") or "").strip()
        revision = str(source.get("revision") or "main").strip() or "main"
        files = ",".join(str(item or "").strip() for item in (source.get("files") or []))
        snapshot = "1" if bool(source.get("snapshot")) else "0"
        raw = f"hf::{repo}::{revision}::{files}::{snapshot}::{model_format}"
    elif source_kind in {"http", "https", AIModelSourceKind.URL}:
        raw = f"url::{str(source.get('url') or '').strip()}::{model_format}"
    else:
        raw = f"legacy::{source_engine}::{model.get('id') or ''}::{model_format}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _normalize_catalog_entry(model: dict[str, Any], *, source_engine: str) -> dict[str, Any]:
    model_format = _primary_format(model)
    return {
        "catalog_id": _catalog_signature(model, source_engine=source_engine),
        "legacy_model_id": model.get("id") or "",
        "label": model.get("label") or model.get("id") or "",
        "family": model.get("family") or "",
        "summary": model.get("summary") or "",
        "format": model_format,
        "capabilities": normalize_capabilities(model.get("capabilities") or []),
        "extended_capabilities": normalize_capabilities(model.get("extended_capabilities") or []),
        "interfaces": [
            item
            for item in (model.get("interfaces") or [])
            if item
        ],
        "requirements": model.get("requirements") or {},
        "provisioning": model.get("provisioning") or {},
        "artifacts": model.get("artifacts") or [],
        "runtime": model.get("runtime") or {},
        "features": model.get("features") or {},
        "metadata": model.get("metadata") or {},
        "source_engine": source_engine,
        "source_type": _source_type(model),
        "compatible_engines": _compatible_engine_ids(
            model_format,
            normalize_capabilities(model.get("capabilities") or []),
            source_engine=source_engine,
            explicit_engines=model.get("compatible_engines") or [],
        ),
        "downloadable": _source_type(model) in {"http", "https", AIModelSourceKind.HUGGINGFACE, AIModelSourceKind.URL},
    }


def _compatible_engine_ids(
    model_format: str,
    capabilities: list[str],
    *,
    source_engine: str,
    explicit_engines: list[str] | None = None,
) -> list[str]:
    explicit = [
        normalize_token(item)
        for item in (explicit_engines or [])
        if item
    ]
    if explicit:
        return _merge_unique_strings(explicit, [source_engine])
    return [source_engine] if source_engine else []


def _installed_engine_ids() -> set[str]:
    installed_statuses = {"active", "installed"}
    engine_ids: set[str] = set()
    with SessionLocal() as session:
        rows = session.query(EngineRegistry).all()
        for row in rows:
            status = row.status
            if status not in installed_statuses:
                continue
            provider = row.provider
            if provider:
                engine_ids.add(provider)
    return engine_ids


def _merge_unique_strings(left: list[str], right: list[str]) -> list[str]:
    resolved = list(left)
    for item in right:
        if item and item not in resolved:
            resolved.append(item)
    return resolved


def _normalize_csv(raw_value: Any) -> str:
    if raw_value is None:
        return ""
    if isinstance(raw_value, str):
        parts = [part.strip() for part in raw_value.split(",")]
    elif isinstance(raw_value, list):
        parts = [str(part).strip() for part in raw_value]
    else:
        parts = [str(raw_value).strip()]
    return ",".join([part for part in parts if part])


def _serialize_csv(raw_value: Any) -> list[str]:
    value = str(raw_value or "")
    return [part.strip() for part in value.split(",") if part.strip()]


def _serialize_available_row(row: AvailableModelRegistry | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "label": row.label,
        "catalog_model_id": row.catalog_model_id,
        "source_kind": row.source_kind,
        "provider_hint": row.provider_hint,
        "format": row.format,
        "family": row.family,
        "summary": row.summary,
        "storage_ref": row.storage_ref,
        "remote_url": row.remote_url,
        "version": row.version,
        "capabilities": normalize_capabilities(row.capabilities),
        "extended_capabilities": _serialize_csv(row.extended_capabilities),
        "interfaces": _serialize_csv(row.interfaces),
        "tags": _serialize_csv(row.tags),
        "requirements": row.requirements,
        "artifacts": row.artifacts,
        "metadata": row.metadata_json,
        "source_payload": row.source_payload,
        "extra_config": row.extra_config,
        "status": row.status,
    }
