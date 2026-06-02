"""Ingestion and outbox orchestration helpers for the knowledge service.

The functions in this module implement the write-side workflow: persist sources
and items, normalize metadata, store the canonical relational graph, and enqueue
vector/KG projection jobs.
"""

from __future__ import annotations

from uuid import uuid4

from democrai.core.application.knowledge.models import KnowledgeIngestRequest
from democrai.core.application.knowledge.models import KnowledgeIngestResult
from democrai.core.application.knowledge.models import KnowledgeRebuildResult
from democrai.core.application.knowledge.service_helper.metadata import enrich_ingest_item
from democrai.core.runtime.foundation.app import request_context_scope


def ingest(service, request: KnowledgeIngestRequest) -> KnowledgeIngestResult:
    """Persist a source and all of its items, then enqueue projections."""
    owner_access_level = service._resolve_access_level(request.user_id)
    source = service.repository.upsert_source(
        user_id=request.user_id,
        organization_id=request.organization_id,
        owner_access_level=owner_access_level,
        source=request.source,
    )
    item_ids: list[str] = []
    outbox_ids: list[str] = []
    for item in request.items:
        enriched_item = enrich_ingest_item(source=request.source, item=item)
        item_row = service.repository.upsert_item(
            source_id=source.id,
            user_id=request.user_id,
            organization_id=request.organization_id,
            owner_access_level=owner_access_level,
            item=enriched_item,
            embedding_model_id=getattr(service.embedding_provider, "model_id", None),
            embedding_model_version=getattr(
                service.embedding_provider, "model_version", None
            ),
            embedding_dim=getattr(service.embedding_provider, "dim", None),
        )
        service.repository.replace_entities_and_relations(
            item_id=item_row.id,
            user_id=request.user_id,
            organization_id=request.organization_id,
            item=enriched_item,
        )
        item_ids.append(item_row.id)

        vector_job = service.repository.enqueue_projection_job(
            topic="knowledge.vector_upsert",
            aggregate_type="knowledge_item",
            aggregate_id=item_row.id,
            aggregate_version=item_row.version,
            payload={"item_id": item_row.id},
        )
        kg_job = service.repository.enqueue_projection_job(
            topic="knowledge.kg_upsert",
            aggregate_type="knowledge_item",
            aggregate_id=item_row.id,
            aggregate_version=item_row.version,
            payload={"item_id": item_row.id, "source_id": source.id},
        )
        outbox_ids.extend([vector_job.id, kg_job.id])
        if getattr(service, "classification_provider", None) is not None:
            classification_job = service.repository.enqueue_projection_job(
                topic="knowledge.classification_upsert",
                aggregate_type="knowledge_item",
                aggregate_id=item_row.id,
                aggregate_version=item_row.version,
                payload={"item_id": item_row.id},
            )
            outbox_ids.append(classification_job.id)

    return KnowledgeIngestResult(
        source_id=source.id,
        item_ids=tuple(item_ids),
        outbox_ids=tuple(outbox_ids),
    )


def delete_source(
    service,
    *,
    user_id: int,
    organization_id: int | None,
    source_id: str,
) -> tuple[str, ...]:
    """Soft-delete a source and enqueue downstream projection deletions."""
    deleted_source_id, items = service.repository.soft_delete_source(
        source_id=source_id,
        user_id=user_id,
        organization_id=organization_id,
    )
    if deleted_source_id is None:
        return ()
    outbox_ids: list[str] = []
    for item_id, item_version in items:
        vector_job = service.repository.enqueue_projection_job(
            topic="knowledge.vector_delete",
            aggregate_type="knowledge_item",
            aggregate_id=item_id,
            aggregate_version=item_version,
            payload={"item_id": item_id},
        )
        kg_job = service.repository.enqueue_projection_job(
            topic="knowledge.kg_delete",
            aggregate_type="knowledge_item",
            aggregate_id=item_id,
            aggregate_version=item_version,
            payload={"item_id": item_id, "source_id": deleted_source_id},
        )
        classification_job = service.repository.enqueue_projection_job(
            topic="knowledge.classification_delete",
            aggregate_type="knowledge_item",
            aggregate_id=item_id,
            aggregate_version=item_version,
            payload={"item_id": item_id},
        )
        outbox_ids.extend([vector_job.id, kg_job.id, classification_job.id])
    return tuple(outbox_ids)


def _delete_payload(payload: dict, *, force: bool) -> dict:
    if not force:
        return payload
    return {**payload, "force": True}


def _enqueue_delete_jobs(repository, deleted_items, *, force: bool = False) -> tuple[str, ...]:
    outbox_ids: list[str] = []
    for item in deleted_items:
        item_id = item["item_id"]
        item_version = item["item_version"]
        source_id = item["source_id"]
        vector_job = repository.enqueue_projection_job(
            topic="knowledge.vector_delete",
            aggregate_type="knowledge_item",
            aggregate_id=item_id,
            aggregate_version=item_version,
            payload=_delete_payload({"item_id": item_id}, force=force),
        )
        kg_job = repository.enqueue_projection_job(
            topic="knowledge.kg_delete",
            aggregate_type="knowledge_item",
            aggregate_id=item_id,
            aggregate_version=item_version,
            payload=_delete_payload(
                {"item_id": item_id, "source_id": source_id},
                force=force,
            ),
        )
        classification_job = repository.enqueue_projection_job(
            topic="knowledge.classification_delete",
            aggregate_type="knowledge_item",
            aggregate_id=item_id,
            aggregate_version=item_version,
            payload=_delete_payload({"item_id": item_id}, force=force),
        )
        outbox_ids.extend([vector_job.id, kg_job.id, classification_job.id])
    return tuple(outbox_ids)


