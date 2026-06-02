from __future__ import annotations

from typing import Any

from modules.system.utils.actions.knowledge.extractors import extractor_install_task_key


ENABLED_EXTRACTOR_IDS = ("docling", "ai_audio", "ai_image")
ACTIVE_TASK_STATUSES = {"pending", "running", "waiting_confirmation"}
EXTRACTOR_INSTALL_TASK_MOUNT_ID = "knowledge_extractor_install_task_mount"


def _t(module_sdk, key: str, context: dict[str, Any] | None = None) -> str:
    return module_sdk.i18n.t(key, context=context or {})


def active_extractor_install_task_ids(
    module_sdk,
    *,
    extractor_id: str,
    extractor_row_id: int,
    organization_id: int | None = None,
) -> list[str]:
    task_ids: list[str] = []
    for task in module_sdk.tasks.get_tasks_by_key(
        extractor_install_task_key(extractor_id, extractor_row_id),
        organization_id,
    ):
        status = str(task.get("status") or "").strip().lower()
        if status not in ACTIVE_TASK_STATUSES:
            continue
        task_id = str(task.get("taskId") or task.get("id") or "").strip()
        if task_id:
            task_ids.append(task_id)
    return task_ids


def _registry_rows_by_extractor_id(module_sdk) -> dict[str, dict[str, Any]]:
    listing = module_sdk.models.extractor_registry.list(
        page=0,
        page_size=200,
        filters={},
    )
    rows: dict[str, dict[str, Any]] = {}
    for row in listing.get("rows") or []:
        if not isinstance(row, dict):
            continue
        extractor_id = str(row.get("extractor_id") or "").strip().lower()
        if extractor_id:
            rows[extractor_id] = row
    return rows


def _enabled_manifests(module_sdk) -> list[dict[str, Any]]:
    enabled = set(ENABLED_EXTRACTOR_IDS)
    manifests = []
    for manifest in module_sdk.extractors.list_manifests():
        extractor_id = str(manifest.get("id") or "").strip().lower()
        if extractor_id in enabled:
            manifests.append(dict(manifest))
    manifests.sort(key=lambda item: ENABLED_EXTRACTOR_IDS.index(str(item.get("id"))))
    return manifests


def extractor_engine_rows(module_sdk) -> list[dict[str, Any]]:
    registry_rows = _registry_rows_by_extractor_id(module_sdk)
    rows: list[dict[str, Any]] = []
    for manifest in _enabled_manifests(module_sdk):
        extractor_id = str(manifest.get("id") or "").strip().lower()
        registry = registry_rows.get(extractor_id, {})
        mime_types = list(manifest.get("mime_types") or [])
        rows.append(
            {
                "extractor_id": extractor_id,
                "name": str(manifest.get("name") or extractor_id),
                "status": str(registry.get("status") or "uninstalled"),
                "mime_types": ", ".join(str(item) for item in mime_types),
                "mime_type_items": [str(item) for item in mime_types],
                "mime_type_count": len(mime_types),
                "file_extensions": ", ".join(
                    str(item) for item in list(manifest.get("file_extensions") or [])
                ),
                "icon_url": str(manifest.get("icon_url") or ""),
                "registry_row_id": registry.get("id"),
                "config": dict(registry.get("config") or {}),
                "install_config": dict(registry.get("install_config") or {}),
                "install_config_schema": list(
                    (manifest.get("install") or {}).get("config_schema") or []
                )
                if isinstance(manifest.get("install"), dict)
                else [],
                "runtime_config_schema": list(
                    (manifest.get("runtime") or {}).get("config_schema") or []
                )
                if isinstance(manifest.get("runtime"), dict)
                else [],
            }
        )
    return rows


def extractor_engine_row(module_sdk, extractor_id: str) -> dict[str, Any] | None:
    normalized = str(extractor_id or "").strip().lower()
    for row in extractor_engine_rows(module_sdk):
        if str(row.get("extractor_id") or "").strip().lower() == normalized:
            return row
    return None


