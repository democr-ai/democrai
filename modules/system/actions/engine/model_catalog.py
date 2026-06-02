from __future__ import annotations

import asyncio
import time
from typing import Any

from democrai.sdk.ai_constants import AI_CONTEXT_POLICIES
from democrai.sdk.auth import permission_required
from democrai.sdk.decorators import action

from modules.system.actions.engine.available_models.helpers import (
    EMBEDDING_INPUT_POLICY_KEY,
)
from modules.system.utils.actions.model.catalog import active_catalog_download_ids
from modules.system.utils.ui.engine.model_catalog import (
    ENGINE_CATALOG_PAGE_SIZE,
    load_engine_catalog_page,
)
from modules.system.utils.ui.model.catalog import catalog_list_page, catalog_page_info


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


def _configuration_toast(
    module_sdk,
    level: str,
    title_key: str,
    message_key: str,
):
    return module_sdk.effects.notify(
        "toast",
        {
            "level": level,
            "title": module_sdk.i18n.t(title_key),
            "message": module_sdk.i18n.t(message_key),
        },
    )


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("expected_string_list")
    return [str(item).strip() for item in value if str(item).strip()]


def _positive_int(value: Any) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("expected_positive_int") from None
    if result <= 0:
        raise ValueError("expected_positive_int")
    return result


def _context_policy(value: Any) -> str:
    policy = str(value or "").strip()
    if policy and policy not in set(AI_CONTEXT_POLICIES):
        raise ValueError("invalid_context_policy")
    return policy


def _feature_config(
    payload: dict[str, Any],
    capability: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    config = dict(schema["default"])
    config["supported"] = True
    mime_key = f"feature__{capability}__mime_types"
    if mime_key in payload:
        mime_types = _string_list(payload[mime_key])
        schema_fields = list(_dict(schema).get("fields") or [])
        mime_field = next(
            (
                _dict(field)
                for field in schema_fields
                if _dict(field).get("name") == "mime_types"
            ),
            {},
        )
        item_schema = _dict(mime_field.get("item_schema"))
        valid_values = {
            str(option.get("value") or "").strip()
            for option in list(item_schema.get("options") or [])
            if isinstance(option, dict)
        }
        if valid_values and any(item not in valid_values for item in mime_types):
            raise ValueError("invalid_mime_types")
        config["mime_types"] = mime_types
    if capability == "reasoning" and "feature__reasoning__mode" in payload:
        config["mode"] = str(payload["feature__reasoning__mode"] or "").strip()
    return config


def _catalog_items_with_status(
    module_sdk,
    items: Any,
    entry: dict[str, Any],
    status: str,
    provider: str,
    engine_id: int,
) -> list[dict[str, Any]]:
    current_items = [dict(item) for item in items if isinstance(item, dict)] if isinstance(items, list) else []
    catalog_id = str(entry.get("catalog_id") or "").strip()
    if not current_items or not catalog_id:
        return current_items
    replacement = catalog_list_page(
        module_sdk,
        [entry],
        {catalog_id: status},
        engine_filter=str(provider or "").strip().lower(),
        page_size=1,
    ).get("items") or []
    if not replacement or not isinstance(replacement[0], dict):
        return current_items
    replacement_item = dict(replacement[0])
    replacement_item["detail_path"] = (
        f"/system/engine/instance/{engine_id}/model/catalog/{catalog_id}/view"
    )
    return [
        replacement_item if str(item.get("id") or "") == catalog_id else item
        for item in current_items
    ]


def _filter_catalog_items(
    items: list[dict[str, Any]],
    *,
    search: str = "",
    status_filter: str = "",
) -> list[dict[str, Any]]:
    query = str(search or "").strip().lower()
    status = str(status_filter or "").strip().lower()
    filtered: list[dict[str, Any]] = []
    for item in items:
        if status and str(item.get("status") or "").strip().lower() != status:
            continue
        if query:
            haystack = " ".join(
                [
                    str(item.get("title") or ""),
                    str(item.get("text") or ""),
                    str(item.get("id") or ""),
                ]
            ).lower()
            if query not in haystack:
                continue
        filtered.append(item)
    return filtered


@action("system.filter_engine_model_catalog")
@permission_required(["system.engine.model.manage"])
async def filter_engine_model_catalog(ctx: dict[str, Any], session: dict, module_sdk):
    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower()
    page_size = max(1, min(int(ctx.get("page_size") or ENGINE_CATALOG_PAGE_SIZE), 100))
    page = max(0, int(ctx.get("page") or 0))
    direction = str(ctx["direction"]).strip() if "direction" in ctx else ""
    if direction == "next":
        page += 1
    elif direction == "prev":
        page -= 1

    search = str(ctx.get("engine_model_catalog_search") or "").strip()
    status_filter = str(ctx.get("engine_model_catalog_status_filter") or "").strip()
    page_data = await load_engine_catalog_page(
        module_sdk,
        provider,
        engine_id=engine_id,
        search=search,
        status_filter=status_filter,
        page=page,
        page_size=page_size,
    )
    resolved_page = int(page_data.get("page") or 0)
    resolved_page_size = int(page_data.get("page_size") or page_size)
    total = int(page_data.get("total") or 0)
    surface_id = str(ctx["_surface_id"])
    button_params = {
        "provider": provider,
        "page": resolved_page,
        "page_size": resolved_page_size,
    }

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_model_catalog/show_pagination": total
                            > resolved_page_size,
                            "/engine_model_catalog/items": list(page_data.get("items") or []),
                            "/engine_model_catalog/visible_items": list(
                                page_data.get("items") or []
                            ),
                        },
                    }
                }
            ]
        ),
        module_sdk.effects.ui_property_update(
            "engine_model_catalog_page_info",
            "text",
            catalog_page_info(
                module_sdk,
                page=resolved_page,
                page_size=resolved_page_size,
                total=total,
            ),
            surface_id=surface_id,
        ),
        module_sdk.effects.ui_property_update(
            "engine_model_catalog_prev",
            "params",
            {**button_params, "direction": "prev"},
            surface_id=surface_id,
        ),
        module_sdk.effects.ui_property_update(
            "engine_model_catalog_next",
            "params",
            {**button_params, "direction": "next"},
            surface_id=surface_id,
        ),
    )