def delete_by_metadata_with_repository(
    repository,
    *,
    user_id: int,
    organization_id: int | None,
    metadata_filters: dict,
    force: bool = False,
) -> dict:
    """Delete repository records by metadata and queue projection deletions."""
    result = repository.delete_by_metadata(
        user_id=user_id,
        organization_id=organization_id,
        metadata_filters=metadata_filters,
        force=force,
    )
    outbox_ids = _enqueue_delete_jobs(
        repository,
        result["deleted_items"],
        force=force,
    )
    return {**result, "outbox_ids": outbox_ids, "force": bool(force)}


def delete_by_metadata(
    service,
    *,
    user_id: int,
    organization_id: int | None,
    metadata_filters: dict,
    force: bool = False,
) -> dict:
    """Delete owned knowledge records by metadata and queue projection deletions."""
    return delete_by_metadata_with_repository(
        service.repository,
        user_id=user_id,
        organization_id=organization_id,
        metadata_filters=metadata_filters,
        force=force,
    )


def rebuild_source(
    service,
    *,
    user_id: int,
    organization_id: int | None,
    source_id: str,
) -> tuple[str, ...]:
    """Enqueue fresh vector and KG upserts for every item in a source."""
    source = service.repository.get_source(source_id)
    if source is None or source.deleted_at is not None:
        return ()
    if not service.repository._is_owned_by(
        source,
        user_id=user_id,
        organization_id=organization_id,
    ):
        return ()
    return _enqueue_rebuild_for_source(service, source)


def _enqueue_rebuild_for_source(service, source) -> tuple[str, ...]:
    """Enqueue rebuild jobs for an existing canonical source."""
    outbox_ids: list[str] = []
    for item in service.repository.list_items_for_source(
        source_id=source.id,
        include_deleted=False,
    ):
        rebuild_key = f"rebuild:{uuid4().hex}"
        vector_job = service.repository.enqueue_projection_job(
            topic="knowledge.vector_upsert",
            aggregate_type="knowledge_item",
            aggregate_id=item.id,
            aggregate_version=item.version,
            payload={"item_id": item.id},
            dedupe_suffix=rebuild_key,
        )
        kg_job = service.repository.enqueue_projection_job(
            topic="knowledge.kg_upsert",
            aggregate_type="knowledge_item",
            aggregate_id=item.id,
            aggregate_version=item.version,
            payload={"item_id": item.id, "source_id": source.id},
            dedupe_suffix=rebuild_key,
        )
        outbox_ids.extend([vector_job.id, kg_job.id])
        if getattr(service, "classification_provider", None) is not None:
            classification_job = service.repository.enqueue_projection_job(
                topic="knowledge.classification_upsert",
                aggregate_type="knowledge_item",
                aggregate_id=item.id,
                aggregate_version=item.version,
                payload={"item_id": item.id},
                dedupe_suffix=rebuild_key,
            )
            outbox_ids.append(classification_job.id)
    return tuple(outbox_ids)


def admin_rebuild_sources(
    service,
    *,
    source_id: str | None = None,
    user_id: int | None = None,
    organization_id: int | None = None,
    source_type: str | None = None,
    limit: int | None = None,
) -> tuple[KnowledgeRebuildResult, ...]:
    """Administrative helper that schedules rebuilds for multiple sources."""
    results: list[KnowledgeRebuildResult] = []
    for source in service.repository.list_sources(
        include_deleted=False,
        source_id=source_id,
        user_id=user_id,
        organization_id=organization_id,
        source_type=source_type,
        limit=limit,
    ):
        normalized_org_id = source.organization_id or None
        outbox_ids = _enqueue_rebuild_for_source(service, source)
        results.append(
            KnowledgeRebuildResult(
                source_id=source.id,
                user_id=source.user_id,
                organization_id=normalized_org_id,
                source_type=source.source_type,
                outbox_ids=outbox_ids,
            )
        )
    return tuple(results)


async def process_outbox_once(
    service,
    *,
    batch_size: int,
    lease_owner: str,
    lease_seconds: int,
    max_attempts: int,
) -> int:
    """Lease one batch of outbox jobs and dispatch them by topic."""
    jobs = service.repository.claim_outbox_jobs(
        batch_size=batch_size,
        owner=lease_owner,
        lease_seconds=lease_seconds,
    )
    for job in jobs:
        with request_context_scope(dict(job.request_context or {})):
            try:
                if job.topic == "knowledge.vector_upsert":
                    await service._process_vector_job(job)
                elif job.topic == "knowledge.kg_upsert":
                    await service._process_kg_job(job)
                elif job.topic == "knowledge.vector_delete":
                    await service._process_vector_delete_job(job)
                elif job.topic == "knowledge.kg_delete":
                    await service._process_kg_delete_job(job)
                elif job.topic == "knowledge.classification_upsert":
                    await service._process_classification_job(job)
                elif job.topic == "knowledge.classification_delete":
                    await service._process_classification_delete_job(job)
                else:
                    raise ValueError(f"Unknown knowledge outbox topic: {job.topic}")
                service.repository.complete_outbox_job(job.id)
                if bool(job.payload.get("force")):
                    service.purge_deleted_item_if_ready(str(job.payload["item_id"]))
            except Exception as exc:
                service.repository.fail_outbox_job(
                    job.id,
                    error=str(exc),
                    max_attempts=max_attempts,
                )
    return len(jobs)
