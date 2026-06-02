from __future__ import annotations

import asyncio
import time
from typing import Any

from democrai.sdk.ai_constants import AIModelSourceKind
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.utils.actions.model.inventory import (
    prepare_available_model_payload,
)
from modules.system.utils.ui.model.inventory import inventory_list_items
from modules.system.utils.ui.model.runtime import engine_rows_by_id, loaded_model_items


def _toast(
    module_sdk,
    level: str,
    message_key: str,
    context: dict[str, Any] | None = None,
):
    return module_sdk.effects.notify(
        "toast",
        {
            "level": level,
            "message": module_sdk.i18n.t(message_key, context=context or {}),
        },
    )


def _source_payload(source_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if source_kind == AIModelSourceKind.UPLOAD:
        artifact_files = payload["artifact_file"]
        if not isinstance(artifact_files, list):
            raise ValueError("system.model.toast.upload_required")
        upload_items = [item for item in artifact_files if isinstance(item, dict)]
        if not upload_items or not str(upload_items[0].get("path") or "").strip():
            raise ValueError("system.model.toast.upload_required")
        return {
            "remote_url": None,
            "hf_repo": None,
            "hf_revision": "main",
            "hf_snapshot": False,
            "artifact_file": dict(upload_items[0]),
            "tags": [],
        }
    if source_kind == AIModelSourceKind.URL:
        remote_url = str(payload["remote_url"]).strip()
        if not remote_url:
            raise ValueError("system.model.toast.url_required")
        return {
            "remote_url": remote_url,
            "hf_repo": None,
            "hf_revision": "main",
            "hf_snapshot": False,
            "artifact_file": {},
            "tags": [],
        }
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        hf_repo = str(payload["hf_repo"]).strip()
        if not hf_repo:
            raise ValueError("system.model.toast.hf_required")
        return {
            "remote_url": None,
            "hf_repo": hf_repo,
            "hf_revision": str(payload["hf_revision"]).strip() or "main",
            "hf_snapshot": bool(payload["hf_snapshot"]),
            "artifact_file": {},
            "tags": [],
        }
    return {
        "remote_url": None,
        "hf_repo": None,
        "hf_revision": "main",
        "hf_snapshot": False,
        "artifact_file": {},
        "tags": [],
    }


@action("system.filter_manual_models")
@permission_required(["system.engine.model.manage"])
async def filter_manual_models(ctx: dict[str, Any], session: dict, module_sdk):
    search = str(ctx["system_model_manual_import_search"]).strip()
    status_filter = str(ctx["system_model_manual_import_status_filter"]).strip()
    rows = (
        module_sdk.models.available_model_registry.all(
            sort={"field": "label", "direction": "asc"},
        ).get("rows")
        or []
    )
    surface_id = str(ctx["_surface_id"])
    return module_sdk.effects.respond(
        module_sdk.effects.ui_property_update(
            "system_model_manual_import_list",
            "dataSource",
            {
                "type": "inline",
                "data": inventory_list_items(
                    module_sdk,
                    list(rows),
                    search=search,
                    status_filter=status_filter,
                ),
            },
            action="set",
            surface_id=surface_id,
        )
    )


@action("system.unload_loaded_model")
@permission_required(["system.engine.model.manage"])
async def unload_loaded_model(ctx: dict[str, Any], session: dict, module_sdk):
    engine_registry_id = int(ctx["engine_registry_id"])
    model_registry_id = int(ctx["model_registry_id"])
    result = await module_sdk.engines.unload_loaded_model(
        engine_registry_id=engine_registry_id,
        model_registry_id=model_registry_id,
    )
    loaded_rows = await module_sdk.engines.list_loaded_models()
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/system/model/loaded/items": loaded_model_items(
                                list(loaded_rows),
                                engine_rows_by_id(module_sdk),
                            )
                        },
                    }
                }
            ]
        ),
        module_sdk.effects.notify(
            "toast",
            {
                "level": "success" if result.get("unloaded") else "warning",
                "message": (
                    "Model unloaded from memory"
                    if result.get("unloaded")
                    else "Model was not loaded in memory"
                ),
            },
        ),
    )


