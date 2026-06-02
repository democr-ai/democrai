from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from democrai.sdk.system import to_optional_int


_EXTRACTOR_TASK_MOUNT_ID = "knowledge_extractor_install_task_mount"
_EXTRACTOR_INSTALL_STREAM_ID = "system.extractor.install.events"
_EXTRACTOR_INSTALL_OUTPUT_EVENT_NAME = "extractor.install.output"


def _t(module_sdk, key: str, context: dict[str, Any] | None = None) -> str:
    return module_sdk.i18n.t(key, context=context or {})


def extractor_install_task_key(extractor_id: str, extractor_row_id: int) -> str:
    return f"system.extractor.install.{extractor_id}.{int(extractor_row_id)}"


def extractor_install_restore_task_key(
    extractor_id: str,
    extractor_row_id: int,
    event_id: str,
) -> str:
    return (
        "system.extractor.install.restore."
        f"{extractor_id}.{int(extractor_row_id)}.{event_id}"
    )


def subscribe_extractor_install_output(module_sdk):
    return module_sdk.events.subscribe_stream(_EXTRACTOR_INSTALL_STREAM_ID)


def unsubscribe_extractor_install_output(module_sdk, queue) -> None:
    module_sdk.events.unsubscribe_stream(_EXTRACTOR_INSTALL_STREAM_ID, queue)


def drain_extractor_install_output(
    queue,
    *,
    event_id: str,
) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    while True:
        try:
            payload = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if not isinstance(payload, dict):
            continue
        if str(payload.get("event_name") or "").strip() != _EXTRACTOR_INSTALL_OUTPUT_EVENT_NAME:
            continue
        if str(payload.get("event_id") or "").strip() != str(event_id or "").strip():
            continue
        latest = payload
    return latest


async def emit_extractor_install_output_progress(
    module_sdk,
    *,
    task_id: str,
    progress: float,
    payload: dict[str, Any] | None,
) -> None:
    if not payload:
        return
    line = str(payload.get("line") or "").strip()
    if not line:
        return
    phase = str(payload.get("phase") or "").strip()
    label = f"{phase}: {line}" if phase else line
    await module_sdk.tasks.emit_progress(task_id, progress, label=label)


async def run_extractor_install_restore_background(
    module_sdk,
    *,
    task_ref: dict[str, str],
    extractor_row_id: int,
    extractor_id: str,
    event_id: str,
) -> dict[str, Any]:
    while not str(task_ref.get("task_id") or "").strip():
        await asyncio.sleep(0.05)

    task_id = str(task_ref["task_id"])
    await module_sdk.tasks.update_progress(
        task_id,
        0.10,
        label=_t(module_sdk, "system.knowledge.extractor_task.preparing_install"),
    )

    deadline = asyncio.get_running_loop().time() + 1800.0
    output_queue = subscribe_extractor_install_output(module_sdk)
    last_status = ""
    last_live_emit = 0.0
    try:
        while True:
            now = asyncio.get_running_loop().time()
            latest_output = drain_extractor_install_output(
                output_queue,
                event_id=event_id,
            )
            if latest_output and now - last_live_emit >= 0.5:
                await emit_extractor_install_output_progress(
                    module_sdk,
                    task_id=task_id,
                    progress=0.60,
                    payload=latest_output,
                )
                last_live_emit = now

            listing = module_sdk.models.extractor_node_install_registry.list(
                page=0,
                page_size=20,
                filters={"extractor_id": extractor_id, "last_event_id": event_id},
                sort={"field": "updated_at", "direction": "desc"},
            )
            rows = listing.get("rows") or []
            row = rows[0] if rows else {}
            status = str(row.get("status") or "").strip().lower()
            last_error = str(row.get("last_error") or "").strip()

            if status == "installing":
                if status != last_status:
                    await module_sdk.tasks.update_progress(
                        task_id,
                        0.60,
                        label=_t(
                            module_sdk,
                            "system.knowledge.extractor_task.installing_runtime",
                        ),
                    )
            elif status == "installed":
                module_sdk.models.extractor_registry.update(
                    extractor_row_id,
                    {"status": "installed", "supported": True},
                )
                await module_sdk.tasks.update_progress(
                    task_id,
                    1.0,
                    label=_t(module_sdk, "system.knowledge.extractor_task.installed"),
                )
                return {"status": "installed", "event_id": event_id}
            elif status == "error":
                raise RuntimeError(last_error or f"{extractor_id} install failed")
            last_status = status

            if now >= deadline:
                raise TimeoutError(f"{extractor_id} install timed out")
            await asyncio.sleep(0.25)
    finally:
        with suppress(Exception):
            unsubscribe_extractor_install_output(module_sdk, output_queue)
_EXTRACTOR_TEST_TASK_MOUNT_ID = "knowledge_extractor_test_task_mount"


