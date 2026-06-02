"""Helpers for item-level graph refresh, merge, and scope resolution.

The canonical relational graph for an item is stored as entities and relations
in the database. The helpers in this module merge explicit inputs with
extractor-derived triples, derive stable node identifiers, and compute the
projection scopes used by vector and KG stores.
"""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from democrai.core.application.knowledge.models import EntityInput
from democrai.core.application.knowledge.models import RelationInput
from democrai.core.application.knowledge.visibility import inherited_visibility_scopes
from democrai.core.application.knowledge.visibility import retrieval_scope_chain


def refresh_item_graph(
    service,
    *,
    item_id: str,
    user_id: int,
    organization_id: int | None,
) -> tuple[list[Any], list[Any]]:
    """Refresh the relational graph for an item before KG projection.

    Existing entities and relations are loaded, optionally enriched through the
    configured triple extractor, and then replaced atomically in canonical
    storage.
    """
    entities = service.repository.list_entities(item_id)
    relations = service.repository.list_relations(item_id)
    if service.triple_extractor is None:
        return entities, relations

    item = service.repository.get_item(item_id)
    if item is None:
        return entities, relations
    merged_entities, merged_relations = service._merge_graph_inputs(
        item=item,
        entities=entities,
        relations=relations,
    )
    service.repository.replace_item_graph(
        item_id=item_id,
        user_id=user_id,
        organization_id=organization_id,
        entities=merged_entities,
        relations=merged_relations,
    )
    return service.repository.list_entities(item_id), service.repository.list_relations(
        item_id
    )


def merge_graph_inputs(
    service,
    *,
    item: Any,
    entities: list[Any],
    relations: list[Any],
) -> tuple[tuple[EntityInput, ...], tuple[RelationInput, ...]]:
    """Merge explicit graph inputs with extractor-derived entities/relations."""
    entity_inputs = {
        service._entity_key(entity.canonical_name): EntityInput(
            name=entity.canonical_name,
            entity_type=entity.entity_type,
            confidence=entity.confidence,
            metadata=service._metadata_load(entity.metadata_json),
        )
        for entity in entities
    }
    relation_inputs = {}
    entity_by_id = {entity.id: entity for entity in entities}
    for relation in relations:
        source_entity = entity_by_id.get(relation.source_entity_id)
        target_entity = entity_by_id.get(relation.target_entity_id)
        if source_entity is None or target_entity is None:
            continue
        relation_input = RelationInput(
            relation_type=relation.relation_type,
            source_entity_name=source_entity.canonical_name,
            target_entity_name=target_entity.canonical_name,
            confidence=relation.confidence,
            weight=relation.weight,
            metadata=service._metadata_load(relation.metadata_json),
        )
        relation_inputs[service._relation_key(relation_input)] = relation_input

    extracted = service.triple_extractor.extract_item(
        kind=item.kind,
        title=item.title,
        summary=item.summary,
        content=item.content,
    )
    for entity in extracted.entities:
        key = service._entity_key(entity.name)
        existing = entity_inputs.get(key)
        if existing is None or existing.entity_type == "Entity":
            entity_inputs[key] = entity
    for relation in extracted.relations:
        relation_inputs.setdefault(service._relation_key(relation), relation)
    return tuple(entity_inputs.values()), tuple(relation_inputs.values())


def entity_key(name: str) -> str:
    """Return the normalization key used to deduplicate entities by name."""
    return name.casefold()


def relation_key(relation: RelationInput) -> tuple[str, str, str]:
    """Return the normalization key used to deduplicate relations."""
    return (
        relation.relation_type.casefold(),
        relation.source_entity_name.casefold(),
        relation.target_entity_name.casefold(),
    )


def graph_entity_node_id(entity: Any) -> str:
    """Return the stable KG node identifier for an entity projection."""
    canonical_name = str(getattr(entity, "canonical_name", "") or "").strip()
    entity_type = str(getattr(entity, "entity_type", "Entity") or "Entity").strip()
    if not canonical_name:
        return f"entity:{uuid4().hex}"
    digest = hashlib.sha1(
        f"{entity_type}:{canonical_name.casefold()}".encode("utf-8")
    ).hexdigest()
    return f"entity:{digest}"


def projection_scopes_for_item(
    service,
    *,
    owner_user_id: int,
    owner_organization_id: int | None,
    owner_access_level: int,
    is_public: bool,
    kind: str,
) -> tuple[tuple[int, int | None], ...]:
    """Return every projection scope that must contain the item's projection."""
    scopes = [(owner_user_id, owner_organization_id)]
    scopes.extend(
        inherited_visibility_scopes(
            owner_access_level=owner_access_level,
            organization_id=owner_organization_id,
            is_public=is_public,
            kind=kind,
        )
    )
    deduped: list[tuple[int, int | None]] = []
    seen: set[tuple[int, int | None]] = set()
    for scope in scopes:
        if scope in seen:
            continue
        seen.add(scope)
        deduped.append(scope)
    return tuple(deduped)


def graph_scope_for_item(
    service,
    *,
    requester_user_id: int,
    requester_organization_id: int | None,
    requester_access_level: int,
    owner_user_id: int,
    owner_organization_id: int | None,
    owner_access_level: int,
    is_public: bool,
    kind: str,
) -> tuple[int, int | None]:
    """Return the most appropriate graph scope visible to the requester."""
    if requester_user_id == owner_user_id:
        return owner_user_id, owner_organization_id
    candidate_scopes = service._projection_scopes_for_item(
        owner_user_id=owner_user_id,
        owner_organization_id=owner_organization_id,
        owner_access_level=owner_access_level,
        is_public=is_public,
        kind=kind,
    )
    allowed_scopes = retrieval_scope_chain(
        user_id=requester_user_id,
        organization_id=requester_organization_id,
        access_level=requester_access_level,
    )
    for scope in candidate_scopes:
        if scope in allowed_scopes:
            return scope
    return owner_user_id, owner_organization_id
