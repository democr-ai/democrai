"""Core data structures and normalization helpers for graph extraction.

Both heuristic and LLM-backed extractors return the same normalized graph shape
defined here. This keeps downstream ingestion and projection logic independent
from the extraction strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from democrai.core.application.knowledge.models import EntityInput, RelationInput


@dataclass(frozen=True)
class ExtractedKnowledgeGraph:
    """Normalized graph extraction result for a single item."""
    entities: tuple[EntityInput, ...]
    relations: tuple[RelationInput, ...]


class TripleExtractor(ABC):
    """Abstract base class implemented by all graph extractors."""
    @abstractmethod
    def extract_item(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        raise NotImplementedError


def clamp_limit(value: int, *, fallback: int) -> int:
    """Clamp an extraction limit to a safe positive integer."""
    return max(1, int(value or fallback))


def normalize_graph_payload(
    payload: dict[str, object] | None,
    *,
    max_entities: int,
    max_relations: int,
) -> ExtractedKnowledgeGraph:
    """Normalize raw JSON-like payloads into the canonical graph shape.

    Invalid rows, missing names, self-relations, and duplicates are discarded so
    downstream code can assume a compact and consistent graph payload.
    """
    raw_payload = payload or {}
    raw_entities = raw_payload.get("entities")
    raw_relations = raw_payload.get("relations")

    entities: list[EntityInput] = []
    seen_entities: set[str] = set()
    for raw_entity in raw_entities if isinstance(raw_entities, list) else []:
        if not isinstance(raw_entity, dict):
            continue
        name = str(raw_entity.get("name") or "").strip()
        entity_type = str(raw_entity.get("entity_type") or "Entity").strip() or "Entity"
        if not name:
            continue
        key = name.casefold()
        if key in seen_entities:
            continue
        seen_entities.add(key)
        confidence = raw_entity.get("confidence")
        entities.append(
            EntityInput(
                name=name,
                entity_type=entity_type,
                confidence=float(confidence)
                if isinstance(confidence, (int, float))
                else None,
                metadata=raw_entity.get("metadata")
                if isinstance(raw_entity.get("metadata"), dict)
                else {},
            )
        )
        if len(entities) >= max_entities:
            break

    relation_candidates = {}
    for raw_relation in raw_relations if isinstance(raw_relations, list) else []:
        if not isinstance(raw_relation, dict):
            continue
        relation_type = str(raw_relation.get("relation_type") or "").strip()
        source_name = str(raw_relation.get("source_entity_name") or "").strip()
        target_name = str(raw_relation.get("target_entity_name") or "").strip()
        if (
            not relation_type
            or not source_name
            or not target_name
            or source_name == target_name
        ):
            continue
        relation = RelationInput(
            relation_type=relation_type,
            source_entity_name=source_name,
            target_entity_name=target_name,
            confidence=float(raw_relation["confidence"])
            if isinstance(raw_relation.get("confidence"), (int, float))
            else None,
            weight=float(raw_relation["weight"])
            if isinstance(raw_relation.get("weight"), (int, float))
            else None,
            metadata=raw_relation.get("metadata")
            if isinstance(raw_relation.get("metadata"), dict)
            else {},
        )
        relation_candidates[
            (
                relation.relation_type.casefold(),
                relation.source_entity_name.casefold(),
                relation.target_entity_name.casefold(),
            )
        ] = relation

    return ExtractedKnowledgeGraph(
        entities=tuple(entities[:max_entities]),
        relations=tuple(list(relation_candidates.values())[:max_relations]),
    )


def build_llm_prompt(
    *, kind: str, title: str | None, summary: str | None, content: str
) -> str:
    """Build the user prompt passed to the LLM graph extractor."""
    return f"kind: {kind}\ntitle: {title or ''}\nsummary: {summary or ''}\ncontent:\n{content}"


GRAPH_SYSTEM_PROMPT = (
    "Extract a compact knowledge graph from the text. "
    "Return strict JSON with keys 'entities' and 'relations'. "
    "Each entity must contain: name, entity_type, confidence, metadata. "
    "Each relation must contain: relation_type, source_entity_name, target_entity_name, confidence, weight, metadata. "
    "Use only facts grounded in the input. Do not invent entities or relations. "
    "Prefer canonical entities and include grounded scalar metadata when present, such as role, title, organization, location, aliases, status, year, month, day, hour, minute, time_iso, time_granularity. "
    "If the text describes notable events, either emit Event entities or relations whose metadata includes the event name and grounded temporal fields."
)
