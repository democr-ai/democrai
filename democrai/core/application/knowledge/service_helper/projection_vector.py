"""Vector projection helpers for the knowledge service.

The vector store is a derived index built from canonical knowledge items. This
module computes embeddings when needed, writes vectors into every visible scope,
and keeps projection state synchronized with the outbox worker lifecycle.
"""

from __future__ import annotations

import json

from democrai.core.application.knowledge.repository import ClaimedOutboxJob
from democrai.core.infrastructure.storage.kg.providers.base import KGNode
from democrai.core.infrastructure.storage.vector.base import UserScope
from democrai.core.infrastructure.storage.vector.base import VectorDoc


async def process_vector_job(service, job: ClaimedOutboxJob) -> None:
    """Project one knowledge item into the vector backend.

    If the item does not already store an embedding vector the function computes
    it from ``embedding_text``, persists the vector metadata back into canonical
    storage, and then writes the vector to every scope visible for the item.
    """
    item = service.repository.get_item(job.payload["item_id"])
    if item is None or item.deleted_at is not None:
        return
    module_name = service._module_name_for_source_id(item.source_id)
    vector_spec = service._vector_spec_for_module(module_name)
    vector = (
        json.loads(item.embedding_vector_json) if item.embedding_vector_json else None
    )
    if vector is None:
        if service.embedding_provider is None:
            raise RuntimeError(
                "No embedding provider configured for knowledge vector projection"
            )
        vector = service.embedding_provider.embed_texts([item.embedding_text])[0]
        item = service.repository.set_item_embedding(
            item_id=item.id,
            vector=vector,
            embedding_model_id=service.embedding_provider.model_id,
            embedding_model_version=service.embedding_provider.model_version,
        )

    if item.embedding_dim and item.embedding_dim != vector_spec.dim:
        raise ValueError(
            f"Knowledge vector dim mismatch: item={item.embedding_dim} index={vector_spec.dim}"
        )

    await service.vector_store.ensure_index(vector_spec)
    for scope_user_id, scope_organization_id in service._projection_scopes_for_item(
        owner_user_id=item.user_id,
        owner_organization_id=item.organization_id or None,
        owner_access_level=item.owner_access_level,
        is_public=bool(item.is_public),
        kind=item.kind,
    ):
        await service.vector_store.upsert(
            UserScope(user_id=scope_user_id, organization_id=scope_organization_id),
            vector_spec,
            [
                VectorDoc(
                    id=item.id,
                    vector=vector,
                    metadata={
                        "source_id": item.source_id,
                        "kind": item.kind,
                        "title": item.title,
                        "owner_user_id": item.user_id,
                        "is_public": bool(item.is_public),
                    },
                )
            ],
        )
    service.repository.mark_item_status(item_id=item.id, vector_status="synced")
    service.repository.upsert_projection_state(
        aggregate_type="knowledge_item",
        aggregate_id=item.id,
        projection="vector",
        backend=(await service.vector_store.info()).name,
        backend_key=(
            f"{vector_spec.tenant_id}:{vector_spec.app_id}:"
            f"{vector_spec.name}:{item.id}"
        ),
        synced_version=item.version,
        status="synced",
    )


async def process_vector_delete_job(service, job: ClaimedOutboxJob) -> None:
    """Delete one item's vectors from every visible vector scope."""
    item = service.repository.get_item(job.payload["item_id"])
    if item is None:
        return
    module_name = service._module_name_for_source_id(item.source_id)
    vector_spec = service._vector_spec_for_module(module_name)
    for scope_user_id, scope_organization_id in service._projection_scopes_for_item(
        owner_user_id=item.user_id,
        owner_organization_id=item.organization_id or None,
        owner_access_level=item.owner_access_level,
        is_public=bool(item.is_public),
        kind=item.kind,
    ):
        await service.vector_store.delete_ids(
            UserScope(user_id=scope_user_id, organization_id=scope_organization_id),
            vector_spec,
            [item.id],
        )
    service.repository.mark_item_status(item_id=item.id, vector_status="deleted")
    service.repository.upsert_projection_state(
        aggregate_type="knowledge_item",
        aggregate_id=item.id,
        projection="vector",
        backend=(await service.vector_store.info()).name,
        backend_key=(
            f"{vector_spec.tenant_id}:{vector_spec.app_id}:"
            f"{vector_spec.name}:{item.id}"
        ),
        synced_version=item.version,
        status="deleted",
    )


async def upsert_node(service, node: KGNode) -> None:
    """Idempotently upsert a KG node through the configured backend.

    The helper lives here because vector and KG projection workers share a small
    amount of generic graph-upsert logic.
    """
    existing = await service.kg_store.get_node(
        node.user_id,
        node.id,
        organization_id=node.organization_id,
    )
    if existing is None:
        await service.kg_store.add_node(node)
        return
    await service.kg_store.update_node(
        node.user_id,
        node.id,
        node.properties,
        organization_id=node.organization_id,
        name=node.name,
        external_ref=node.external_ref,
        deleted_at=None,
    )