@action("system.download_engine_model_catalog")
@permission_required(["system.engine.model.manage"])
async def download_engine_model_catalog(ctx: dict[str, Any], session: dict, module_sdk):
    catalog_id = str(ctx["catalog_id"]).strip()
    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower()
    confirmed_resource_warning = bool(ctx.get("confirmed_resource_warning"))

    try:
        preflight = await module_sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=confirmed_resource_warning,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "catalog_already_added":
            return module_sdk.effects.respond(
                _toast(module_sdk, "warning", "system.model.toast.catalog_already_added")
            )
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.catalog_not_found")
        )

    entry = dict(preflight.get("entry") or {})
    active_downloads = active_catalog_download_ids(module_sdk)
    if catalog_id in active_downloads:
        return module_sdk.effects.respond(
            _toast(module_sdk, "warning", "system.model.toast.catalog_already_running")
        )

    if str(preflight.get("status") or "") == "requires_confirmation":
        return module_sdk.effects.respond(
            module_sdk.effects.confirm(
                via="dialog",
                path="/system/engine/model/catalog/resource_warning",
                params={
                    "catalog_id": catalog_id,
                    "engine_id": engine_id,
                    "provider": provider,
                    "task_mount_id": str(ctx["task_mount_id"]).strip(),
                    "label": str(entry.get("label") or ""),
                    "resource_warning": dict(preflight.get("resource_warning") or {}),
                    "items": list(ctx.get("items") or []),
                    "action_name": "system.download_engine_model_catalog",
                },
            )
        )

    attempt_id = str(int(time.time() * 1000))
    task_ref = {"task_id": ""}

    async def _run_download():
        while not str(task_ref.get("task_id") or "").strip():
            await asyncio.sleep(0.05)
        return await module_sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=confirmed_resource_warning,
            task_id=str(task_ref["task_id"]),
        )

    task_id = await module_sdk.tasks.run_background(
        _run_download(),
        label=f"{module_sdk.i18n.t('system.model.catalog.action.download')}: {str(entry.get('label') or '')}",
        task_key=f"system.model.catalog.download.{catalog_id}.{attempt_id}",
    )
    task_ref["task_id"] = task_id

    mount_id = str(ctx["task_mount_id"]).strip()
    refresh_action = {
        "name": "system.filter_engine_model_catalog",
        "context": {
            "provider": provider,
            "engine_id": engine_id,
            "page": 0,
            "page_size": ENGINE_CATALOG_PAGE_SIZE,
            "engine_model_catalog_search": str(
                ctx.get("engine_model_catalog_search") or ""
            ).strip(),
            "engine_model_catalog_status_filter": str(
                ctx.get("engine_model_catalog_status_filter") or ""
            ).strip(),
        },
    }
    task_card = module_sdk.ui.BackgroundTask(
        f"engine_model_catalog_download_{catalog_id}_{task_id}",
        task_id=task_id,
        on_finish=refresh_action,
    )
    catalog_items = _catalog_items_with_status(
        module_sdk,
        ctx.get("items"),
        entry,
        "downloading",
        provider,
        engine_id,
    )
    search = str(ctx.get("engine_model_catalog_search") or "").strip()
    status_filter = str(ctx.get("engine_model_catalog_status_filter") or "").strip()
    visible_catalog_items = _filter_catalog_items(
        catalog_items,
        search=search,
        status_filter=status_filter,
    )
    messages = [
        {"deleteSurface": {"surfaceId": "drawer"}},
        {"deleteSurface": {"surfaceId": "modal"}},
    ]
    if catalog_items:
        messages.append(
            {
                "stateUpdate": {
                    "scope": "page",
                    "values": {
                        "/engine_model_catalog/items": catalog_items,
                        "/engine_model_catalog/visible_items": visible_catalog_items,
                    },
                }
            }
        )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(messages),
        module_sdk.effects.ui_collection_append(
            mount_id,
            "children",
            task_card.to_dict(),
        ),
        _toast(
            module_sdk,
            "success",
            "system.model.toast.catalog_started",
            {"label": str(entry.get("label") or "")},
        ),
    )


