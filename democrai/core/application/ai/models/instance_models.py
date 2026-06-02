from __future__ import annotations

import asyncio
from typing import Any

from democrai.core.application.ai.constants import (
    AIDeployment,
    AIModelFormat,
    AIModelSource,
    AIModelSourceKind,
    AIRegistryStatus,
    methods_for_capabilities,
    normalize_capabilities,
    normalize_token,
)
from democrai.core.application.ai.models.catalog import list_engine_models
from democrai.core.application.ai.engine.config_crypto import decrypt_provider_config
from democrai.core.application.ai.engine.manifests import get_engine_manifest
from democrai.core.application.ai.engine.runtime.methods import (
    invoke_engine_method,
    run_engine_result,
)
from democrai.core.application.ai.engine.runtime.worker import EngineWorkerSubject
from democrai.core.infrastructure.database import SessionLocal
from democrai.core.infrastructure.database.models import (
    AvailableModelRegistry,
    EngineRegistry,
    ModelRegistry,
)
from democrai.core.platform.utils.identity import to_optional_int


def _csv_to_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value or "").split(",")
    resolved: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in resolved:
            resolved.append(text)
    return resolved


def _runtime_model_ref(row: ModelRegistry) -> str:
    extra_config = row.extra_config if isinstance(row.extra_config, dict) else {}
    return extra_config.get("runtime_model_ref") or row.model_path or row.name


def _binding_label(row: ModelRegistry) -> str:
    extra_config = row.extra_config if isinstance(row.extra_config, dict) else {}
    return extra_config.get("binding_label") or row.name


def _serialize_registered_model(row: ModelRegistry) -> dict[str, Any]:
    extra_config = row.extra_config if isinstance(row.extra_config, dict) else {}
    registry_meta = (
        extra_config.get("_model_registry")
        if isinstance(extra_config.get("_model_registry"), dict)
        else {}
    )
    capabilities = normalize_capabilities(row.capabilities)
    return {
        "id": row.id,
        "name": row.name,
        "model_id": _runtime_model_ref(row),
        "label": _binding_label(row),
        "engine_id": row.engine_id,
        "available_model_id": row.available_model_id,
        "model_path": row.model_path,
        "remote_url": row.remote_url,
        "version": row.version,
        "capabilities": capabilities,
        "runtime_methods": methods_for_capabilities(capabilities),
        "status": row.status or "available",
        "is_downloaded": row.is_downloaded,
        "source_mode": registry_meta.get("source_mode") or AIModelSourceKind.CATALOG,
        "source_kind": (
            (
                extra_config.get("available_model")
                if isinstance(extra_config.get("available_model"), dict)
                else {}
            ).get("source_kind")
            or registry_meta.get("source_mode")
            or AIModelSourceKind.REGISTERED
        ),
        "extra_config": extra_config,
    }


def _serialize_inventory_model(row: AvailableModelRegistry) -> dict[str, Any]:
    capabilities = normalize_capabilities(row.capabilities)
    return {
        "id": row.name,
        "model_id": row.name,
        "label": row.label,
        "available_model_id": row.id,
        "catalog_model_id": row.catalog_model_id,
        "source_kind": row.source_kind,
        "provider_hint": row.provider_hint,
        "format": row.format,
        "family": row.family,
        "summary": row.summary,
        "storage_ref": row.storage_ref,
        "remote_url": row.remote_url,
        "version": row.version,
        "capabilities": capabilities,
        "runtime_methods": methods_for_capabilities(capabilities),
        "interfaces": _csv_to_list(row.interfaces),
        "tags": _csv_to_list(row.tags),
        "requirements": row.requirements if isinstance(row.requirements, dict) else {},
        "artifacts": row.artifacts if isinstance(row.artifacts, list) else [],
        "source_payload": row.source_payload if isinstance(row.source_payload, dict) else {},
        "status": row.status,
    }


def _engine_row(engine_id: int | str) -> EngineRegistry | None:
    row_id = to_optional_int(engine_id)
    if row_id is None:
        return None
    with SessionLocal() as session:
        row = session.query(EngineRegistry).filter(EngineRegistry.id == row_id).first()
        if row is None:
            return None
        session.expunge(row)
        return row


def _provider_definition(provider: str) -> dict[str, Any]:
    manifest = get_engine_manifest(provider) or {}
    provider_payload = (
        manifest.get("provider") if isinstance(manifest.get("provider"), dict) else {}
    )
    return provider_payload