@action("create_available_model")
@permission_required(["system.engine.model.manage"])
async def create_available_model(ctx: dict[str, Any], session: dict, module_sdk):
    payload = dict(ctx[str(ctx["form_id"])])
    payload["source_kind"] = ctx["source_kind"]
    normalized = prepare_available_model_payload(payload)
    if not normalized["name"] or not normalized["label"] or not normalized["format"]:
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.invalid_payload")
        )

    source_kind = normalized["source_kind"]
    try:
        source_payload = _source_payload(source_kind, payload)
    except ValueError as exc:
        return module_sdk.effects.respond(_toast(module_sdk, "error", str(exc)))

    if source_kind == AIModelSourceKind.UPLOAD:
        upload_meta = dict(source_payload["artifact_file"])
        try:
            result = await module_sdk.engines.import_model_from_source(
                source={
                    "kind": "uploaded_media",
                    "storage_path": str(upload_meta.get("path") or "").strip(),
                    "filename": str(upload_meta.get("name") or "").strip(),
                },
                model={
                    "name": normalized["name"],
                    "label": normalized["label"],
                    "format": normalized["format"],
                    "family": normalized["family"],
                    "summary": normalized["summary"],
                    "capabilities": normalized["capabilities"],
                    "interfaces": normalized["interfaces"],
                },
            )
        except Exception as exc:
            return module_sdk.effects.respond(
                _toast(
                    module_sdk,
                    "error",
                    "system.model.toast.create_failed",
                    {"error": str(exc)},
                )
            )
        row = dict(result.get("row") or {})
    elif source_kind in {AIModelSourceKind.URL, AIModelSourceKind.HUGGINGFACE}:
        source = _remote_download_source(source_kind, source_payload)
        model = {
            "name": normalized["name"],
            "label": normalized["label"],
            "format": normalized["format"],
            "family": normalized["family"],
            "summary": normalized["summary"],
            "capabilities": normalized["capabilities"],
            "interfaces": normalized["interfaces"],
        }
        attempt_id = str(int(time.time() * 1000))
        task_ref = {"task_id": ""}

        async def _run_download():
            while not str(task_ref.get("task_id") or "").strip():
                await asyncio.sleep(0.05)
            return await module_sdk.engines.download_model_from_source(
                source=source,
                model=model,
                task_id=str(task_ref["task_id"]),
            )

        task_id = await module_sdk.tasks.run_background(
            _run_download(),
            label=f"{module_sdk.i18n.t('system.model.catalog.action.download')}: {normalized['label']}",
            task_key=f"system.model.source.download.{normalized['name']}.{attempt_id}",
        )
        task_ref["task_id"] = task_id
        task_card = module_sdk.ui.BackgroundTask(
            f"model_source_download_{normalized['name']}_{task_id}",
            task_id=task_id,
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_collection_append(
                "system_model_tasks_cards",
                "children",
                task_card.to_dict(),
            ),
            _toast(
                module_sdk,
                "success",
                "system.model.toast.catalog_started",
                {"label": normalized["label"]},
            ),
            module_sdk.effects.render(),
        )
    else:
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.invalid_payload")
        )

    return module_sdk.effects.respond(
        _toast(
            module_sdk,
            "success",
            "system.model.toast.created",
            {"label": str(row.get("label") or normalized["label"])},
        ),
        module_sdk.effects.render(),
    )


def _remote_download_source(source_kind: str, source_payload: dict[str, Any]) -> dict[str, Any]:
    if source_kind == AIModelSourceKind.URL:
        return {
            "kind": AIModelSourceKind.URL,
            "url": str(source_payload["remote_url"]).strip(),
        }
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        return {
            "kind": AIModelSourceKind.HUGGINGFACE,
            "repo": str(source_payload["hf_repo"]).strip(),
            "revision": str(source_payload["hf_revision"]).strip() or "main",
            "snapshot": bool(source_payload["hf_snapshot"]),
        }
    raise ValueError("unsupported_model_download_source")


async def _delete_available_model_row(module_sdk, row_id: int):
    try:
        await module_sdk.engines.delete_available_model(available_model_id=row_id)
    except ValueError as exc:
        message = str(exc)
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.delete_failed",
                {"error": message},
            )
        )
    except Exception as exc:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.delete_failed",
                {"error": str(exc)},
            )
        )
    return module_sdk.effects.respond(
        _toast(module_sdk, "success", "system.model.toast.deleted"),
        module_sdk.effects.render(),
    )


@action("delete_catalog_available_model")
@permission_required(["system.engine.model.manage"])
async def delete_catalog_available_model(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
):
    catalog_id = str(ctx["catalog_id"]).strip()
    rows = (
        module_sdk.models.available_model_registry.all(
            filters={"catalog_model_id": catalog_id},
        ).get("rows")
        or []
    )
    row = rows[0] if rows and isinstance(rows[0], dict) else None
    if isinstance(row, dict):
        return await _delete_available_model_row(module_sdk, int(row["id"]))
    return module_sdk.effects.respond(
        _toast(module_sdk, "error", "system.model.toast.catalog_not_found")
    )


@action("delete_available_model")
@permission_required(["system.engine.model.manage"])
async def delete_available_model(ctx: dict[str, Any], session: dict, module_sdk):
    row_id = int(ctx["available_model_id"])
    row = module_sdk.models.available_model_registry.view(row_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())
    return await _delete_available_model_row(module_sdk, row_id)
