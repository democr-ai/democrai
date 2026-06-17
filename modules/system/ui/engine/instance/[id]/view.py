from __future__ import annotations

from democrai.sdk.engines import list_provider_definitions, provider_requirements
from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.system import to_optional_int

from modules.system.ui.layout import shared_layout
from modules.system.utils.actions.engine.providers import demo_background_job
from modules.system.utils.ui.engine.available_models import load_available_items
from modules.system.utils.ui.engine.model_catalog import (
    ENGINE_CATALOG_PAGE_SIZE,
    load_engine_catalog_page,
)
from modules.system.utils.actions.engine.model_import import (
    provider_supports_inventory_import,
)
from modules.system.utils.actions.model.catalog import active_catalog_download_tasks
from modules.system.utils.actions.engine.quotas import (
    quota_limit_table_model,
)
from modules.system.utils.ui.engine.list import (
    provider_status_label,
    provider_status_variant,
)
from modules.system.utils.ui.engine.provider_page import capability_label
from modules.system.utils.ui.model.catalog import catalog_page_info
from democrai.sdk.ui import merge_builders


_ACTIVE_TASK_STATUSES = {"pending", "running", "waiting_confirmation"}


def _resolve_instance_id(params: dict) -> int | None:
    route_params = dict(params.get("route_params") or {})
    return int(route_params["id"]) if "id" in route_params else None


async def _install_status(engine_registry_id: int | None) -> dict:
    if engine_registry_id is None:
        return {}
    try:
        return await sdk.engines.install_status(engine_registry_id=int(engine_registry_id))
    except Exception:
        return {}


def _show_install_node(node: dict) -> bool:
    status = str(node.get("status") or "").strip().lower()
    event_id = str(node.get("last_event_id") or "").strip()
    last_error = str(node.get("last_error") or "").strip()
    return bool(event_id or last_error or status in {"installing", "installed", "error"})


def _installing_event_id(install_status: dict) -> str:
    nodes = install_status.get("nodes") if isinstance(install_status, dict) else []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        if str(node.get("status") or "").strip().lower() != "installing":
            continue
        event_id = str(node.get("last_event_id") or "").strip()
        if event_id:
            return event_id
    return ""


def _install_node_items(install_status: dict) -> list[dict]:
    nodes = install_status.get("nodes") if isinstance(install_status, dict) else []
    items: list[dict] = []
    for node in nodes if isinstance(nodes, list) else []:
        if not isinstance(node, dict):
            continue
        if not _show_install_node(node):
            continue
        node_id = str(node.get("node_id") or "").strip()
        status = str(node.get("status") or "").strip().lower()
        if not node_id:
            continue
        last_error = str(node.get("last_error") or "").strip()
        text = provider_status_label(sdk.i18n.t, status)
        if last_error:
            text = f"{text}: {last_error}"
        items.append({"title": node_id, "text": text})
    return items


