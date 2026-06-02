from __future__ import annotations

import hashlib
from typing import Any

from democrai.sdk.ai_constants import (
    AIModelSource,
    AIModelSourceKind,
    normalize_capabilities,
    normalize_token,
)
from democrai.sdk.engines import get_provider_definition, list_provider_definitions


def first_artifact(model: dict[str, Any]) -> dict[str, Any] | None:
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


def primary_format(model: dict[str, Any]) -> str:
    artifact = first_artifact(model)
    if artifact is None:
        return str(model.get("format") or "").strip().lower()
    return str(artifact.get("format") or model.get("format") or "").strip().lower()


def source_type(model: dict[str, Any]) -> str:
    artifact = first_artifact(model)
    if artifact is None:
        provisioning = model.get("provisioning") if isinstance(model.get("provisioning"), dict) else {}
        download = provisioning.get("download") if isinstance(provisioning.get("download"), dict) else {}
        if str(download.get("strategy") or "").strip().lower() == "none":
            return "none"
        return ""
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    return str(source.get("type") or "").strip().lower()


def compatible_with_engine(provider: str, *, model_format: str, capabilities: list[str]) -> bool:
    normalized_provider = str(provider or "").strip().lower()
    definition = get_provider_definition(normalized_provider) or {}
    if normalize_token(definition.get("model_source")) != AIModelSource.INVENTORY:
        return False
    accepted_formats = {
        normalize_token(item) for item in (definition.get("accepted_model_formats") or [])
    }
    normalized_format = str(model_format or "").strip().lower()
    if accepted_formats and normalized_format and normalized_format not in accepted_formats:
        return False

    model_caps = set(normalize_capabilities(capabilities))
    engine_caps = set(
        normalize_capabilities(
            definition.get("model_capabilities") or definition.get("capabilities") or []
        )
    )
    if not model_caps or not engine_caps:
        return True
    return bool(model_caps.intersection(engine_caps))


def compatible_engine_ids(
    model_format: str,
    capabilities: list[str],
    *,
    source_engine: str,
    explicit_engines: list[str] | None = None,
) -> list[str]:
    explicit = [
        str(item or "").strip().lower()
        for item in (explicit_engines or [])
        if str(item or "").strip()
    ]
    if explicit:
        return _merge_unique_strings(explicit, [source_engine])
    compatible: list[str] = []
    if source_engine not in compatible:
        compatible.append(source_engine)
    return compatible


def _catalog_signature(model: dict[str, Any], *, source_engine: str) -> str:
    artifact = first_artifact(model) or {}
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    model_format = primary_format(model)
    source_kind = str(source.get("type") or "").strip().lower()
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        repo = str(source.get("repo") or "").strip()
        revision = str(source.get("revision") or "main").strip() or "main"
        files = ",".join(str(item or "").strip() for item in (source.get("files") or []))
        snapshot = "1" if bool(source.get("snapshot")) else "0"
        raw = f"hf::{repo}::{revision}::{files}::{snapshot}::{model_format}"
    elif source_kind in {"http", "https", AIModelSourceKind.URL}:
        raw = f"url::{str(source.get('url') or '').strip()}::{model_format}"
    else:
        raw = f"legacy::{source_engine}::{str(model.get('id') or '').strip()}::{model_format}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _merge_unique_strings(left: list[str], right: list[str]) -> list[str]:
    resolved = list(left)
    for item in right:
        value = str(item or "").strip()
        if value and value not in resolved:
            resolved.append(value)
    return resolved


def active_catalog_download_ids(module_sdk) -> set[str]:
    return {catalog_id for catalog_id, _task in active_catalog_download_tasks(module_sdk).items()}


def active_catalog_download_tasks(module_sdk) -> dict[str, dict[str, Any]]:
    active_statuses = {"pending", "running", "waiting_confirmation"}
    active_catalog_tasks: dict[str, dict[str, Any]] = {}
    prefix = "system.model.catalog.download."
    for task in module_sdk.tasks.get_tasks_by_key_prefix(prefix):
        status = str(task.get("status") or "").strip().lower()
        if status not in active_statuses:
            continue
        task_key = str(task.get("taskKey") or task.get("task_key") or "").strip()
        if not task_key.startswith(prefix):
            continue
        remainder = task_key[len(prefix):]
        catalog_id = remainder.rsplit(".", 1)[0] if "." in remainder else remainder
        if catalog_id:
            active_catalog_tasks[catalog_id] = task
    return active_catalog_tasks