def _status_variant(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized == "active":
        return "success"
    if normalized in {"installed", "installing"}:
        return "secondary"
    if normalized == "error":
        return "destructive"
    return "outline"


def extractor_status_variant(status: str) -> str:
    return _status_variant(status)


def _model_options_for_capability(module_sdk, capability: str) -> list[dict[str, Any]]:
    normalized = str(capability or "").strip().lower()
    options: list[dict[str, Any]] = [
        {
            "label": _t(module_sdk, "system.knowledge.extractors.select_model"),
            "value": "",
        }
    ]
    rows = (
        module_sdk.models.model_registry.all(filters={"status": "active"}).get("rows")
        or []
    )
    available_models = {
        int(row["id"]): row
        for row in (
            module_sdk.models.available_model_registry.all().get("rows")
            or []
        )
        if isinstance(row, dict) and row.get("id") is not None
    }
    engines = {
        int(row["id"]): row
        for row in (
            module_sdk.models.engine_registry.all().get("rows")
            or []
        )
        if isinstance(row, dict) and row.get("id") is not None
    }
    for row in rows:
        if not isinstance(row, dict):
            continue
        capabilities = {
            str(item or "").strip().lower()
            for item in list(row.get("capabilities") or [])
            if str(item or "").strip()
        }
        if normalized and normalized not in capabilities:
            continue
        available = available_models.get(int(row.get("available_model_id") or 0))
        engine = engines.get(int(row.get("engine_id") or 0))
        model_name = (
            str((available or {}).get("label") or "").strip()
            or str(row.get("name") or row.get("id")).strip()
        )
        engine_name = (
            str((engine or {}).get("name") or "").strip()
            or str((engine or {}).get("provider") or "").strip()
        )
        label = f"{model_name} ({engine_name})" if engine_name else model_name
        options.append(
            {
                "label": label,
                "value": int(row["id"]),
            }
        )
    return options


def _config_form_field(
    module_sdk,
    field: dict[str, Any],
    values: dict[str, Any],
) -> dict[str, Any]:
    item = dict(field)
    name = str(item.get("name") or "").strip()
    if name and name in values:
        item["value"] = values[name]
    source = item.get("source") if isinstance(item.get("source"), dict) else {}
    if source.get("type") == "model_registry":
        item["options"] = _model_options_for_capability(
            module_sdk,
            str(source.get("capability") or ""),
        )
    return item


def extractor_config_form_model(
    module_sdk,
    row: dict[str, Any],
    *,
    phase: str,
) -> list[dict[str, Any]]:
    resolved_phase = str(phase or "").strip().lower()
    if resolved_phase == "install":
        schema = list(row.get("install_config_schema") or [])
        values = dict(row.get("install_config") or {})
    else:
        schema = list(row.get("runtime_config_schema") or [])
        values = dict(row.get("config") or {})
    return [
        _config_form_field(module_sdk, field, values)
        for field in schema
        if isinstance(field, dict)
    ]


def _install_card_action(module_sdk, row: dict[str, Any]) -> dict[str, Any] | None:
    extractor_id = str(row.get("extractor_id") or "").strip().lower()
    status = str(row.get("status") or "").strip().lower()
    if status not in {"uninstalled", "error"}:
        return None
    label = (
        _t(module_sdk, "system.knowledge.extractors.retry_install")
        if status == "error"
        else _t(module_sdk, "system.knowledge.extractors.install")
    )
    has_install_config = bool(list(row.get("install_config_schema") or []))
    if has_install_config:
        action = {
            "name": "open_modal",
            "context": {
                "path": f"/system/knowledge/extractors/install_config/{extractor_id}",
        "title": label,
                "width": 560,
            },
        }
    else:
        action = {
            "name": "system.install_extractor",
            "context": {"extractor_id": extractor_id},
        }
    item = {
        "label": label,
        "icon": "ric.download-cloud-2",
        "variant": "primary",
        "action": action,
        "required_permissions": ["system.knowledge.extractor.manage"],
    }
    if not has_install_config:
        item["track_loading"] = "system.install_extractor"
    return item


def add_extractor_engine_cards(
    module_sdk,
    builder,
    *,
    container_id: str,
    organization_id: int | None = None,
) -> None:
    card_ids: list[str] = []
    task_card_ids: list[str] = []
    for row in extractor_engine_rows(module_sdk):
        extractor_id = str(row.get("extractor_id") or "").strip().lower()
        if not extractor_id:
            continue

        registry_row_id = row.get("registry_row_id")
        active_task_ids: list[str] = []
        if registry_row_id is not None:
            active_task_ids = active_extractor_install_task_ids(
                module_sdk,
                extractor_id=extractor_id,
                extractor_row_id=int(registry_row_id),
                organization_id=organization_id,
            )

        safe_id = extractor_id.replace("-", "_")
        card_id = f"knowledge_extractor_{safe_id}_card"
        wrapper_id = f"knowledge_extractor_{safe_id}_wrap"
        status = "installing" if active_task_ids else str(row.get("status") or "uninstalled")

        icon = module_sdk.ui.Image(
            f"{card_id}_icon",
            str(row.get("name") or extractor_id),
            url=str(row.get("icon_url") or "assets/engines/llamacpp.png"),
            width=48,
            height=48,
        )
        icon.set_property(
            "style",
            (
                "min-width: 48px; min-height: 48px; max-width: 48px; "
                "max-height: 48px;"
            ),
        )

        header = module_sdk.ui.Row(
            f"{card_id}_header",
            [
                icon,
                module_sdk.ui.Column(
                    f"{card_id}_identity",
                    [
                        module_sdk.ui.Title(
                            f"{card_id}_title",
                            str(row.get("name") or extractor_id),
                            level=4,
                        ),
                        module_sdk.ui.Text(
                            f"{card_id}_description",
                            _t(
                                module_sdk,
                                "system.knowledge.extractors.mime_types_count",
                                {"count": int(row.get("mime_type_count") or 0)},
                            ),
                        ),
                    ],
                ),
            ],
        )
        header.set_property("spacing", 12)
        header.set_property("style", "margin-bottom: 12px;")

        meta = module_sdk.ui.Row(
            f"{card_id}_meta",
            [
                module_sdk.ui.Badge(
                    f"{card_id}_status",
                    status,
                    variant=_status_variant(status),
                ),
                module_sdk.ui.Badge(
                    f"{card_id}_count",
                    _t(
                        module_sdk,
                        "system.knowledge.extractors.mime_count",
                        {"count": int(row.get("mime_type_count") or 0)},
                    ),
                    variant="info",
                ),
                module_sdk.ui.Button(
                    f"{card_id}_mime_types_btn",
                    "",
                    action="open_modal",
                    params={
                        "path": (
                            "/system/knowledge/extractors/mime_types/"
                            f"{extractor_id}"
                        ),
                        "title": _t(
                            module_sdk,
                            "system.knowledge.extractors.mime_types_title",
                            {"name": str(row.get("name") or extractor_id)},
                        ),
                        "width": 640,
                    },
                    icon="ric.list-check-2",
                    variant="secondary",
                    mode="ghost",
                    shape="icon",
                ),
            ],
        )
        meta.set_property("spacing", 8)
        meta.set_property("style", "margin-bottom: 12px;")

        card_children = [header, meta]
        actions = [
            {
                "label": _t(module_sdk, "system.knowledge.extractors.details"),
                "icon": "ric.external-link-line",
                "variant": "default",
                "action": {
                    "name": "nav",
                    "context": {
                        "type": "nav",
                        "path": f"/system/knowledge/extractors/{extractor_id}",
                    },
                },
            }
        ]
        install_action = None if active_task_ids else _install_card_action(module_sdk, row)
        if install_action is not None:
            actions.append(install_action)

        card = module_sdk.ui.Card(
            card_id,
            card_children,
            variant="elevated",
            item_actions=actions,
            data={
                "extractor_id": extractor_id,
                "status": status,
                "registry_row_id": row.get("registry_row_id"),
            },
        )
        card.set_property("padding", [16, 16, 16, 16])
        card.set_property("style", "width: 480px; max-width: 480px;")

        wrapper = module_sdk.ui.Column(wrapper_id, [card])
        wrapper.set_property("width", 480)
        wrapper.set_property("max_width", 480)
        wrapper.set_property("style", "max-width: 480px;")
        builder.add(wrapper)
        card_ids.append(wrapper_id)

        for task_id in active_task_ids:
            task_card_id = (
                f"knowledge_extractor_install_task_{registry_row_id}_{task_id}"
            )
            builder.add(
                module_sdk.ui.BackgroundTask(
                    task_card_id,
                    task_id,
                    on_finish={
                        "name": "nav",
                        "context": {
                            "type": "nav",
                            "path": "/system/knowledge/extractors/list",
                        },
                    },
                )
            )
            task_card_ids.append(task_card_id)

    flow = module_sdk.ui.Flow("knowledge_extractor_cards_flow", spacing=16)
    flow.set_children(card_ids)
    builder.add(flow)

    container = builder.get_component(container_id)
    if container is not None:
        container.set_children(["knowledge_extractor_cards_flow"])
    task_mount = builder.get_component(EXTRACTOR_INSTALL_TASK_MOUNT_ID)
    if task_mount is not None:
        task_mount.set_children(task_card_ids)


def extractor_mime_config_rows(module_sdk) -> list[dict[str, Any]]:
    return module_sdk.extractors.list_configurable_mime_bindings()


def extractor_mime_type_rows(
    module_sdk,
    *,
    extractor_id: str,
) -> list[dict[str, Any]]:
    normalized = str(extractor_id or "").strip().lower()
    for row in extractor_engine_rows(module_sdk):
        if str(row.get("extractor_id") or "").strip().lower() != normalized:
            continue
        return [
            {"mime_type": str(item)}
            for item in list(row.get("mime_type_items") or [])
            if str(item).strip()
        ]
    return []


def extractor_mime_type_table_model(module_sdk) -> list[dict[str, str]]:
    return [
        {
            "field": "mime_type",
            "label": _t(module_sdk, "system.knowledge.extractor_config.mime_type"),
        }
    ]


def extractor_mime_config_table_model(module_sdk) -> list[dict[str, Any]]:
    return [
        {
            "field": "mime_type",
            "label": _t(module_sdk, "system.knowledge.extractor_config.mime_type"),
        },
        {
            "field": "configured_extractor_id",
            "label": _t(module_sdk, "system.knowledge.extractor_config.extractor"),
            "type": "enum",
            "editable": True,
            "options_field": "extractor_options",
        },
    ]