def _provider_model_source(provider: str) -> str:
    provider_payload = _provider_definition(provider)
    source = normalize_token(provider_payload.get("model_source"))
    if source:
        return source
    deployment = normalize_token(provider_payload.get("deployment"))
    if deployment in {AIDeployment.REMOTE, AIDeployment.HYBRID}:
        return AIModelSource.PROVIDER_API
    return AIModelSource.INVENTORY


def _accepted_model_formats(provider: str) -> set[str]:
    provider_payload = _provider_definition(provider)
    formats = provider_payload.get("accepted_model_formats")
    return {normalize_token(item) for item in _csv_to_list(formats)}


def _accepted_model_capabilities(provider: str) -> set[str]:
    provider_payload = _provider_definition(provider)
    capabilities = provider_payload.get("model_capabilities")
    if not capabilities:
        capabilities = provider_payload.get("capabilities")
    return set(normalize_capabilities(capabilities or []))


def _compatible_with_inventory(provider: str, row: AvailableModelRegistry) -> bool:
    normalized_provider = normalize_token(provider)
    provider_hint = normalize_token(row.provider_hint)
    if provider_hint and provider_hint == normalized_provider:
        return True
    source_payload = row.source_payload if isinstance(row.source_payload, dict) else {}
    explicit_engines = {
        normalize_token(item)
        for item in _csv_to_list(source_payload.get("compatible_engines") or [])
    }
    if explicit_engines:
        return normalized_provider in explicit_engines
    formats = _accepted_model_formats(normalized_provider)
    capabilities = _accepted_model_capabilities(normalized_provider)
    model_format = normalize_token(row.format)
    if formats and model_format and model_format not in formats:
        return False
    model_caps = set(normalize_capabilities(row.capabilities))
    if not model_caps or not capabilities:
        return True
    return bool(model_caps.intersection(capabilities))


def _serialize_catalog_model(
    provider: str,
    row: dict[str, Any],
    *,
    source_kind: str = AIModelSource.ENGINE_CATALOG,
    status: str = AIRegistryStatus.AVAILABLE,
) -> dict[str, Any]:
    capabilities = normalize_capabilities(row.get("capabilities") or [])
    runtime = row.get("runtime") if isinstance(row.get("runtime"), dict) else {}
    provisioning = (
        row.get("provisioning") if isinstance(row.get("provisioning"), dict) else {}
    )
    return {
        "id": row["id"],
        "model_id": row["id"],
        "label": row.get("label", row["id"]),
        "available_model_id": None,
        "catalog_model_id": row["id"],
        "source_kind": source_kind,
        "provider_hint": normalize_token(provider),
        "format": row.get("format", AIModelFormat.HF_SNAPSHOT),
        "family": row.get("family", ""),
        "summary": row.get("summary", ""),
        "storage_ref": "",
        "remote_url": "",
        "version": row.get("version", ""),
        "capabilities": capabilities,
        "runtime_methods": methods_for_capabilities(capabilities),
        "interfaces": _csv_to_list(row.get("interfaces") or []),
        "tags": _csv_to_list(row.get("tags") or []),
        "requirements": row.get("requirements")
        if isinstance(row.get("requirements"), dict)
        else {},
        "artifacts": row.get("artifacts") if isinstance(row.get("artifacts"), list) else [],
        "provisioning": provisioning,
        "runtime": runtime,
        "features": row.get("features") if isinstance(row.get("features"), dict) else {},
        "status": status,
    }


def _runtime_model_ref_from_catalog(row: dict[str, Any]) -> str:
    runtime = row.get("runtime") if isinstance(row.get("runtime"), dict) else {}
    return runtime.get("model_ref") or row.get("id") or ""


def _provider_discovery_ids(rows: list[Any]) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        model_id = row.get("id") or row.get("model_id") or ""
        if model_id:
            ids.add(model_id)
    return ids


def _available_rows_by_provider_name(
    provider: str,
    model_ids: list[str],
) -> dict[str, AvailableModelRegistry]:
    resolved_provider = normalize_token(provider)
    ids = [item for item in model_ids if item]
    if not resolved_provider or not ids:
        return {}
    with SessionLocal() as session:
        rows = (
            session.query(AvailableModelRegistry)
            .filter(AvailableModelRegistry.provider_hint == resolved_provider)
            .filter(AvailableModelRegistry.name.in_(ids))
            .all()
        )
        for row in rows:
            session.expunge(row)
    return {row.name: row for row in rows if row.name}