def _catalog_status_from_row(row: dict[str, Any], *, active_downloads: set[str]) -> str:
    status = str(row.get("status") or "").strip().lower()
    catalog_id = str(row.get("catalog_model_id") or "").strip()
    if status == "downloading" and catalog_id and catalog_id not in active_downloads:
        return "failed"
    if status in {"available", "installed", "active"}:
        return "available"
    return status or "available"


def _source_identity(model: dict[str, Any]) -> tuple[str, ...]:
    artifact = first_artifact(model) or {}
    source = artifact.get("source") if isinstance(artifact.get("source"), dict) else {}
    model_format = primary_format(model)
    source_kind = str(source.get("type") or "").strip().lower()
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        files = tuple(
            str(item or "").strip()
            for item in list(source.get("files") or [])
            if str(item or "").strip()
        )
        return (
            "hf",
            str(source.get("repo") or "").strip(),
            str(source.get("revision") or "main").strip() or "main",
            "1" if bool(source.get("snapshot")) else "0",
            model_format,
            *files,
        )
    if source_kind in {"http", "https", AIModelSourceKind.URL}:
        return (
            "url",
            str(source.get("url") or "").strip(),
            model_format,
        )
    return ()


def _provider_matches(entry: dict[str, Any], row: dict[str, Any]) -> bool:
    row_provider = str(row.get("provider_hint") or "").strip().lower()
    source_engines = {
        str(item or "").strip().lower()
        for item in (entry.get("source_engines") or [entry.get("source_engine")])
        if str(item or "").strip()
    }
    return bool(row_provider and row_provider in source_engines)


def catalog_inventory_row_matches(entry: dict[str, Any], row: dict[str, Any]) -> bool:
    catalog_id = str(entry.get("catalog_id") or "").strip()
    row_catalog_id = str(row.get("catalog_model_id") or "").strip()
    if catalog_id and row_catalog_id == catalog_id:
        return True

    source_payload = row.get("source_payload") if isinstance(row.get("source_payload"), dict) else {}
    if catalog_id and str(source_payload.get("catalog_id") or "").strip() == catalog_id:
        return True

    legacy_model_id = str(entry.get("legacy_model_id") or "").strip()
    row_name = str(row.get("name") or "").strip()
    if not legacy_model_id or row_name != legacy_model_id:
        entry_identity = _source_identity(entry)
        row_identity = _source_identity(row)
        return bool(
            entry_identity
            and row_identity
            and entry_identity == row_identity
            and _provider_matches(entry, row)
        )

    return _provider_matches(entry, row)


def catalog_inventory_row_for_entry(
    entry: dict[str, Any],
    inventory_rows: list[dict[str, Any]],
) -> dict[str, Any] | None:
    for row in inventory_rows:
        if isinstance(row, dict) and catalog_inventory_row_matches(entry, row):
            return row
    return None


def catalog_row_with_entry_defaults(
    row: dict[str, Any],
    entry: dict[str, Any],
) -> dict[str, Any]:
    extra_config = row.get("extra_config") if isinstance(row.get("extra_config"), dict) else {}
    defaults = extra_config.get("defaults") if isinstance(extra_config.get("defaults"), dict) else {}
    generation = defaults.get("generation") if isinstance(defaults.get("generation"), dict) else {}
    runtime = defaults.get("runtime") if isinstance(defaults.get("runtime"), dict) else {}
    entry_runtime = entry.get("runtime") if isinstance(entry.get("runtime"), dict) else {}
    entry_defaults = (
        entry_runtime.get("defaults")
        if isinstance(entry_runtime.get("defaults"), dict)
        else {}
    )
    entry_generation = (
        entry_defaults.get("generation")
        if isinstance(entry_defaults.get("generation"), dict)
        else {}
    )
    entry_runtime_defaults = (
        entry_defaults.get("runtime")
        if isinstance(entry_defaults.get("runtime"), dict)
        else (
            entry_defaults
            if not isinstance(entry_defaults.get("generation"), dict)
            else {}
        )
    )
    return {
        **row,
        "extra_config": {
            **extra_config,
            "defaults": {
                **defaults,
                "generation": {
                    **entry_generation,
                    **generation,
                },
                "runtime": {
                    **entry_runtime_defaults,
                    **runtime,
                },
            },
        },
    }


