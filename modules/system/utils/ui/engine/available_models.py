from __future__ import annotations

from typing import Any

from democrai.sdk.ai_constants import AIModelSource
from democrai.sdk.ai_constants import AIRegistryStatus


def model_filter_value(ctx: dict[str, Any], field_id: str) -> str:
    return str(ctx[field_id]).strip()


def _csv_text(values: list[Any]) -> str:
    return ", ".join(str(item or "").strip() for item in values if str(item or "").strip())


def model_key(row: dict[str, Any]) -> str:
    return str(row["model_id"]).strip()


def _download_strategy(row: dict[str, Any]) -> str:
    provisioning = (
        row.get("provisioning") if isinstance(row.get("provisioning"), dict) else {}
    )
    download = (
        provisioning.get("download")
        if isinstance(provisioning.get("download"), dict)
        else {}
    )
    return str(download.get("strategy") or "").strip().lower()


def activated_model_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys: dict[str, int] = {}
    for row in rows:
        if str(row.get("status") or "").strip().lower() != "active":
            continue
        model_row_id = int(row["id"])
        key = model_key(row)
        keys[key] = model_row_id
        available_model_id = row.get("available_model_id")
        if available_model_id is not None:
            keys[f"available:{available_model_id}"] = model_row_id
    return keys


def available_item(
    row: dict[str, Any],
    *,
    activated: bool,
    model_row_id: int | None,
) -> dict[str, Any]:
    capabilities = list(row["capabilities"])
    source_kind = str(row["source_kind"]).strip()
    model_format = str(row["format"]).strip()
    summary = str(row["summary"]).strip()
    meta = " | ".join(
        value
        for value in [source_kind, model_format, _csv_text(capabilities), summary]
        if value
    )
    available_model_id = row.get("available_model_id")
    key = model_key(row)
    storage_ref = str(row.get("storage_ref") or "").strip()
    status = str(row["status"]).strip().lower()
    is_downloaded = (
        available_model_id is not None
        and bool(storage_ref)
        and status == AIRegistryStatus.AVAILABLE
    )
    is_engine_catalog_runtime_model = (
        source_kind == AIModelSource.ENGINE_CATALOG
        and status == AIRegistryStatus.AVAILABLE
        and _download_strategy(row) == "none"
    )
    activation_kind = (
        "inventory"
        if is_downloaded
        else "registration"
        if source_kind == AIModelSource.PROVIDER_API and not capabilities
        else "provider"
        if source_kind == AIModelSource.PROVIDER_API or is_engine_catalog_runtime_model
        else "unavailable"
    )
    return {
        "id": key,
        "title": str(row["label"]).strip(),
        "text": meta,
        "icon": "ric.checkbox-circle-line" if activated else "ric.circle-line",
        "icon_color": "#22C55E" if activated else "#94A3B8",
        "activated": activated,
        "model_row_id": model_row_id,
        "activation_kind": activation_kind,
        "available_model_id": available_model_id,
        "is_downloaded": is_downloaded,
        "is_engine_catalog_runtime_model": is_engine_catalog_runtime_model,
        "storage_ref": storage_ref,
        "model_id": key,
        "model_label": str(row["label"]).strip(),
        "source_kind": source_kind,
        "format": model_format,
        "provisioning": row.get("provisioning")
        if isinstance(row.get("provisioning"), dict)
        else {},
        "runtime": row.get("runtime") if isinstance(row.get("runtime"), dict) else {},
        "features": row.get("features") if isinstance(row.get("features"), dict) else {},
        "capabilities": capabilities,
        "capabilities_text": _csv_text(capabilities),
        "search_text": " ".join(
            [
                str(row["label"]).strip(),
                key,
                source_kind,
                model_format,
                _csv_text(capabilities),
                summary,
            ]
        ).lower(),
    }


def filter_available_items(
    items: list[dict[str, Any]], *, name: str = "", capability: str = ""
) -> list[dict[str, Any]]:
    name_query = str(name or "").strip().lower()
    capability_query = str(capability or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for item in items:
        if name_query and name_query not in str(item["search_text"]):
            continue
        if capability_query:
            capabilities = [
                str(capability or "").strip().lower()
                for capability in item["capabilities"]
            ]
            if not any(capability_query in capability for capability in capabilities):
                continue
        filtered.append(item)
    return filtered


async def load_available_items(module_sdk, engine_id: int) -> list[dict[str, Any]]:
    available_models = await module_sdk.engines.list_available_models(engine_id=str(engine_id))
    activated_models = await module_sdk.engines.list_models(engine_id=str(engine_id))
    activated = activated_model_rows(activated_models)
    items: list[dict[str, Any]] = []
    for row in available_models:
        key = model_key(row)
        available_model_id = row.get("available_model_id")
        model_row_id = activated.get(key)
        if model_row_id is None and available_model_id is not None:
            model_row_id = activated.get(f"available:{available_model_id}")
        items.append(
            available_item(
                row,
                activated=model_row_id is not None,
                model_row_id=model_row_id,
            )
        )
    return items