@action("system.delete_engine_catalog_available_model")
@permission_required(["system.engine.model.manage"])
async def delete_engine_catalog_available_model(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
):
    catalog_id = str(ctx["catalog_id"]).strip()
    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower()
    rows = (
        module_sdk.models.available_model_registry.all(
            filters={"catalog_model_id": catalog_id},
        ).get("rows")
        or []
    )
    row = rows[0] if rows and isinstance(rows[0], dict) else None
    if not isinstance(row, dict):
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.catalog_not_found")
        )

    try:
        await module_sdk.engines.delete_available_model(available_model_id=int(row["id"]))
    except Exception as exc:
        return module_sdk.effects.respond(
            _toast(
                module_sdk,
                "error",
                "system.model.toast.delete_failed",
                {"error": str(exc)},
            )
        )

    page_size = max(1, min(int(ctx.get("page_size") or ENGINE_CATALOG_PAGE_SIZE), 100))
    search = str(ctx.get("engine_model_catalog_search") or "").strip()
    status_filter = str(ctx.get("engine_model_catalog_status_filter") or "").strip()
    page_data = await load_engine_catalog_page(
        module_sdk,
        provider,
        engine_id=engine_id,
        search=search,
        status_filter=status_filter,
        page=0,
        page_size=page_size,
    )
    total = int(page_data.get("total") or 0)
    surface_id = str(ctx["_surface_id"])

    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine_model_catalog/show_pagination": total
                            > page_size,
                            "/engine_model_catalog/items": list(
                                page_data.get("items") or []
                            ),
                            "/engine_model_catalog/visible_items": list(
                                page_data.get("items") or []
                            ),
                        },
                    }
                }
            ]
        ),
        module_sdk.effects.ui_property_update(
            "engine_model_catalog_page_info",
            "text",
            catalog_page_info(
                module_sdk,
                page=0,
                page_size=page_size,
                total=total,
            ),
            surface_id=surface_id,
        ),
        _toast(module_sdk, "success", "system.model.toast.deleted"),
    )