def extractor_install_in_progress(module_sdk, extractor_id: str) -> bool:
    normalized = str(extractor_id or "").strip().lower()
    if not normalized:
        return False
    rows = module_sdk.models.extractor_node_install_registry.list(
        page=0,
        page_size=1,
        filters={"extractor_id": normalized, "status": "installing"},
        sort={"field": "updated_at", "direction": "desc"},
    ).get("rows") or []
    return bool(rows)


async def run_extractor_install_background(
    module_sdk,
    *,
    task_ref: dict[str, str],
    extractor_row_id: int,
    extractor_id: str,
    requested_by: dict[str, Any],
) -> dict[str, Any]:
    while not str(task_ref.get("task_id") or "").strip():
        await asyncio.sleep(0.05)

    task_id = str(task_ref.get("task_id") or "").strip()
    await module_sdk.tasks.update_progress(
        task_id,
        0.10,
        label=_t(module_sdk, "system.knowledge.extractor_task.preparing_install"),
    )
    try:
        install_event = await module_sdk.extractors.request_install(
            extractor_id=extractor_id,
            force=False,
            install_config=dict(
                (
                    module_sdk.models.extractor_registry.view(extractor_row_id)
                    or {}
                ).get("install_config")
                or {}
            ),
            requested_by=requested_by,
            task_id=task_id,
        )
        event_id = str((install_event or {}).get("event_id") or "").strip()
        await module_sdk.tasks.update_progress(
            task_id,
            0.20,
            label=_t(
                module_sdk,
                "system.knowledge.extractor_task.installing_dependencies",
            ),
        )

        deadline = asyncio.get_running_loop().time() + 1800.0
        last_status = ""
        while True:
            now = asyncio.get_running_loop().time()
            listing = module_sdk.models.extractor_node_install_registry.list(
                page=0,
                page_size=20,
                filters={
                    "extractor_id": extractor_id,
                    **({"last_event_id": event_id} if event_id else {}),
                },
                sort={"field": "updated_at", "direction": "desc"},
            )
            rows = listing.get("rows") or []
            node_row = rows[0] if rows else {}
            status = str(node_row.get("status") or "").strip().lower()
            last_error = str(node_row.get("last_error") or "").strip()

            if status == "installing" and status != last_status:
                await module_sdk.tasks.update_progress(
                    task_id,
                    0.60,
                    label=_t(
                        module_sdk,
                        "system.knowledge.extractor_task.installing_runtime",
                    ),
                )
            elif status == "installed":
                module_sdk.models.extractor_registry.update(
                    extractor_row_id,
                    {"status": "installed", "supported": True},
                )
                await module_sdk.tasks.update_progress(
                    task_id,
                    1.0,
                    label=_t(module_sdk, "system.knowledge.extractor_task.installed"),
                )
                return {
                    "extractor_id": extractor_id,
                    "extractor_row_id": extractor_row_id,
                    "status": "installed",
                }
            elif status == "error":
                raise RuntimeError(last_error or f"{extractor_id} install failed")

            last_status = status
            if now >= deadline:
                raise TimeoutError(f"{extractor_id} install timed out")
            await asyncio.sleep(0.5)
    except Exception:
        with suppress(Exception):
            module_sdk.models.extractor_registry.update(
                extractor_row_id,
                {"status": "error", "supported": False},
            )
        raise


async def start_extractor_install_task(
    module_sdk,
    *,
    extractor_row_id: int,
    extractor_id: str,
    session: dict[str, Any],
) -> list[dict[str, Any]]:
    task_ref = {"task_id": ""}
    user = session.get("user") if isinstance(session.get("user"), dict) else {}
    requested_by = {
        "user_id": to_optional_int(user.get("id")),
        "organization_id": to_optional_int(user.get("organization_id")),
    }
    task_id = await module_sdk.tasks.run_background(
        run_extractor_install_background(
            module_sdk,
            task_ref=task_ref,
            extractor_row_id=extractor_row_id,
            extractor_id=extractor_id,
            requested_by=requested_by,
        ),
        label=_t(
            module_sdk,
            "system.knowledge.extractor_task.install_label",
            {"extractor_id": extractor_id},
        ),
        task_key=extractor_install_task_key(extractor_id, extractor_row_id),
    )
    task_ref["task_id"] = task_id
    card = module_sdk.ui.BackgroundTask(
        f"knowledge_extractor_install_task_{extractor_row_id}_{task_id}",
        task_id,
        on_finish={
            "name": "nav",
            "context": {
                "type": "nav",
                "path": "/system/knowledge/extractors/list",
            },
        },
    )
    return [
        module_sdk.effects.ui_collection_append(
            _EXTRACTOR_TASK_MOUNT_ID,
            "children",
            card.to_dict(),
        )
    ]


