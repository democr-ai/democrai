"""Knowledge-graph projection helpers for the knowledge service.

This module turns canonical item/entity/relation records into a scoped graph
representation suitable for neighborhood lookup and traversal-based retrieval.
In addition to direct entity relations it also projects hierarchy links,
attribute nodes, event nodes, and normalized time expressions.
"""

from __future__ import annotations

import hashlib

from democrai.core.application.knowledge.repository import ClaimedOutboxJob
from democrai.core.application.knowledge.service_helper.hierarchy import build_hierarchy_edges
from democrai.core.application.knowledge.service_helper.metadata import build_time_node_payload
from democrai.core.infrastructure.storage.kg.providers.base import KGEdge
from democrai.core.infrastructure.storage.kg.providers.base import KGEvidence
from democrai.core.infrastructure.storage.kg.providers.base import KGNode


_ATTRIBUTE_METADATA_EXCLUDE = {
    "extracted_by",
    "sentence",
    "source_sentence",
    "time_iso",
    "time_year",
    "time_month",
    "time_day",
    "time_hour",
    "time_minute",
    "time_granularity",
}
_EVENT_METADATA_KEYS = {
    "event",
    "events",
    "event_name",
    "event_type",
    "activity",
    "activities",
    "milestone",
    "milestones",
}


async def _upsert_item_reference_node(
    service,
    *,
    item,
    scope_user_id: int,
    scope_organization_id: int | None,
) -> None:
    await service._upsert_node(
        KGNode(
            id=f"ki:{item.id}",
            type="KnowledgeItem",
            user_id=scope_user_id,
            organization_id=scope_organization_id,
            name=item.title or item.kind,
            external_ref=item.external_ref,
            properties={
                "kind": item.kind,
                "content": item.content,
                "summary": item.summary,
                "metadata": service._metadata_load(item.metadata_json),
                "source_id": item.source_id,
                "owner_user_id": item.user_id,
                "is_public": bool(item.is_public),
            },
        )
    )


def _value_iterable(value):
    if isinstance(value, (list, tuple, set)):
        return [item for item in value if item not in (None, "")]
    if value in (None, ""):
        return []
    return [value]


def _attribute_node_id(entity_node_id: str, key: str, value: str) -> str:
    digest = hashlib.sha1(f"{entity_node_id}:{key}:{value}".encode("utf-8")).hexdigest()
    return f"attribute:{digest}"


def _event_node_id(entity_node_id: str, value: str) -> str:
    digest = hashlib.sha1(f"{entity_node_id}:event:{value}".encode("utf-8")).hexdigest()
    return f"event:{digest}"


