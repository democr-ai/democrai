from __future__ import annotations

from typing import Any

from democrai.core.runtime.foundation.app import app_ctx

EXTRACTION_TASK_KEY_PREFIX = "knowledge.extraction:"


def extraction_task_key(request_id: str) -> str:
    return f"{EXTRACTION_TASK_KEY_PREFIX}{request_id}"


def extraction_task_id_from_metadata(metadata: dict[str, Any] | None) -> str:
    return str(dict(metadata or {}).get("background_task_id") or "").strip()


def extraction_task_id(repository, request_id: str) -> str:
    metadata = repository.get_extraction_request_metadata(request_id)
    return extraction_task_id_from_metadata(metadata)


def create_extraction_task(
    *,
    request_id: str,
    filename: str,
    user_id: int,
    organization_id: int | None,
) -> str:
    manager = getattr(app_ctx(), "task_manager", None)
    if manager is None:
        return ""
    task_id, _created = manager.submit_external_sync(
        user_id=user_id,
        organization_id=organization_id,
        module="core",
        task_key=extraction_task_key(request_id),
        label=f"Preparing extraction: {filename}",
    )
    return task_id


def update_extraction_task(
    task_id: str,
    *,
    progress: float,
    label: str,
    checkpoint: dict[str, Any] | None = None,
) -> None:
    if not task_id:
        return
    manager = getattr(app_ctx(), "task_manager", None)
    if manager is None:
        return
    manager.update_progress_sync(
        task_id,
        progress=progress,
        label=label,
        checkpoint=checkpoint,
    )


def complete_extraction_task(task_id: str, *, result: dict[str, Any] | None = None) -> None:
    if not task_id:
        return
    manager = getattr(app_ctx(), "task_manager", None)
    if manager is None:
        return
    manager.complete_external_sync(task_id, result=result or {})


def fail_extraction_task(task_id: str, *, error: str) -> None:
    if not task_id:
        return
    manager = getattr(app_ctx(), "task_manager", None)
    if manager is None:
        return
    manager.fail_external_sync(task_id, error=error)
