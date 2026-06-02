"""Wrapper extractors that compose and gate graph extraction strategies."""

from __future__ import annotations

from typing import Sequence

from democrai.core.application.knowledge.models import EntityInput, RelationInput

from ._base import ExtractedKnowledgeGraph, TripleExtractor, clamp_limit


class ConditionalTripleExtractor(TripleExtractor):
    """Delegate to another extractor only when the item matches guard rules."""
    def __init__(
        self,
        extractor: TripleExtractor,
        *,
        allowed_kinds: Sequence[str] | None = None,
        min_chars: int = 0,
        max_chars: int = 12000,
    ) -> None:
        self.extractor = extractor
        self.allowed_kinds = {
            str(kind).strip() for kind in (allowed_kinds or ()) if str(kind).strip()
        }
        self.min_chars = max(0, min_chars)
        self.max_chars = max(self.min_chars if self.min_chars > 0 else 1, max_chars)

    def extract_item(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        """Run the wrapped extractor only for eligible kinds and lengths."""
        text = content
        if self.allowed_kinds and kind not in self.allowed_kinds:
            return ExtractedKnowledgeGraph(entities=(), relations=())
        if len(text) < self.min_chars:
            return ExtractedKnowledgeGraph(entities=(), relations=())
        return self.extractor.extract_item(
            kind=kind, title=title, summary=summary, content=text[: self.max_chars]
        )


class CompositeTripleExtractor(TripleExtractor):
    """Merge the outputs of multiple extractors into one normalized graph."""
    def __init__(
        self,
        *extractors: TripleExtractor,
        max_entities: int = 24,
        max_relations: int = 48,
    ) -> None:
        self.extractors = tuple(
            extractor for extractor in extractors if extractor is not None
        )
        self.max_entities = clamp_limit(max_entities, fallback=24)
        self.max_relations = clamp_limit(max_relations, fallback=48)

    def extract_item(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        """Run each extractor and merge the resulting entities/relations."""
        merged_entities: dict[str, EntityInput] = {}
        merged_relations: dict[tuple[str, str, str], RelationInput] = {}
        for extractor in self.extractors:
            try:
                extracted = extractor.extract_item(
                    kind=kind, title=title, summary=summary, content=content
                )
            except Exception:
                continue
            for entity in extracted.entities:
                merged_entities.setdefault(entity.name.casefold(), entity)
            for relation in extracted.relations:
                merged_relations.setdefault(
                    (
                        relation.relation_type.casefold(),
                        relation.source_entity_name.casefold(),
                        relation.target_entity_name.casefold(),
                    ),
                    relation,
                )
        return ExtractedKnowledgeGraph(
            entities=tuple(list(merged_entities.values())[: self.max_entities]),
            relations=tuple(list(merged_relations.values())[: self.max_relations]),
        )