def catalog_statuses_from_inventory(
    module_sdk,
    inventory_rows: list[dict[str, Any]],
    catalog_entries: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    active_downloads = active_catalog_download_ids(module_sdk)
    statuses: dict[str, str] = {catalog_id: "downloading" for catalog_id in active_downloads}
    for row in inventory_rows:
        if not isinstance(row, dict) or not row.get("catalog_model_id"):
            continue
        catalog_id = str(row["catalog_model_id"]).strip()
        statuses[catalog_id] = _catalog_status_from_row(row, active_downloads=active_downloads)
    for entry in catalog_entries or []:
        if not isinstance(entry, dict):
            continue
        catalog_id = str(entry.get("catalog_id") or "").strip()
        if not catalog_id or catalog_id in statuses:
            continue
        row = catalog_inventory_row_for_entry(entry, inventory_rows)
        if row is not None:
            statuses[catalog_id] = _catalog_status_from_row(row, active_downloads=active_downloads)
    return statuses


def _normalize_catalog_entry(model: dict[str, Any], *, source_engine: str) -> dict[str, Any]:
    model_format = primary_format(model)
    resolved_source_type = source_type(model)
    return {
        "catalog_id": _catalog_signature(model, source_engine=source_engine),
        "legacy_model_id": str(model.get("id") or "").strip(),
        "label": str(model.get("label") or model.get("id") or "").strip(),
        "family": str(model.get("family") or "").strip(),
        "summary": str(model.get("summary") or "").strip(),
        "format": model_format,
        "capabilities": normalize_capabilities(model.get("capabilities") or []),
        "extended_capabilities": normalize_capabilities(
            model.get("extended_capabilities") or []
        ),
        "interfaces": [
            str(item or "").strip()
            for item in (model.get("interfaces") or [])
            if str(item or "").strip()
        ],
        "requirements": dict(model.get("requirements") or {}),
        "provisioning": dict(model.get("provisioning") or {}),
        "artifacts": list(model.get("artifacts") or []),
        "runtime": dict(model.get("runtime") or {}),
        "features": dict(model.get("features") or {}),
        "metadata": dict(model.get("metadata") or {}),
        "source_engine": source_engine,
        "source_type": resolved_source_type,
        "compatible_engines": compatible_engine_ids(
            model_format,
            normalize_capabilities(model.get("capabilities") or []),
            source_engine=source_engine,
            explicit_engines=list(model.get("compatible_engines") or []),
        ),
        "downloadable": resolved_source_type in {"http", "https", AIModelSourceKind.HUGGINGFACE, AIModelSourceKind.URL},
    }


def _installed_engine_ids(module_sdk) -> set[str]:
    rows = (
        module_sdk.models.engine_registry.all(
            sort={"field": "provider", "direction": "asc"},
        ).get("rows")
        or []
    )
    installed_statuses = {"active", "installed"}
    engine_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "").strip().lower()
        if status not in installed_statuses:
            continue
        provider = str(row.get("provider") or "").strip().lower()
        if provider:
            engine_ids.add(provider)
    return engine_ids


async def load_static_model_catalog(module_sdk) -> list[dict[str, Any]]:
    entries: dict[str, dict[str, Any]] = {}
    installed_engine_ids = _installed_engine_ids(module_sdk)
    for definition in list_provider_definitions() or []:
        if not isinstance(definition, dict):
            continue
        if normalize_token(definition.get("model_source")) == AIModelSource.PROVIDER_API:
            continue
        engine_id = str(definition.get("id") or "").strip().lower()
        if not engine_id:
            continue
        if engine_id not in installed_engine_ids:
            continue
        try:
            models = await module_sdk.engines.list_catalog_models(engine_id=engine_id)
        except Exception:
            models = []
        for model in models:
            if not isinstance(model, dict):
                continue
            if source_type(model) == "local_upload":
                continue
            model_format = primary_format(model)
            if not model_format:
                continue
            entry = _normalize_catalog_entry(model, source_engine=engine_id)
            key = str(entry.get("catalog_id") or "")
            if key not in entries:
                entries[key] = entry
                entries[key]["source_engines"] = [engine_id]
                continue
            current = entries[key]
            current["compatible_engines"] = _merge_unique_strings(
                list(current.get("compatible_engines") or []),
                list(entry.get("compatible_engines") or []),
            )
            current["source_engines"] = _merge_unique_strings(
                list(current.get("source_engines") or []),
                [engine_id],
            )
    return sorted(entries.values(), key=lambda item: str(item.get("label") or "").lower())


async def catalog_entry_by_id(module_sdk, catalog_id: str) -> dict[str, Any] | None:
    resolved_id = str(catalog_id or "").strip()
    if not resolved_id:
        return None
    for entry in await load_static_model_catalog(module_sdk):
        if str(entry.get("catalog_id") or "") == resolved_id:
            return entry
    return None