async def process_kg_job(service, job: ClaimedOutboxJob) -> None:
    """Project one knowledge item and its graph neighborhood into the KG store."""
    item = service.repository.get_item(job.payload["item_id"])
    source = service.repository.get_source(job.payload["source_id"])
    if item is None or source is None or item.deleted_at is not None:
        return

    org_id = item.organization_id or None
    entities, relations = service._refresh_item_graph(
        item_id=item.id,
        user_id=item.user_id,
        organization_id=org_id,
    )
    source_items = service.repository.list_items_for_source(
        source_id=item.source_id,
        include_deleted=False,
    )
    hierarchy_edges = build_hierarchy_edges(
        items=list(source_items),
        metadata_load=service._metadata_load,
        focus_item_id=item.id,
    )
    entity_map = {entity.id: entity for entity in entities}
    for scope_user_id, scope_organization_id in service._projection_scopes_for_item(
        owner_user_id=item.user_id,
        owner_organization_id=org_id,
        owner_access_level=item.owner_access_level,
        is_public=bool(item.is_public),
        kind=item.kind,
    ):
        evidence = KGEvidence(
            id=f"evidence:{item.id}:{item.version}",
            kind=item.kind,
            ref=item.id,
            user_id=scope_user_id,
            organization_id=scope_organization_id,
            payload={
                "source_id": item.source_id,
                "item_id": item.id,
                "summary": item.summary,
                "owner_user_id": item.user_id,
                "is_public": bool(item.is_public),
            },
        )
        await service._ensure_evidence(evidence)
        await service._upsert_node(
            KGNode(
                id=f"ks:{source.id}",
                type="KnowledgeSource",
                user_id=scope_user_id,
                organization_id=scope_organization_id,
                name=source.title,
                external_ref=source.external_ref,
                properties={
                    "source_type": source.source_type,
                    "mime_type": source.mime_type,
                    "media_uri": source.media_uri,
                    "metadata": service._metadata_load(source.metadata_json),
                    "owner_user_id": item.user_id,
                    "is_public": bool(item.is_public),
                },
            )
        )
        await _upsert_item_reference_node(
            service,
            item=item,
            scope_user_id=scope_user_id,
            scope_organization_id=scope_organization_id,
        )
        item_metadata = service._metadata_load(item.metadata_json)
        time_payload = build_time_node_payload(item_metadata)
        if time_payload:
            time_node_id = str(time_payload["node_id"])
            await service._upsert_node(
                KGNode(
                    id=time_node_id,
                    type="TimeExpression",
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    name=str(time_payload.get("time_iso") or ""),
                    properties={
                        "time_iso": time_payload.get("time_iso"),
                        "time_year": time_payload.get("time_year"),
                        "time_month": time_payload.get("time_month"),
                        "time_day": time_payload.get("time_day"),
                        "time_hour": time_payload.get("time_hour"),
                        "time_minute": time_payload.get("time_minute"),
                        "time_granularity": time_payload.get("time_granularity"),
                    },
                )
            )
            time_edge_id = f"edge:time-ref:{item.id}:{time_node_id}"
            await service._upsert_edge(
                KGEdge(
                    id=time_edge_id,
                    src=f"ki:{item.id}",
                    dst=time_node_id,
                    type="REFERENCES_TIME",
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    evidence_id=evidence.id,
                    source="knowledge-service",
                    properties={"item_id": item.id, "time_iso": time_payload.get("time_iso")},
                )
            )
            await service.kg_store.link_edge_to_evidence(
                scope_user_id,
                time_edge_id,
                evidence.id,
                organization_id=scope_organization_id,
            )
            reverse_time_edge_id = f"edge:time-mentioned-in:{time_node_id}:{item.id}"
            await service._upsert_edge(
                KGEdge(
                    id=reverse_time_edge_id,
                    src=time_node_id,
                    dst=f"ki:{item.id}",
                    type="TIME_REFERENCED_IN",
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    evidence_id=evidence.id,
                    source="knowledge-service",
                    properties={"item_id": item.id, "time_iso": time_payload.get("time_iso")},
                )
            )
            await service.kg_store.link_edge_to_evidence(
                scope_user_id,
                reverse_time_edge_id,
                evidence.id,
                organization_id=scope_organization_id,
            )
        await service._upsert_edge(
            KGEdge(
                id=f"edge:source:{item.id}",
                src=f"ki:{item.id}",
                dst=f"ks:{source.id}",
                type="DERIVED_FROM",
                user_id=scope_user_id,
                organization_id=scope_organization_id,
                evidence_id=evidence.id,
                source="knowledge-service",
                properties={"item_id": item.id, "source_id": source.id},
            )
        )
        await service.kg_store.link_edge_to_evidence(
            scope_user_id,
            f"edge:source:{item.id}",
            evidence.id,
            organization_id=scope_organization_id,
        )

        for entity in entities:
            entity_node_id = service._graph_entity_node_id(entity)
            entity_metadata = service._metadata_load(entity.metadata_json)
            await service._upsert_node(
                KGNode(
                    id=entity_node_id,
                    type=entity.entity_type,
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    name=entity.canonical_name,
                    properties=entity_metadata,
                )
            )
            mention_edge_id = f"edge:mention:{item.id}:{entity.id}"
            await service._upsert_edge(
                KGEdge(
                    id=mention_edge_id,
                    src=f"ki:{item.id}",
                    dst=entity_node_id,
                    type="MENTIONS",
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    confidence=entity.confidence,
                    evidence_id=evidence.id,
                    source="knowledge-service",
                    properties={"item_id": item.id},
                )
            )
            await service.kg_store.link_edge_to_evidence(
                scope_user_id,
                mention_edge_id,
                evidence.id,
                organization_id=scope_organization_id,
            )
            referenced_edge_id = f"edge:mentioned-in:{entity.id}:{item.id}"
            await service._upsert_edge(
                KGEdge(
                    id=referenced_edge_id,
                    src=entity_node_id,
                    dst=f"ki:{item.id}",
                    type="MENTIONED_IN",
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    confidence=entity.confidence,
                    evidence_id=evidence.id,
                    source="knowledge-service",
                    properties={"item_id": item.id},
                )
            )
            await service.kg_store.link_edge_to_evidence(
                scope_user_id,
                referenced_edge_id,
                evidence.id,
                organization_id=scope_organization_id,
            )
            for key, raw_value in entity_metadata.items():
                if str(key).strip().lower() in _ATTRIBUTE_METADATA_EXCLUDE:
                    continue
                values = _value_iterable(raw_value)
                if not values:
                    continue
                for value in values:
                    rendered = str(value).strip()
                    if not rendered:
                        continue
                    if str(key).strip().lower() in _EVENT_METADATA_KEYS:
                        event_node_id = _event_node_id(entity_node_id, rendered)
                        await service._upsert_node(
                            KGNode(
                                id=event_node_id,
                                type="Event",
                                user_id=scope_user_id,
                                organization_id=scope_organization_id,
                                name=rendered,
                                properties={"event_key": str(key), "value": rendered},
                            )
                        )
                        event_edge_id = f"edge:event:{entity.id}:{event_node_id}"
                        await service._upsert_edge(
                            KGEdge(
                                id=event_edge_id,
                                src=entity_node_id,
                                dst=event_node_id,
                                type="PARTICIPATES_IN",
                                user_id=scope_user_id,
                                organization_id=scope_organization_id,
                                evidence_id=evidence.id,
                                source="knowledge-service",
                                properties={"item_id": item.id, "event_key": str(key)},
                            )
                        )
                        await service.kg_store.link_edge_to_evidence(
                            scope_user_id,
                            event_edge_id,
                            evidence.id,
                            organization_id=scope_organization_id,
                        )
                        continue
                    attribute_node_id = _attribute_node_id(
                        entity_node_id,
                        str(key).strip().lower(),
                        rendered,
                    )
                    await service._upsert_node(
                        KGNode(
                            id=attribute_node_id,
                            type="Attribute",
                            user_id=scope_user_id,
                            organization_id=scope_organization_id,
                            name=f"{key}: {rendered}",
                            properties={"attribute_key": str(key), "value": rendered},
                        )
                    )
                    attribute_edge_id = f"edge:attribute:{entity.id}:{attribute_node_id}"
                    await service._upsert_edge(
                        KGEdge(
                            id=attribute_edge_id,
                            src=entity_node_id,
                            dst=attribute_node_id,
                            type="HAS_ATTRIBUTE",
                            user_id=scope_user_id,
                            organization_id=scope_organization_id,
                            evidence_id=evidence.id,
                            source="knowledge-service",
                            properties={"item_id": item.id, "attribute_key": str(key)},
                        )
                    )
                    await service.kg_store.link_edge_to_evidence(
                        scope_user_id,
                        attribute_edge_id,
                        evidence.id,
                        organization_id=scope_organization_id,
                    )

        for relation in relations:
            source_entity = entity_map.get(relation.source_entity_id)
            target_entity = entity_map.get(relation.target_entity_id)
            if source_entity is None or target_entity is None:
                continue
            edge_id = f"edge:relation:{relation.id}"
            await service._upsert_edge(
                KGEdge(
                    id=edge_id,
                    src=service._graph_entity_node_id(source_entity),
                    dst=service._graph_entity_node_id(target_entity),
                    type=relation.relation_type,
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    confidence=relation.confidence,
                    weight=relation.weight,
                    evidence_id=evidence.id,
                    source="knowledge-service",
                    properties=service._metadata_load(relation.metadata_json),
                )
            )
            await service.kg_store.link_edge_to_evidence(
                scope_user_id,
                edge_id,
                evidence.id,
                organization_id=scope_organization_id,
            )
        source_item_by_id = {row.id: row for row in source_items}
        for hierarchy_edge in hierarchy_edges:
            src_item = source_item_by_id.get(hierarchy_edge.src_item_id)
            dst_item = source_item_by_id.get(hierarchy_edge.dst_item_id)
            if src_item is None or dst_item is None:
                continue
            await _upsert_item_reference_node(
                service,
                item=src_item,
                scope_user_id=scope_user_id,
                scope_organization_id=scope_organization_id,
            )
            await _upsert_item_reference_node(
                service,
                item=dst_item,
                scope_user_id=scope_user_id,
                scope_organization_id=scope_organization_id,
            )
            hierarchy_edge_id = (
                f"edge:hierarchy:{hierarchy_edge.edge_type.lower()}:"
                f"{hierarchy_edge.src_item_id}:{hierarchy_edge.dst_item_id}"
            )
            await service._upsert_edge(
                KGEdge(
                    id=hierarchy_edge_id,
                    src=f"ki:{hierarchy_edge.src_item_id}",
                    dst=f"ki:{hierarchy_edge.dst_item_id}",
                    type=hierarchy_edge.edge_type,
                    user_id=scope_user_id,
                    organization_id=scope_organization_id,
                    evidence_id=evidence.id,
                    source="knowledge-service",
                    properties={"source_id": item.source_id},
                )
            )
            await service.kg_store.link_edge_to_evidence(
                scope_user_id,
                hierarchy_edge_id,
                evidence.id,
                organization_id=scope_organization_id,
            )

    service.repository.mark_item_status(item_id=item.id, kg_status="synced")
    service.repository.upsert_projection_state(
        aggregate_type="knowledge_item",
        aggregate_id=item.id,
        projection="kg",
        backend=type(service.kg_store).__name__,
        backend_key=f"ki:{item.id}",
        synced_version=item.version,
        status="synced",
    )


