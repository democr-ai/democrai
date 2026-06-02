from __future__ import annotations

import asyncio
import time
from typing import Any

from democrai.sdk.ai_constants import AIModelSourceKind
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.utils.actions.engine.model_import import (
    engine_import_runtime_template,
    provider_model_capabilities,
    provider_model_formats,
    provider_supports_inventory_import,
    runtime_options_schema,
    runtime_payload_from_form,
    update_imported_model_for_engine,
)
from modules.system.utils.actions.engine.models import parse_capabilities, sanitize_name


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


def _required_source_payload(source_kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    if source_kind == AIModelSourceKind.UPLOAD:
        artifact_files = payload["artifact_file"]
        if not isinstance(artifact_files, list):
            raise ValueError("system.model.toast.upload_required")
        upload_items = [item for item in artifact_files if isinstance(item, dict)]
        if not upload_items or not str(upload_items[0].get("path") or "").strip():
            raise ValueError("system.model.toast.upload_required")
        return {"artifact_file": dict(upload_items[0])}
    if source_kind == AIModelSourceKind.HUGGINGFACE:
        hf_repo = str(payload["hf_repo"]).strip()
        if not hf_repo:
            raise ValueError("system.model.toast.hf_required")
        return {
            "hf_repo": hf_repo,
            "hf_revision": str(payload["hf_revision"]).strip() or "main",
            "hf_snapshot": bool(payload["hf_snapshot"]),
        }
    raise ValueError("system.model.toast.invalid_payload")


def _model_payload(
    payload: dict[str, Any],
    *,
    provider: str,
) -> dict[str, Any]:
    name = sanitize_name(str(payload["name"]).strip())
    label = str(payload["label"]).strip()
    model_format = str(payload["format"]).strip().lower()
    capabilities = parse_capabilities(payload["capabilities"])
    valid_formats = set(provider_model_formats(provider))
    valid_capabilities = set(provider_model_capabilities(provider))
    if (
        not name
        or not label
        or not model_format
        or (valid_formats and model_format not in valid_formats)
        or (valid_capabilities and any(item not in valid_capabilities for item in capabilities))
    ):
        raise ValueError("system.model.toast.invalid_payload")
    return {
        "name": name,
        "label": label,
        "format": model_format,
        "family": "",
        "summary": str(payload.get("summary") or "").strip(),
        "capabilities": capabilities,
        "interfaces": [],
        "provider_hint": provider,
    }


@action("system.create_engine_available_model")
@permission_required(["system.engine.model.manage"])
async def create_engine_available_model(ctx: dict[str, Any], session: dict, module_sdk):
    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower()
    source_kind = str(ctx["source_kind"]).strip().lower()
    if not provider_supports_inventory_import(provider):
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.invalid_payload")
        )
    payload = dict(ctx[str(ctx["form_id"])])
    try:
        model = _model_payload(payload, provider=provider)
        source_payload = _required_source_payload(source_kind, payload)
    except ValueError as exc:
        return module_sdk.effects.respond(_toast(module_sdk, "error", str(exc)))

    template = await engine_import_runtime_template(
        module_sdk,
        provider,
        source_kind=source_kind,
    )
    submitted_runtime = runtime_payload_from_form(
        payload,
        runtime_options_schema(template),
    )

    if source_kind == AIModelSourceKind.UPLOAD:
        upload_meta = dict(source_payload["artifact_file"])
        try:
            result = await module_sdk.engines.import_model_from_source(
                source={
                    "kind": "uploaded_media",
                    "storage_path": str(upload_meta.get("path") or "").strip(),
                    "filename": str(upload_meta.get("name") or "").strip(),
                    "compatible_engines": [provider],
                },
                model=model,
            )
            row = update_imported_model_for_engine(
                module_sdk,
                dict(result.get("row") or {}),
                provider=provider,
                template=template,
                submitted_runtime=submitted_runtime,
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
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            _toast(
                module_sdk,
                "success",
                "system.model.toast.created",
                {"label": str(row.get("label") or model["label"])},
            ),
            module_sdk.effects.render(),
        )

    if source_kind == AIModelSourceKind.HUGGINGFACE:
        source = {
            "kind": AIModelSourceKind.HUGGINGFACE,
            "repo": str(source_payload["hf_repo"]).strip(),
            "revision": str(source_payload["hf_revision"]).strip() or "main",
            "snapshot": bool(source_payload["hf_snapshot"]),
            "compatible_engines": [provider],
        }
        attempt_id = str(int(time.time() * 1000))
        task_ref = {"task_id": ""}

        async def _run_download():
            while not str(task_ref.get("task_id") or "").strip():
                await asyncio.sleep(0.05)
            result = await module_sdk.engines.download_model_from_source(
                source=source,
                model=model,
                task_id=str(task_ref["task_id"]),
            )
            return update_imported_model_for_engine(
                module_sdk,
                dict(result.get("row") or {}),
                provider=provider,
                template=template,
                submitted_runtime=submitted_runtime,
            )

        task_id = await module_sdk.tasks.run_background(
            _run_download(),
            label=f"{module_sdk.i18n.t('system.model.catalog.action.download')}: {model['label']}",
            task_key=f"system.engine.model.source.download.{provider}.{model['name']}.{attempt_id}",
        )
        task_ref["task_id"] = task_id
        task_card = module_sdk.ui.BackgroundTask(
            f"engine_model_source_download_{provider}_{model['name']}_{task_id}",
            task_id=task_id,
            on_finish={
                "name": "system.filter_engine_model_catalog",
                "context": {
                    "provider": provider,
                    "engine_id": engine_id,
                    "page": 0,
                    "page_size": 20,
                },
            },
        )
        return module_sdk.effects.respond(
            module_sdk.effects.ui_messages([{"deleteSurface": {"surfaceId": "drawer"}}]),
            module_sdk.effects.ui_collection_append(
                "engine_instance_models_task_mount_col",
                "children",
                task_card.to_dict(),
            ),
            _toast(
                module_sdk,
                "success",
                "system.model.toast.catalog_started",
                {"label": model["label"]},
            ),
        )

    return module_sdk.effects.respond(
        _toast(module_sdk, "error", "system.model.toast.invalid_payload")
    )