def format_extraction_test_result(
    module_sdk,
    *,
    upload: dict[str, Any],
    payload: dict[str, Any],
) -> str:
    filename = str(upload.get("name") or upload.get("filename") or "").strip()
    mime_type = str(
        upload.get("mime") or upload.get("type") or upload.get("content_type") or ""
    ).strip()
    resolved = payload.get("resolved_extractor")
    resolved_extractor = ""
    if isinstance(resolved, dict):
        resolved_extractor = str(resolved.get("extractor_id") or "").strip()

    markdown = str(payload.get("markdown_content") or "").strip()
    chunks = list(payload.get("chunks") or [])
    tables = list(payload.get("tables") or [])
    images = list(payload.get("images") or [])
    preview = markdown[:4000]
    if len(markdown) > len(preview):
        preview = f"{preview}\n\n..."

    lines = [
        f"### {_t(module_sdk, 'system.knowledge.extractor_test.result_title')}",
        "",
        f"- {_t(module_sdk, 'system.knowledge.extractor_test.file')}: "
        f"`{filename or _t(module_sdk, 'system.knowledge.extractor_test.uploaded_document')}`",
        f"- {_t(module_sdk, 'system.knowledge.extractor_config.mime_type')}: "
        f"`{mime_type or _t(module_sdk, 'system.knowledge.extractor_test.unknown')}`",
        f"- {_t(module_sdk, 'system.knowledge.extractor_config.extractor')}: "
        f"`{resolved_extractor or str(payload.get('extractor_id') or _t(module_sdk, 'system.knowledge.extractor_test.unknown'))}`",
        f"- {_t(module_sdk, 'system.knowledge.extractor_test.markdown_chars')}: `{len(markdown)}`",
        f"- {_t(module_sdk, 'system.knowledge.extractor_test.chunks')}: `{len(chunks)}`",
        f"- {_t(module_sdk, 'system.knowledge.extractor_test.tables')}: `{len(tables)}`",
        f"- {_t(module_sdk, 'system.knowledge.extractor_test.images')}: `{len(images)}`",
        "",
        f"#### {_t(module_sdk, 'system.knowledge.extractor_test.markdown_preview')}",
        "",
    ]
    lines.append(
        preview
        or f"_{_t(module_sdk, 'system.knowledge.extractor_test.no_markdown')}_"
    )
    return "\n".join(lines)


async def run_extractor_test_background(
    module_sdk,
    *,
    task_ref: dict[str, str],
    extractor_id: str,
    upload: dict[str, Any],
    storage_path: str,
    filename: str,
    mime_type: str,
) -> dict[str, Any]:
    while not str(task_ref.get("task_id") or "").strip():
        await asyncio.sleep(0.05)

    task_id = str(task_ref.get("task_id") or "").strip()
    await module_sdk.tasks.update_progress(
        task_id,
        0.10,
        label=_t(module_sdk, "system.knowledge.extractor_task.loading_document"),
    )

    def _run_extract() -> dict[str, Any] | None:
        return module_sdk.extractors.extract_with_registered(
            extractor_id=extractor_id,
            path=storage_path,
            filename=filename,
            mime_type=mime_type,
        )

    await module_sdk.tasks.update_progress(
        task_id,
        0.25,
        label=_t(module_sdk, "system.knowledge.extractor_task.running_runtime"),
    )
    payload = await asyncio.to_thread(_run_extract)
    if payload is None:
        raise RuntimeError(
            _t(module_sdk, "system.knowledge.extractor_task.no_extractor")
        )
    normalized_extractor_id = str(extractor_id or "").strip().lower()

    result_markdown = format_extraction_test_result(
        module_sdk,
        upload=upload,
        payload=payload,
    )
    await module_sdk.tasks.update_progress(
        task_id,
        1.0,
        label=_t(module_sdk, "system.knowledge.extractor_task.test_completed"),
    )
    return {
        "extractor_id": normalized_extractor_id,
        "result_markdown": result_markdown,
    }


async def start_extractor_test_task(
    module_sdk,
    *,
    extractor_id: str,
    upload: dict[str, Any],
    storage_path: str,
    filename: str,
    mime_type: str,
) -> list[dict[str, Any]]:
    task_ref = {"task_id": ""}
    normalized_extractor_id = str(extractor_id or "").strip().lower()
    task_id = await module_sdk.tasks.run_background(
        run_extractor_test_background(
            module_sdk,
            task_ref=task_ref,
            extractor_id=normalized_extractor_id,
            upload=upload,
            storage_path=storage_path,
            filename=filename,
            mime_type=mime_type,
        ),
        label=_t(
            module_sdk,
            "system.knowledge.extractor_task.test_label",
            {"extractor_id": normalized_extractor_id},
        ),
        task_key=f"system.extractor.test.{normalized_extractor_id}",
    )
    task_ref["task_id"] = task_id
    card = module_sdk.ui.BackgroundTask(
        f"knowledge_extractor_test_task_{normalized_extractor_id}_{task_id}",
        task_id,
        on_completed={
            "name": "system.show_extractor_test_result",
            "context": {"extractor_id": normalized_extractor_id},
        },
        on_error={
            "name": "system.show_extractor_test_error",
            "context": {"extractor_id": normalized_extractor_id},
        },
    )
    return [
        module_sdk.effects.ui_collection_append(
            _EXTRACTOR_TEST_TASK_MOUNT_ID,
            "children",
            card.to_dict(),
        )
    ]
