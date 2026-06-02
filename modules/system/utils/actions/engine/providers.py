from __future__ import annotations

import asyncio
from contextlib import suppress

from collections.abc import Sequence
from typing import Any


_ENGINE_INSTALL_STREAM_ID = "system.engine.install.events"
_ENGINE_INSTALL_OUTPUT_EVENT_NAME = "engine.install.output"


def subscribe_engine_install_output(module_sdk):
    return module_sdk.events.subscribe_stream(_ENGINE_INSTALL_STREAM_ID)


def unsubscribe_engine_install_output(module_sdk, queue) -> None:
    module_sdk.events.unsubscribe_stream(_ENGINE_INSTALL_STREAM_ID, queue)


def drain_engine_install_output(queue, *, event_id: str) -> dict[str, Any] | None:
    latest: dict[str, Any] | None = None
    while True:
        try:
            payload = queue.get_nowait()
        except asyncio.QueueEmpty:
            break
        if not isinstance(payload, dict):
            continue
        if str(payload.get("event_name") or "").strip() != _ENGINE_INSTALL_OUTPUT_EVENT_NAME:
            continue
        if str(payload.get("event_id") or "").strip() != str(event_id or "").strip():
            continue
        latest = payload
    return latest


async def emit_engine_install_output_progress(
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


async def demo_background_job(
    sdk,
    *,
    task_ref: dict[str, str],
    event_id: str,
    provider: str,
) -> dict:
    # evita race: aspetta che task_id sia disponibile
    while not str(task_ref.get("task_id") or "").strip():
        await asyncio.sleep(0.05)

    task_id = str(task_ref["task_id"])
    await sdk.tasks.update_progress(
        task_id,
        0.10,
        label="Preparing engine installation",
    )

    deadline = asyncio.get_running_loop().time() + 600.0
    output_queue = subscribe_engine_install_output(sdk)
    last_status = ""
    last_live_emit = 0.0
    try:
        while True:
            now = asyncio.get_running_loop().time()
            latest_output = drain_engine_install_output(output_queue, event_id=event_id)
            if latest_output and now - last_live_emit >= 0.5:
                await emit_engine_install_output_progress(
                    sdk,
                    task_id=task_id,
                    progress=0.60,
                    payload=latest_output,
                )
                last_live_emit = now

            listing = sdk.models.engine_node_install_registry.list(
                page=0,
                page_size=20,
                filters={"engine_id": provider, "last_event_id": event_id},
                sort={"field": "updated_at", "direction": "desc"},
            )

            rows = listing.get("rows") or []
            row = rows[0] if rows else {}
            status = str(row.get("status") or "").strip().lower()
            last_error = str(row.get("last_error") or "").strip()

            if status == "installing":
                if status != last_status:
                    await sdk.tasks.update_progress(
                        task_id,
                        0.60,
                        label="Installing engine runtime",
                    )
            elif status == "installed":
                await sdk.tasks.update_progress(
                    task_id,
                    1.00,
                    label="Engine installed",
                )
                return {"status": "installed", "event_id": event_id}
            elif status == "error":
                raise RuntimeError(last_error or f"{provider} install failed")
            last_status = status

            if now >= deadline:
                raise TimeoutError(f"{provider} install timed out")

            await asyncio.sleep(0.25)
    finally:
        with suppress(Exception):
            unsubscribe_engine_install_output(sdk, output_queue)


def dependency_labels(dependencies: Sequence[dict[str, str]]) -> list[str]:
    labels: list[str] = []
    for dep in dependencies:
        label = str(dep.get("label") or dep.get("dependency_key") or "").strip()
        if label:
            labels.append(label)
    return labels