@action("system.download_engine_catalog_detail_model")
@permission_required(["system.engine.model.manage"])
async def download_engine_catalog_detail_model(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
):
    catalog_id = str(ctx["catalog_id"]).strip()
    engine_id = int(ctx["engine_id"])
    provider = str(ctx["provider"]).strip().lower()
    confirmed_resource_warning = bool(ctx.get("confirmed_resource_warning"))

    try:
        preflight = await module_sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=confirmed_resource_warning,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "catalog_already_added":
            return module_sdk.effects.respond(
                _toast(module_sdk, "warning", "system.model.toast.catalog_already_added")
            )
        return module_sdk.effects.respond(
            _toast(module_sdk, "error", "system.model.toast.catalog_not_found")
        )

    entry = dict(preflight.get("entry") or {})
    active_downloads = active_catalog_download_ids(module_sdk)
    if catalog_id in active_downloads:
        return module_sdk.effects.respond(
            _toast(module_sdk, "warning", "system.model.toast.catalog_already_running")
        )

    if str(preflight.get("status") or "") == "requires_confirmation":
        return module_sdk.effects.respond(
            module_sdk.effects.confirm(
                via="dialog",
                path="/system/engine/model/catalog/resource_warning",
                params={
                    "catalog_id": catalog_id,
                    "engine_id": engine_id,
                    "provider": provider,
                    "task_mount_id": str(ctx["task_mount_id"]).strip(),
                    "label": str(entry.get("label") or ""),
                    "resource_warning": dict(preflight.get("resource_warning") or {}),
                    "items": [],
                    "action_name": "system.download_engine_catalog_detail_model",
                },
            )
        )

    attempt_id = str(int(time.time() * 1000))
    task_ref = {"task_id": ""}

    async def _run_download():
        while not str(task_ref.get("task_id") or "").strip():
            await asyncio.sleep(0.05)
        return await module_sdk.engines.download_model(
            catalog_id=catalog_id,
            confirmed_resource_warning=confirmed_resource_warning,
            task_id=str(task_ref["task_id"]),
        )

    task_id = await module_sdk.tasks.run_background(
        _run_download(),
        label=f"{module_sdk.i18n.t('system.model.catalog.action.download')}: {str(entry.get('label') or '')}",
        task_key=f"system.model.catalog.download.{catalog_id}.{attempt_id}",
    )
    task_ref["task_id"] = task_id

    detail_path = f"/system/engine/instance/{engine_id}/model/catalog/{catalog_id}/view"
    task_card = module_sdk.ui.BackgroundTask(
        f"engine_model_catalog_detail_download_{catalog_id}_{task_id}",
        task_id=task_id,
        on_finish={
            "name": "nav",
            "context": {
                "type": "nav",
                "path": detail_path,
            },
        },
    )
    return module_sdk.effects.respond(
        module_sdk.effects.ui_messages(
            [
                {"deleteSurface": {"surfaceId": "drawer"}},
                {"deleteSurface": {"surfaceId": "modal"}},
                {
                    "stateUpdate": {
                        "scope": "page",
                        "values": {
                            "/engine/model/catalog_detail/imported": False,
                            "/engine/model/catalog_detail/can_download": False,
                            "/engine/model/catalog_detail/downloading": True,
                        },
                    }
                },
            ]
        ),
        module_sdk.effects.ui_collection_append(
            str(ctx["task_mount_id"]).strip(),
            "children",
            task_card.to_dict(),
        ),
        _toast(
            module_sdk,
            "success",
            "system.model.toast.catalog_started",
            {"label": str(entry.get("label") or "")},
        ),
    )


