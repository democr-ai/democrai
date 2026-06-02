from __future__ import annotations

import json
from importlib import import_module
from typing import Any

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.engines import list_provider_definitions
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.actions.model.catalog import (
    active_catalog_download_tasks,
    catalog_entry_by_id,
    catalog_inventory_row_for_entry,
    catalog_row_with_entry_defaults,
    catalog_statuses_from_inventory,
)

_config_form_model = import_module(
    "modules.system.ui.model.catalog.[id].view"
)._config_form_model


def _route_engine_id(params: dict) -> int | None:
    route_params = dict(params.get("route_params") or {})
    value = route_params.get("id")
    return int(value) if value is not None else None


def _route_catalog_id(params: dict) -> str:
    route_params = dict(params.get("route_params") or {})
    return str(route_params.get("catalog_id") or "").strip()


def _join(values: Any) -> str:
    if not isinstance(values, list):
        return str(values or "")
    return ", ".join(str(value or "").strip() for value in values if str(value or "").strip())


def _pretty(value: Any) -> str:
    if value in (None, "", [], {}):
        return "-"
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, sort_keys=True)
    return str(value)


def _markdown_block(title: str, value: Any) -> str:
    return f"### {title}\n\n```json\n{_pretty(value)}\n```"


def _gb_value(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return f"{value} GB"


def _metadata_text(value: dict[str, Any]) -> str:
    if not value:
        return "-"
    parts: list[str] = []
    for key, item in value.items():
        if isinstance(item, list):
            item_text = _join(item)
        elif isinstance(item, dict):
            item_text = ", ".join(
                f"{nested_key}: {nested_value}" for nested_key, nested_value in item.items()
            )
        else:
            item_text = str(item)
        if item_text:
            parts.append(f"{key}: {item_text}")
    if parts:
        return " | ".join(parts)
    return "-"


def _literal(value: str) -> dict[str, str]:
    return {"literalString": str(value or "")}


def _overview_model() -> list[dict[str, str]]:
    return [
        {"field": "status", "label": sdk.i18n.t("system.model.detail.status")},
        {"field": "format", "label": sdk.i18n.t("system.model.form.format.label")},
        {"field": "source_type", "label": sdk.i18n.t("system.model.detail.source")},
        {"field": "family", "label": sdk.i18n.t("system.model.form.family.label")},
        {"field": "source_engine", "label": sdk.i18n.t("system.model.detail.source_engine")},
        {"field": "capabilities", "label": sdk.i18n.t("system.model.form.capabilities.label")},
        {"field": "engines", "label": sdk.i18n.t("system.model.catalog.item.engines")},
    ]


def _provider_definition(provider: str) -> dict[str, Any]:
    for item in list_provider_definitions() or []:
        if str(item.get("id") or "").strip().lower() == provider:
            return dict(item)
    return {}


def _provider_label(provider: str) -> str:
    definition = _provider_definition(provider)
    return str(definition.get("title") or definition.get("label") or provider)


def _entry_matches_provider(entry: dict[str, Any], provider: str) -> bool:
    source_engines = {
        str(item or "").strip().lower()
        for item in list(entry.get("source_engines") or [entry.get("source_engine")])
    }
    return provider in source_engines


async def render(params: dict, session: dict):
    engine_id = _route_engine_id(params)
    catalog_id = _route_catalog_id(params)
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    merge_builders(builder, sdk.ui.load("utils/ui/yaml/engine/model_catalog_detail"))

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["engine_model_catalog_detail_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    engine = None
    if engine_id is not None:
        try:
            engine = sdk.models.engine_registry.view(engine_id)
        except Exception:
            engine = None
    provider = str((engine or {}).get("provider") or "").strip().lower()
    engine_path = f"/system/engine/instance/{int(engine_id or 0)}/view"
    provider_label = _provider_label(provider) if provider else ""

    breadcrumb = builder.get_component("engine_model_catalog_detail_breadcrumb")
    if breadcrumb is not None:
        breadcrumb.set_property(
            "segments",
            [
                {
                    "label": sdk.i18n.t("system.engine.list.title"),
                    "path": "/system/engine/list",
                },
                {
                    "label": str((engine or {}).get("name") or provider_label or provider),
                    "path": engine_path,
                },
                {
                    "label": sdk.i18n.t("system.model.catalog.action.details"),
                    "current": True,
                },
            ],
        )

    back = builder.get_component("engine_model_catalog_detail_back")
    if back is not None:
        back.set_property(
            "action",
            {
                "name": "nav",
                "context": {
                    "type": "nav",
                    "path": engine_path,
                },
            },
        )

    entry = await catalog_entry_by_id(sdk, catalog_id)
    if not isinstance(entry, dict) or not provider or not _entry_matches_provider(entry, provider):
        title = builder.get_component("engine_model_catalog_detail_title")
        if title is not None:
            title.set_property("text", sdk.i18n.t("system.model.toast.catalog_not_found"))
        return builder

    existing_rows = (
        sdk.models.available_model_registry.all(
            sort={"field": "label", "direction": "asc"},
        ).get("rows")
        or []
    )
    existing_row = catalog_inventory_row_for_entry(entry, list(existing_rows))
    if isinstance(existing_row, dict):
        existing_row = catalog_row_with_entry_defaults(existing_row, entry)
    catalog_statuses = catalog_statuses_from_inventory(sdk, list(existing_rows), [entry])
    status = str(catalog_statuses.get(catalog_id) or "catalog_available").strip().lower()
    downloaded = status == "available"
    downloading = status == "downloading"
    can_download = not downloaded and not downloading
    builder.set_store("/engine/model/catalog_detail/imported", downloaded, scope="page")
    builder.set_store(
        "/engine/model/catalog_detail/can_download",
        can_download,
        scope="page",
    )
    builder.set_store("/engine/model/catalog_detail/downloading", downloading, scope="page")
    builder.set_store(
        "/engine/model/catalog_detail/available_model_id",
        int(existing_row["id"]) if isinstance(existing_row, dict) else None,
        scope="page",
    )
    builder.set_store(
        "/engine/model/catalog_detail/capabilities",
        list((existing_row or {}).get("capabilities") or []),
        scope="page",
    )
    constants = await sdk.engines.constants()
    builder.set_store(
        "/engine/model/catalog_detail/config_form",
        _config_form_model(existing_row, constants) if isinstance(existing_row, dict) else [],
        scope="page",
    )

    title = builder.get_component("engine_model_catalog_detail_title")
    if title is not None:
        title.set_property("text", str(entry.get("label") or ""))

    summary = builder.get_component("engine_model_catalog_detail_summary")
    if summary is not None:
        summary.set_property("text", str(entry.get("summary") or ""))

    overview = builder.get_component("engine_model_catalog_detail_overview")
    if overview is not None:
        overview.set_property("model", _overview_model())
        overview.set_property(
            "data",
            {
                "status": sdk.i18n.t(
                    {
                        "available": "system.model.catalog.status.imported",
                        "downloading": "system.model.catalog.status.downloading",
                        "failed": "system.model.catalog.status.failed",
                    }.get(status, "system.model.catalog.status.available")
                ),
                "format": str(entry.get("format") or ""),
                "source_type": str(entry.get("source_type") or ""),
                "family": str(entry.get("family") or ""),
                "source_engine": _join(
                    list(entry.get("source_engines") or [entry.get("source_engine")])
                ),
                "capabilities": _join(list(entry.get("capabilities") or [])),
                "engines": _join(
                    list(entry.get("source_engines") or [entry.get("source_engine")])
                ),
            },
        )

    requirements_data = dict(entry.get("requirements") or {})
    metadata_data = dict(entry.get("metadata") or {})
    artifacts_data = list(entry.get("artifacts") or [])

    ram_value = builder.get_component("engine_model_catalog_detail_ram_value")
    if ram_value is not None:
        ram_value.set_property("text", _gb_value(requirements_data.get("ram_gb")))

    storage_value = builder.get_component("engine_model_catalog_detail_storage_value")
    if storage_value is not None:
        storage_value.set_property("text", _gb_value(requirements_data.get("storage_gb")))

    metadata = builder.get_component("engine_model_catalog_detail_metadata")
    if metadata is not None:
        metadata.set_property("text", _metadata_text(metadata_data))

    artifacts = builder.get_component("engine_model_catalog_detail_artifacts")
    if artifacts is not None:
        artifacts.set_property(
            "text",
            _markdown_block(
                sdk.i18n.t("system.model.detail.artifacts"),
                artifacts_data,
            ),
        )

    download = builder.get_component("engine_model_catalog_detail_download")
    if download is not None:
        download.set_property("label", _literal(sdk.i18n.t("system.model.catalog.action.download")))
        download.set_property(
            "params",
            {
                "catalog_id": catalog_id,
                "engine_id": int(engine_id or 0),
                "provider": provider,
                "task_mount_id": "engine_model_catalog_detail_tasks",
            },
        )
        if status == "failed":
            download.set_property(
                "label",
                _literal(sdk.i18n.t("system.model.catalog.action.retry")),
            )

    tasks_container = builder.get_component("engine_model_catalog_detail_tasks")
    if tasks_container is not None:
        tasks_container.allow("children.append")
        active_task = active_catalog_download_tasks(sdk).get(catalog_id)
        task_id = str(
            (active_task or {}).get("id")
            or (active_task or {}).get("task_id")
            or (active_task or {}).get("taskId")
            or ""
        ).strip()
        if task_id:
            task_card_id = f"engine_model_catalog_detail_task_{task_id}"
            builder.add(
                sdk.ui.BackgroundTask(
                    task_card_id,
                    task_id,
                    on_finish={
                        "name": "nav",
                        "context": {
                            "type": "nav",
                            "path": (
                                f"/system/engine/instance/{int(engine_id or 0)}"
                                f"/model/catalog/{catalog_id}/view"
                            ),
                        },
                    },
                )
            )
            tasks_container.set_children([task_card_id])

    return builder
