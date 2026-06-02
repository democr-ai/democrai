from __future__ import annotations

from democrai.sdk.client import active_sdk as sdk
from democrai.sdk.system import to_optional_int
from democrai.sdk.ui import merge_builders

from modules.system.ui.layout import shared_layout
from modules.system.utils.actions.knowledge.extractors import (
    extractor_install_restore_task_key,
    run_extractor_install_restore_background,
)
from modules.system.utils.ui.knowledge.extractors import (
    ACTIVE_TASK_STATUSES,
    EXTRACTOR_INSTALL_TASK_MOUNT_ID,
    add_extractor_engine_cards,
    active_extractor_install_task_ids,
    extractor_engine_rows,
)


def _installing_event_id(extractor_id: str) -> str:
    rows = sdk.models.extractor_node_install_registry.list(
        page=0,
        page_size=20,
        filters={"extractor_id": extractor_id, "status": "installing"},
        sort={"field": "updated_at", "direction": "desc"},
    ).get("rows") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        event_id = str(row.get("last_event_id") or "").strip()
        if event_id:
            return event_id
    return ""


def _active_restore_task_id(
    *,
    extractor_id: str,
    extractor_row_id: int,
    event_id: str,
    organization_id: int | None,
) -> str:
    task_key = extractor_install_restore_task_key(
        extractor_id,
        extractor_row_id,
        event_id,
    )
    for task in sdk.tasks.get_tasks_by_key(task_key, organization_id):
        status = str(task.get("status") or "").strip().lower()
        if status not in ACTIVE_TASK_STATUSES:
            continue
        task_id = str(task.get("taskId") or task.get("id") or "").strip()
        if task_id:
            return task_id
    return ""


async def render(params: dict, session: dict):
    builder = sdk.ui.Builder()
    _, preview_id = await shared_layout(builder)

    page_builder = sdk.ui.load("utils/ui/yaml/knowledge/extractors/list")
    merge_builders(builder, page_builder)
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    organization_id = to_optional_int(user.get("organization_id"))

    add_extractor_engine_cards(
        sdk,
        builder,
        container_id="knowledge_extractor_cards_mount",
        organization_id=organization_id,
    )
    task_mount = builder.get_component(EXTRACTOR_INSTALL_TASK_MOUNT_ID)
    if task_mount is not None:
        task_mount.allow("children.append")

    for row in extractor_engine_rows(sdk):
        extractor_id = str(row.get("extractor_id") or "").strip().lower()
        registry_row_id = row.get("registry_row_id")
        status = str(row.get("status") or "").strip().lower()
        if not extractor_id or registry_row_id is None or status != "installing":
            continue
        if active_extractor_install_task_ids(
            sdk,
            extractor_id=extractor_id,
            extractor_row_id=int(registry_row_id),
            organization_id=organization_id,
        ):
            continue
        event_id = _installing_event_id(extractor_id)
        if not event_id or task_mount is None:
            continue
        task_id = _active_restore_task_id(
            extractor_id=extractor_id,
            extractor_row_id=int(registry_row_id),
            event_id=event_id,
            organization_id=organization_id,
        )
        if not task_id:
            task_ref = {"task_id": ""}
            task_id = await sdk.tasks.run_background(
                run_extractor_install_restore_background(
                    sdk,
                    task_ref=task_ref,
                    extractor_row_id=int(registry_row_id),
                    extractor_id=extractor_id,
                    event_id=event_id,
                ),
                label=sdk.i18n.t(
                    "system.knowledge.extractor_task.install_label",
                    context={"extractor_id": extractor_id},
                ),
                task_key=extractor_install_restore_task_key(
                    extractor_id,
                    int(registry_row_id),
                    event_id,
                ),
            )
            task_ref["task_id"] = task_id
        task_card_id = f"knowledge_extractor_install_task_{registry_row_id}_{task_id}"
        builder.add(
            sdk.ui.BackgroundTask(
                task_card_id,
                task_id=task_id,
                on_finish={
                    "name": "nav",
                    "context": {
                        "type": "nav",
                        "path": "/system/knowledge/extractors/list",
                    },
                },
            )
        )
        children = list(task_mount.children or [])
        children.append(task_card_id)
        task_mount.set_children(children)

    preview = builder.get_component(preview_id)
    if preview is not None:
        preview.set_children(
            [component.id for component in page_builder.get_roots() if component.id]
        )
        preview.set_property("padding", [28, 28, 28, 28])
        preview.set_property("spacing", 22)

    return builder
