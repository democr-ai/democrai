"""Classification projection helpers for the knowledge service."""

from __future__ import annotations

from typing import Any

from democrai.core.application.knowledge.repository import ClaimedOutboxJob


async def process_classification_job(service, job: ClaimedOutboxJob) -> None:
    """Classify one knowledge item and persist the derived result."""
    item = service.repository.get_item(job.payload["item_id"])
    if item is None or item.deleted_at is not None:
        return
    provider = getattr(service, "classification_provider", None)
    if provider is None:
        raise RuntimeError("No classification provider configured for knowledge")
    text = str(item.summary or item.content or "").strip()
    if not text:
        return
    results = provider.classify([text])
    if not results:
        return
    result = results[0]
    label = str(_result_value(result, "label") or "").strip()
    if not label:
        return
    score = _optional_float(_result_value(result, "score"))
    scores = _result_value(result, "scores")
    service.repository.upsert_item_classification(
        item_id=item.id,
        user_id=item.user_id,
        organization_id=item.organization_id or None,
        model_registry_id=provider.model_registry_id,
        model_version=provider.model_version,
        label=label,
        score=score,
        scores=scores if isinstance(scores, dict) else {},
    )
    service.repository.upsert_projection_state(
        aggregate_type="knowledge_item",
        aggregate_id=item.id,
        projection="classification",
        backend=provider.model_id,
        backend_key=f"{provider.model_id}:{item.id}",
        synced_version=item.version,
        status="synced",
    )


async def process_classification_delete_job(service, job: ClaimedOutboxJob) -> None:
    """Delete derived classifications for one item."""
    item_id = job.payload["item_id"]
    service.repository.delete_item_classifications(item_id=item_id)
    service.repository.upsert_projection_state(
        aggregate_type="knowledge_item",
        aggregate_id=item_id,
        projection="classification",
        backend="database",
        backend_key=f"classification:{item_id}",
        synced_version=job.aggregate_version,
        status="deleted",
    )


def _result_value(result: Any, key: str) -> Any:
    if isinstance(result, dict):
        return result.get(key)
    return getattr(result, key, None)


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