async def process_kg_delete_job(service, job: ClaimedOutboxJob) -> None:
    """Delete a knowledge item's derived KG projection from all visible scopes."""
    item = service.repository.get_item(job.payload["item_id"])
    source = service.repository.get_source(job.payload["source_id"])
    if item is None:
        return
    force = bool(job.payload.get("force"))
    entities = service.repository.list_entities(item.id)
    relations = service.repository.list_relations(item.id)
    source_items = service.repository.list_items_for_source(
        source_id=item.source_id,
        include_deleted=True,
    )
    hierarchy_edges = build_hierarchy_edges(
        items=list(source_items),
        metadata_load=service._metadata_load,
        focus_item_id=item.id,
    )
    item_metadata = service._metadata_load(item.metadata_json)
    time_payload = build_time_node_payload(item_metadata)
    for scope_user_id, scope_organization_id in service._projection_scopes_for_item(
        owner_user_id=item.user_id,
        owner_organization_id=item.organization_id or None,
        owner_access_level=item.owner_access_level,
        is_public=bool(item.is_public),
        kind=item.kind,
    ):
        orphan_candidates: list[str] = []
        for relation in relations:
            await service.kg_store.delete_edge(
                scope_user_id,
                f"edge:relation:{relation.id}",
                soft=not force,
                organization_id=scope_organization_id,
            )
        for entity in entities:
            entity_metadata = service._metadata_load(entity.metadata_json)
            entity_node_id = service._graph_entity_node_id(entity)
            orphan_candidates.append(entity_node_id)
            await service.kg_store.delete_edge(
                scope_user_id,
                f"edge:mention:{item.id}:{entity.id}",
                soft=not force,
                organization_id=scope_organization_id,
            )
            await service.kg_store.delete_edge(
                scope_user_id,
                f"edge:mentioned-in:{entity.id}:{item.id}",
                soft=not force,
                organization_id=scope_organization_id,
            )
            for key, raw_value in entity_metadata.items():
                if str(key).strip().lower() in _ATTRIBUTE_METADATA_EXCLUDE:
                    continue
                for value in _value_iterable(raw_value):
                    rendered = str(value).strip()
                    if not rendered:
                        continue
                    if str(key).strip().lower() in _EVENT_METADATA_KEYS:
                        await service.kg_store.delete_edge(
                            scope_user_id,
                            f"edge:event:{entity.id}:{_event_node_id(entity_node_id, rendered)}",
                            soft=not force,
                            organization_id=scope_organization_id,
                        )
                        orphan_candidates.append(_event_node_id(entity_node_id, rendered))
                        continue
                    attribute_node_id = _attribute_node_id(
                        entity_node_id,
                        str(key).strip().lower(),
                        rendered,
                    )
                    await service.kg_store.delete_edge(
                        scope_user_id,
                        f"edge:attribute:{entity.id}:{attribute_node_id}",
                        soft=not force,
                        organization_id=scope_organization_id,
                    )
                    orphan_candidates.append(attribute_node_id)
        await service.kg_store.delete_edge(
            scope_user_id,
            f"edge:source:{item.id}",
            soft=not force,
            organization_id=scope_organization_id,
        )
        for hierarchy_edge in hierarchy_edges:
            if item.id not in {
                hierarchy_edge.src_item_id,
                hierarchy_edge.dst_item_id,
            }:
                continue
            await service.kg_store.delete_edge(
                scope_user_id,
                (
                    f"edge:hierarchy:{hierarchy_edge.edge_type.lower()}:"
                    f"{hierarchy_edge.src_item_id}:{hierarchy_edge.dst_item_id}"
                ),
                soft=not force,
                organization_id=scope_organization_id,
            )
        if time_payload:
            time_node_id = str(time_payload["node_id"])
            orphan_candidates.append(time_node_id)
            await service.kg_store.delete_edge(
                scope_user_id,
                f"edge:time-ref:{item.id}:{time_node_id}",
                soft=not force,
                organization_id=scope_organization_id,
            )
            await service.kg_store.delete_edge(
                scope_user_id,
                f"edge:time-mentioned-in:{time_node_id}:{item.id}",
                soft=not force,
                organization_id=scope_organization_id,
            )
        await service.kg_store.delete_node(
            scope_user_id,
            f"ki:{item.id}",
            soft=not force,
            organization_id=scope_organization_id,
        )
        if source is not None and (
            not force
            or (
                source.deleted_at is not None
                and not service.repository.list_items_for_source(
                    source_id=source.id,
                    include_deleted=False,
                )
            )
        ):
            await service.kg_store.delete_node(
                scope_user_id,
                f"ks:{source.id}",
                soft=not force,
                organization_id=scope_organization_id,
            )
        if force:
            for version in {max(1, int(job.aggregate_version) - 1), int(job.aggregate_version)}:
                await service.kg_store.delete_evidence(
                    scope_user_id,
                    f"evidence:{item.id}:{version}",
                    organization_id=scope_organization_id,
                )
            await service.kg_store.prune_orphan_nodes(
                scope_user_id,
                orphan_candidates,
                organization_id=scope_organization_id,
            )
    service.repository.mark_item_status(item_id=item.id, kg_status="deleted")
    service.repository.upsert_projection_state(
        aggregate_type="knowledge_item",
        aggregate_id=item.id,
        projection="kg",
        backend=type(service.kg_store).__name__,
        backend_key=f"ki:{item.id}",
        synced_version=item.version,
        status="deleted",
    )


async def upsert_edge(service, edge: KGEdge) -> None:
    """Idempotently upsert an edge in the KG backend."""
    existing = await service.kg_store.get_edge(
        edge.user_id,
        edge.id,
        organization_id=edge.organization_id,
    )
    if existing is None:
        await service.kg_store.add_edge(edge)
        return
    await service.kg_store.update_edge(
        edge.user_id,
        edge.id,
        edge.properties,
        organization_id=edge.organization_id,
        weight=edge.weight,
        confidence=edge.confidence,
        source=edge.source,
        evidence_id=edge.evidence_id,
        deleted_at=None,
    )


async def ensure_evidence(service, evidence: KGEvidence) -> None:
    """Idempotently upsert evidence through the configured KG backend."""
    await service.kg_store.add_evidence(evidence)