def _install_summary_text(install_status: dict) -> str:
    summary = install_status.get("summary") if isinstance(install_status, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    installed = int(summary.get("installed") or 0)
    installing = int(summary.get("installing") or 0)
    pending = int(summary.get("pending") or 0)
    error = int(summary.get("error") or 0)
    total = installed + installing + pending + error
    return sdk.i18n.t(
        "system.engine.instance.page.install_nodes.summary",
        context={
            "installed": installed,
            "total": total,
            "installing": installing,
            "pending": pending,
            "error": error,
        },
    )


def _active_catalog_task_ids_for_items(catalog_items: list[dict]) -> list[tuple[str, str]]:
    catalog_ids = {
        str(item.get("id") or "").strip()
        for item in list(catalog_items or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    if not catalog_ids:
        return []
    active_tasks = active_catalog_download_tasks(sdk)
    resolved: list[tuple[str, str]] = []
    for catalog_id, task in active_tasks.items():
        if catalog_id not in catalog_ids:
            continue
        task_id = str(task.get("id") or task.get("task_id") or "").strip()
        if task_id:
            resolved.append((catalog_id, task_id))
    return resolved


def _instance_store_payload(
    engine: dict,
    provider_definition: dict | None,
    *,
    install_in_progress: bool = False,
) -> dict:
    provider = str(engine.get("provider") or "").strip().lower()
    description_key = str((provider_definition or {}).get("description_key") or "")
    description = str((provider_definition or {}).get("description") or "")
    if description_key:
        translated = sdk.i18n.t(description_key)
        if translated != description_key:
            description = translated
    provider_name = str(
        (provider_definition or {}).get("title")
        or (provider_definition or {}).get("label")
        or provider
    )
    status = str(engine.get("status") or "uninstalled").strip().lower()
    requirements = provider_requirements(provider_id=provider)
    capabilities = [
        str(item).strip()
        for item in ((provider_definition or {}).get("capabilities") or [])
        if str(item).strip()
    ]
    configurable = bool((provider_definition or {}).get("configurable"))
    supports_model_import = provider_supports_inventory_import(provider)
    provider_supported = bool(requirements.get("supported"))
    missing_dependencies = [
        item
        for item in list(requirements.get("missing_dependencies") or [])
        if isinstance(item, dict)
    ]
    can_retry_error = status == "error"
    can_install = (
        (status == "uninstalled" or can_retry_error)
        and not bool(install_in_progress)
        and (not configurable or bool(missing_dependencies))
        and provider_supported
    )
    return {
        "valid": True,
        "invalid": False,
        "id": int(engine["id"]),
        "name": str(engine.get("name") or provider_name),
        "provider": provider,
        "provider_name": provider_name,
        "description": description,
        "icon_url": str(
            (provider_definition or {}).get("icon_url")
            or "assets/engines/llamacpp.png"
        ),
        "status": status,
        "status_text": provider_status_label(sdk.i18n.t, status),
        "install_in_progress": bool(install_in_progress),
        "configurable": configurable,
        "provider_supported": provider_supported,
        "capabilities": capabilities,
        "models_visible": status == "active",
        "model_import_visible": status == "active" and supports_model_import,
        "import_local_file_path": f"/system/engine/instance/{int(engine['id'])}/model/import/local_file",
        "import_huggingface_path": f"/system/engine/instance/{int(engine['id'])}/model/import/huggingface",
        "can_install": can_install,
        "can_activate": status == "installed",
        "can_deactivate": status == "active",
        "can_edit": True,
    }


def _instance_actions(payload: dict) -> list[dict]:
    engine_id = payload.get("id")
    provider = str(payload.get("provider") or "")
    actions: list[dict] = []

    if bool(payload.get("can_install")):
        actions.append(
            {
                "label": sdk.i18n.t("system.engine.instance.page.action.install"),
                "icon": "ric.download-cloud-2-line",
                "variant": "primary",
                "action": {
                    "name": "system.install_engine_from_instance_overview",
                    "context": {"engine_id": engine_id, "provider": provider},
                },
            }
        )
    if bool(payload.get("can_activate")):
        actions.append(
            {
                "label": sdk.i18n.t("system.engine.instance.page.action.activate"),
                "icon": "ric.play-circle-line",
                "variant": "primary",
                "action": {
                    "name": "system.activate_engine_instance",
                    "context": {"engine_id": engine_id, "provider": provider},
                },
            }
        )
    if bool(payload.get("can_deactivate")):
        actions.append(
            {
                "label": sdk.i18n.t("system.engine.instance.page.action.deactivate"),
                "icon": "ric.pause-circle-line",
                "variant": "secondary",
                "action": {
                    "name": "system.deactivate_engine",
                    "context": {"engine_id": engine_id, "provider": provider},
                },
            }
        )
    if bool(payload.get("can_edit")):
        actions.append(
            {
                "label": sdk.i18n.t("system.engine.provider.page.action.edit"),
                "icon": "ric.edit-line",
                "variant": "secondary",
                "action": {
                    "name": "open_drawer",
                    "context": {
                        "path": (
                            f"/system/engine/provider/config/{provider}"
                            f"?engine_id={engine_id}"
                        ),
                        "position": "right",
                        "dim": 620,
                    },
                },
            }
        )
    return actions


def _active_install_task_id(provider: str, instance_id: int, session: dict) -> str:
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    organization_id = to_optional_int(user.get("organization_id"))
    task_key = f"system.engine.install.{provider}.{instance_id}"
    for task in sdk.tasks.get_tasks_by_key(task_key, organization_id):
        status = str(task.get("status") or "").strip().lower()
        if status not in _ACTIVE_TASK_STATUSES:
            continue
        task_id = str(task.get("id") or "").strip()
        if task_id:
            return task_id
    return ""


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)
    merge_builders(builder, sdk.ui.load("utils/ui/yaml/engine/instance_overview"))
    merge_builders(builder, sdk.ui.load("utils/ui/yaml/engine/quota_limits"))

    instance_id = _resolve_instance_id(params)
    engine = None
    if instance_id is not None:
        try:
            engine = sdk.models.engine_registry.view(instance_id)
        except Exception:
            engine = None

    card = builder.get_component("engine_instance_overview_card")
    if isinstance(engine, dict):
        provider = str(engine.get("provider") or "").strip().lower()
        provider_definition = next(
            (
                item
                for item in (list_provider_definitions() or [])
                if str(item.get("id") or "").strip().lower() == provider
            ),
            None,
        )
        install_status = await _install_status(instance_id)
        payload = _instance_store_payload(
            engine,
            provider_definition,
            install_in_progress=(
                str(engine.get("status") or "").strip().lower() == "installing"
            ),
        )
        payload["install_nodes"] = _install_node_items(install_status)
        payload["install_status_visible"] = bool(payload["install_nodes"])
        payload["install_summary_text"] = _install_summary_text(install_status)
        builder.set_store("/instance", payload)
        builder.set_store(
            "/engine_quota_limits/create_path",
            f"/system/engine_quota/limit/global/{int(instance_id)}/create",
            scope="page",
        )
        builder.set_store("/engine_quota_limits/visible", True, scope="page")
        quota_table = builder.get_component("engine_quota_limits_table")
        if quota_table is not None:
            quota_table.set_property("model", quota_limit_table_model(sdk))
            quota_table.set_property(
                "remote_service",
                {
                    "name": "system.list_engine_quota_limits",
                    "context": {"scope": "global", "subject_id": int(instance_id)},
                },
            )
        if card is not None:
            card.set_property("itemActions", _instance_actions(payload))
        breadcrumb = builder.get_component("engine_instance_overview_breadcrumb")
        if breadcrumb is not None:
            segments = [
                {
                    "label": sdk.i18n.t("system.engine.list.title"),
                    "path": "/system/engine/list",
                }
            ]
            if bool((provider_definition or {}).get("configurable")):
                segments.append(
                    {
                        "label": str(payload.get("provider_name") or provider),
                        "path": f"/system/engine/provider/{provider}",
                    }
                )
            segments.append(
                {
                    "label": str(payload.get("name") or provider),
                    "current": True,
                }
            )
            breadcrumb.set_property("segments", segments)
        icon = builder.get_component("engine_instance_overview_icon")
        if icon is not None:
            icon.set_property("url", payload.get("icon_url"))
        status_badge_id = "engine_instance_overview_status_badge"
        builder.add(
            sdk.ui.Badge(
                status_badge_id,
                str(payload.get("status_text") or ""),
                variant=provider_status_variant(str(payload.get("status") or "")),
            )
        )
        status_row = builder.get_component("engine_instance_overview_status_row")
        if status_row is not None:
            status_row.set_children([status_badge_id])
        capability_ids: list[str] = []
        for index, capability in enumerate(payload.get("capabilities") or []):
            label = capability_label(sdk.i18n.t, str(capability))
            if not label:
                continue
            badge_id = f"engine_instance_overview_capability_{index}"
            builder.add(sdk.ui.Badge(badge_id, label, variant="secondary"))
            capability_ids.append(badge_id)
        capabilities = builder.get_component("engine_instance_overview_capabilities")
        if capabilities is not None:
            capabilities.set_children(capability_ids)

        task_mount = builder.get_component("engine_instance_overview_task_mount_col")
        if task_mount is not None:
            task_mount.allow("children.append")

        if payload.get("status") == "installing":
            event_id = _installing_event_id(install_status)
            if event_id and task_mount is not None:
                task_id = _active_install_task_id(provider, int(instance_id), session)
                if not task_id:
                    task_ref = {"task_id": ""}
                    task_id = await sdk.tasks.run_background(
                        demo_background_job(
                            sdk,
                            task_ref=task_ref,
                            event_id=event_id,
                            provider=provider,
                        ),
                        label=sdk.i18n.t(
                            "system.engine.install.task.label",
                            context={
                                "provider": str(payload.get("provider_name") or provider)
                            },
                        ),
                        task_key=(
                            "system.engine.install.restore."
                            f"{provider}.{instance_id}.{event_id}"
                        ),
                    )
                    task_ref["task_id"] = task_id

                task_card_id = f"engine_instance_install_task_{instance_id}_{task_id}"
                builder.add(
                    sdk.ui.BackgroundTask(
                        task_card_id,
                        task_id=task_id,
                        on_finish={
                            "name": "nav",
                            "context": {
                                "type": "nav",
                                "path": f"/system/engine/instance/{instance_id}/view",
                            },
                        },
                    )
                )
                children = list(task_mount.children or [])
                children.append(task_card_id)
                task_mount.set_children(children)
        if payload.get("status") == "active":
            catalog_page_data = await load_engine_catalog_page(
                sdk,
                provider,
                engine_id=int(instance_id),
                page_size=ENGINE_CATALOG_PAGE_SIZE,
            )
            has_downloadable_catalog = int(catalog_page_data.get("total") or 0) > 0
            if has_downloadable_catalog:
                merge_builders(builder, sdk.ui.load("utils/ui/yaml/engine/model_catalog_tabs"))
            merge_builders(builder, sdk.ui.load("utils/ui/yaml/engine/models_available"))
            route_content = builder.get_component("engine_instance_models_route_content")
            if route_content is not None:
                route_content.set_children(
                    ["engine_models_tabs_root"]
                    if has_downloadable_catalog
                    else ["engine_models_tab_available"]
                )
            available_mount = builder.get_component("engine_models_available_tab_mount")
            if available_mount is not None:
                available_mount.set_children(["engine_models_tab_available"])
            model_task_mount = builder.get_component("engine_instance_models_task_mount_col")
            if model_task_mount is not None:
                model_task_mount.allow("children.append")
            try:
                available_items = await load_available_items(sdk, int(instance_id))
                available_error = ""
            except Exception as exc:
                available_items = []
                available_error = str(exc)
            builder.set_store("/engine_models_available/all", available_items, scope="page")
            builder.set_store(
                "/engine_models_available/filtered",
                available_items,
                scope="page",
            )
            builder.set_store("/engine_models_available/error", available_error, scope="page")
            builder.set_store("/engine_models_available/filters/name", "", scope="page")
            builder.set_store(
                "/engine_models_available/filters/capability",
                "",
                scope="page",
            )
            builder.set_store("/engine_models_available/loading", False, scope="page")
            if has_downloadable_catalog:
                builder.set_store(
                    "/engine_model_catalog/show_pagination",
                    int(catalog_page_data.get("total") or 0)
                    > int(catalog_page_data.get("page_size") or ENGINE_CATALOG_PAGE_SIZE),
                    scope="page",
                )
                builder.set_store(
                    "/engine_model_catalog/items",
                    list(catalog_page_data.get("items") or []),
                    scope="page",
                )
                builder.set_store(
                    "/engine_model_catalog/visible_items",
                    list(catalog_page_data.get("items") or []),
                    scope="page",
                )
                task_card_ids: list[str] = []
                for catalog_id, task_id in _active_catalog_task_ids_for_items(
                    list(catalog_page_data.get("items") or [])
                ):
                    task_card_id = f"engine_model_catalog_download_{catalog_id}_{task_id}"
                    builder.add(
                        sdk.ui.BackgroundTask(
                            task_card_id,
                            task_id=task_id,
                            on_finish={
                                "name": "system.filter_engine_model_catalog",
                                "context": {
                                    "provider": provider,
                                    "engine_id": int(instance_id),
                                    "page": 0,
                                    "page_size": ENGINE_CATALOG_PAGE_SIZE,
                                },
                            },
                        )
                    )
                    task_card_ids.append(task_card_id)
                if model_task_mount is not None and task_card_ids:
                    model_task_mount.set_children(task_card_ids)
                catalog_info = builder.get_component("engine_model_catalog_page_info")
                if catalog_info is not None:
                    catalog_info.set_property(
                        "text",
                        catalog_page_info(
                            sdk,
                            page=int(catalog_page_data.get("page") or 0),
                            page_size=int(
                                catalog_page_data.get("page_size")
                                or ENGINE_CATALOG_PAGE_SIZE
                            ),
                            total=int(catalog_page_data.get("total") or 0),
                        ),
                    )
    else:
        builder.set_store(
            "/instance",
            {
                "id": 0,
                "valid": False,
                "invalid": True,
                "name": "",
                "provider": "",
                "provider_name": "",
                "icon_url": "assets/engines/llamacpp.png",
                "status": "",
                "status_text": "",
                "description": "",
                "configurable": False,
                "provider_supported": False,
                "capabilities": [],
                "models_visible": False,
            },
        )

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(["engine_instance_overview_page"])
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