def _merge_catalog_model_registry_state(
    payload: dict[str, Any],
    row: AvailableModelRegistry | None,
) -> dict[str, Any]:
    if row is None:
        return payload
    merged = dict(payload)
    merged.update(
        {
            "available_model_id": row.id,
            "storage_ref": row.storage_ref,
            "remote_url": row.remote_url or merged.get("remote_url") or "",
            "version": row.version or merged.get("version") or "",
            "status": row.status or merged.get("status") or AIRegistryStatus.AVAILABLE,
        }
    )
    return merged


def list_registered_models_for_engine(engine_id: int | str) -> list[dict[str, Any]]:
    row_id = to_optional_int(engine_id)
    if row_id is None:
        return []
    with SessionLocal() as session:
        rows = (
            session.query(ModelRegistry)
            .filter(ModelRegistry.engine_id == row_id)
            .order_by(ModelRegistry.name.asc())
            .all()
        )
        return [_serialize_registered_model(row) for row in rows]


async def _refresh_local_network_allowlist_for_engine(provider: str) -> None:
    from democrai.core.infrastructure.sandbox.os.events import (
        process_application_network_allowlist_refresh_event,
    )

    await process_application_network_allowlist_refresh_event(
        {
            "reason": "engine_provider_api_models",
            "resource_type": "engine",
            "module_name": "democrai.core.engine_models",
            "target": provider,
            "mode": "runtime",
        }
    )


async def list_available_models_for_engine(engine_id: int | str) -> list[dict[str, Any]]:
    engine = _engine_row(engine_id)
    if engine is None:
        return []
    provider = engine.provider
    if not provider:
        return []
    model_source = _provider_model_source(provider)

    config = decrypt_provider_config(provider, engine.config or {})
    if model_source == AIModelSource.PROVIDER_API:
        import os

        catalog_rows = [row for row in list_engine_models(provider) if isinstance(row, dict)]
        await _refresh_local_network_allowlist_for_engine(provider)
        if os.environ.get("DEMOCRAI_ENGINE_ORCHESTRATOR") != "1":
            from democrai.core.application.ai.engine.orchestrator.client import (
                EngineOrchestratorClient,
            )

            rows = await asyncio.to_thread(
                EngineOrchestratorClient().invoke_engine_action,
                engine_registry_id=engine.id,
                engine_id=provider,
                config=config,
                method="list_available_models",
                payload={},
            )
        else:
            subject = EngineWorkerSubject(engine_id=provider, config=config)
            try:
                rows = run_engine_result(
                    invoke_engine_method(
                        subject,
                        "list_available_models",
                        {},
                    )
                )
            finally:
                subject.close()
        if not isinstance(rows, list):
            return []
        if catalog_rows:
            discovered_ids = _provider_discovery_ids(rows)
            normalized: list[dict[str, Any]] = []
            for row in catalog_rows:
                model_id = row.get("id") or ""
                runtime_model_ref = _runtime_model_ref_from_catalog(row)
                if model_id not in discovered_ids and runtime_model_ref not in discovered_ids:
                    continue
                normalized.append(
                    _serialize_catalog_model(
                        provider,
                        row,
                        source_kind=AIModelSource.PROVIDER_API,
                    )
                )
            return normalized
        normalized: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id") or row.get("model_id") or ""
            if not model_id:
                continue
            capabilities = normalize_capabilities(row.get("capabilities") or [])
            normalized.append(
                {
                    "id": model_id,
                    "model_id": model_id,
                    "label": row.get("label") or model_id,
                    "capabilities": capabilities,
                    "runtime_methods": methods_for_capabilities(capabilities),
                    "source_kind": AIModelSource.PROVIDER_API,
                    "provider_hint": provider,
                    "format": row.get("format") or AIModelFormat.REMOTE,
                    "summary": row.get("summary") or "",
                    "status": row.get("status") or "available",
                }
            )
        return normalized

    if model_source == AIModelSource.ENGINE_CATALOG:
        catalog_rows = [row for row in list_engine_models(provider) if isinstance(row, dict)]
        catalog_ids = [row.get("id") or "" for row in catalog_rows]
        provider_rows = _available_rows_by_provider_name(provider, catalog_ids)
        return [
            _merge_catalog_model_registry_state(
                _serialize_catalog_model(provider, row),
                provider_rows.get(row.get("id") or ""),
            )
            for row in catalog_rows
        ]

    with SessionLocal() as session:
        rows = (
            session.query(AvailableModelRegistry)
            .filter(AvailableModelRegistry.status == "available")
            .order_by(AvailableModelRegistry.label.asc())
            .all()
        )
        return [
            _serialize_inventory_model(row)
            for row in rows
            if _compatible_with_inventory(provider, row)
        ]