@action("system.update_engine_catalog_model_configuration")
@permission_required(["system.engine.model.manage"])
async def update_engine_catalog_model_configuration(
    ctx: dict[str, Any],
    session: dict,
    module_sdk,
):
    row_id = int(ctx["available_model_id"])
    payload = dict(ctx[str(ctx["form_id"])])
    constants = await module_sdk.engines.constants()

    valid_capabilities = constants.get("model_capabilities")
    if not isinstance(valid_capabilities, list):
        raise ValueError("sdk engines constants model_capabilities must be a list")
    valid_capability_set = {str(item) for item in valid_capabilities}
    try:
        capabilities = _string_list(payload.get("capabilities"))
    except ValueError:
        return module_sdk.effects.respond(
            _configuration_toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_capabilities",
            )
        )
    if any(item not in valid_capability_set for item in capabilities):
        return module_sdk.effects.respond(
            _configuration_toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_capabilities",
            )
        )

    row = module_sdk.models.available_model_registry.view(row_id)
    if not isinstance(row, dict):
        return module_sdk.effects.respond(module_sdk.effects.render())

    label = str(payload.get("label") or "").strip()
    if not label:
        return module_sdk.effects.respond(
            _configuration_toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_payload",
            )
        )

    extra_config = _dict(row.get("extra_config"))
    defaults = _dict(extra_config.get("defaults"))
    runtime = _dict(defaults.get("runtime"))
    output_parsers = constants.get("output_parsers")
    if not isinstance(output_parsers, list):
        raise ValueError("sdk engines constants output_parsers must be a list")
    if "chat" in capabilities:
        output_parser = str(payload.get("output_parser") or "generic").strip()
        if output_parser not in output_parsers:
            return module_sdk.effects.respond(
                _configuration_toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        runtime["output_parser"] = output_parser
    else:
        runtime.pop("output_parser", None)
    if "reasoning" in capabilities:
        reasoning_parser = str(payload.get("reasoning_parser") or "").strip()
        if reasoning_parser and reasoning_parser not in output_parsers:
            return module_sdk.effects.respond(
                _configuration_toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        if reasoning_parser:
            runtime["reasoning_parser"] = reasoning_parser
        else:
            runtime.pop("reasoning_parser", None)
    else:
        runtime.pop("reasoning_parser", None)

    feature_schemas = _dict(constants.get("model_feature_schemas"))
    feature_keys = [item for item in capabilities if item in feature_schemas]
    try:
        features = {
            capability: _feature_config(
                payload,
                capability,
                _dict(feature_schemas.get(capability)),
            )
            for capability in feature_keys
        }
    except ValueError:
        return module_sdk.effects.respond(
            _configuration_toast(
                module_sdk,
                "error",
                "system.model.toast.configuration_error_title",
                "system.model.toast.invalid_model_configuration",
            )
        )
    if "embedding" in feature_keys:
        try:
            dim = _positive_int(payload.get("dim"))
        except ValueError:
            return module_sdk.effects.respond(
                _configuration_toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        policy = {
            "document_prefix": str(payload.get("embedding_document_prefix") or ""),
            "query_prefix": str(payload.get("embedding_query_prefix") or ""),
            "default_purpose": str(
                payload.get("embedding_default_purpose") or "document"
            ).strip(),
        }
        runtime[EMBEDDING_INPUT_POLICY_KEY] = policy
        features["embedding"]["input_policy"] = policy
        runtime["dim"] = dim
    elif EMBEDDING_INPUT_POLICY_KEY in runtime:
        runtime.pop(EMBEDDING_INPUT_POLICY_KEY)
        runtime.pop("dim", None)
    if "context_length" in payload:
        runtime["context_length"] = _positive_int(payload.get("context_length"))
        runtime.pop("n_ctx", None)
        runtime.pop("max_model_len", None)
        runtime.pop("num_ctx", None)
    if "context_policy" in payload:
        try:
            policy = _context_policy(payload.get("context_policy"))
        except ValueError:
            return module_sdk.effects.respond(
                _configuration_toast(
                    module_sdk,
                    "error",
                    "system.model.toast.configuration_error_title",
                    "system.model.toast.invalid_model_configuration",
                )
            )
        if policy:
            runtime["context_policy"] = policy
        else:
            runtime.pop("context_policy", None)

    module_sdk.models.available_model_registry.update(
        row_id,
        {
            "label": label,
            "summary": str(payload.get("summary") or "").strip(),
            "capabilities": capabilities,
            "extra_config": {
                **extra_config,
                "defaults": {
                    **defaults,
                    "runtime": runtime,
                },
                "features": features,
            },
        },
    )
    return module_sdk.effects.respond(
        _configuration_toast(
            module_sdk,
            "success",
            "system.model.toast.configuration_updated_title",
            "system.model.toast.configuration_updated",
        ),
        module_sdk.effects.render(),
    )
