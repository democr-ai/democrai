"""Heuristic entity and relation extractor for lightweight knowledge graphs.

The heuristic extractor is intentionally conservative: it prefers a small set
of grounded patterns over aggressive guessing so it can remain a reliable
fallback when no chat-capable provider is available.
"""

from __future__ import annotations

import re
from typing import Iterable

from democrai.core.application.knowledge.models import EntityInput, RelationInput

from ._base import ExtractedKnowledgeGraph, TripleExtractor


_NAME_PATTERN = r"[A-Z][A-Za-z0-9&'./-]*(?:\s+[A-Z][A-Za-z0-9&'./-]*){0,3}"
_ENTITY_RE = re.compile(_NAME_PATTERN)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_ORG_MARKERS = (
    "inc",
    "corp",
    "corporation",
    "company",
    "co",
    "ltd",
    "llc",
    "gmbh",
    "group",
    "team",
    "agency",
    "association",
    "committee",
    "ministry",
    "department",
    "university",
    "bank",
    "srl",
    "spa",
)
_PERSON_PREFIXES = ("mr", "mrs", "ms", "dr", "prof", "sir", "madam")
_ENTITY_STOPWORDS = {
    "The",
    "This",
    "That",
    "These",
    "Those",
    "And",
    "But",
    "For",
    "From",
    "With",
    "Without",
    "When",
    "Where",
    "While",
    "Because",
    "Columns",
    "Table",
    "Image",
    "Page",
    "Section",
}


class HeuristicTripleExtractor(TripleExtractor):
    """Extract entities and relations using regex-based heuristics."""

    def __init__(self, *, max_entities: int = 24, max_relations: int = 48) -> None:
        self.max_entities = max(1, max_entities)
        self.max_relations = max(1, max_relations)
        src_name = rf"(?P<src>{_NAME_PATTERN})"
        dst_name = rf"(?P<dst>{_NAME_PATTERN})"
        self._relation_patterns = (
            (
                re.compile(
                    rf"{src_name}\s+(?:works at|works for|employed by)\s+{dst_name}"
                ),
                "WORKS_AT",
            ),
            (
                re.compile(
                    rf"{src_name}\s+(?:works with|partners with|partnered with|collaborates with|collaborated with)\s+{dst_name}"
                ),
                "PARTNERS_WITH",
            ),
            (
                re.compile(
                    rf"{src_name}\s+(?:advises|advised|consults for|consulted for)\s+{dst_name}"
                ),
                "ADVISES",
            ),
            (
                re.compile(rf"{src_name}\s+(?:manages|managed|leads|led)\s+{dst_name}"),
                "MANAGES",
            ),
            (
                re.compile(rf"{src_name}\s+(?:reports to|reported to)\s+{dst_name}"),
                "REPORTS_TO",
            ),
            (
                re.compile(
                    rf"{src_name}\s+(?:acquired|acquires|owns|owned)\s+{dst_name}"
                ),
                "OWNS",
            ),
            (
                re.compile(rf"{src_name}\s+(?:is part of|belongs to)\s+{dst_name}"),
                "PART_OF",
            ),
            (
                re.compile(
                    rf"{src_name}\s+(?:uses|used|implements|implemented)\s+{dst_name}"
                ),
                "USES",
            ),
        )

    def extract_item(
        self, *, kind: str, title: str | None, summary: str | None, content: str
    ) -> ExtractedKnowledgeGraph:
        """Extract a compact graph from title/summary/content text."""
        text = "\n".join(
            part.strip() for part in (title, summary, content) if part and part.strip()
        )
        if not text:
            return ExtractedKnowledgeGraph(entities=(), relations=())

        entities: dict[str, EntityInput] = {}
        relations: dict[tuple[str, str, str], RelationInput] = {}
        for sentence in self._sentences(text):
            for pattern, relation_type in self._relation_patterns:
                for match in pattern.finditer(sentence):
                    source_name = self._clean_entity_name(match.group("src"))
                    target_name = self._clean_entity_name(match.group("dst"))
                    if not source_name or not target_name or source_name == target_name:
                        continue
                    source_entity = self._entity_input(source_name)
                    target_entity = self._entity_input(target_name)
                    entities.setdefault(
                        self._entity_key(source_entity.name), source_entity
                    )
                    entities.setdefault(
                        self._entity_key(target_entity.name), target_entity
                    )
                    relation = RelationInput(
                        relation_type=relation_type,
                        source_entity_name=source_entity.name,
                        target_entity_name=target_entity.name,
                        confidence=0.45,
                        weight=0.55,
                        metadata={
                            "extracted_by": "heuristic-triple-extractor",
                            "sentence": sentence[:240],
                        },
                    )
                    relations[self._relation_key(relation)] = relation

            for candidate in self._extract_entities(sentence):
                entities.setdefault(self._entity_key(candidate.name), candidate)

        return ExtractedKnowledgeGraph(
            entities=tuple(list(entities.values())[: self.max_entities]),
            relations=tuple(list(relations.values())[: self.max_relations]),
        )

    def _extract_entities(self, sentence: str) -> Iterable[EntityInput]:
        found: list[EntityInput] = []
        for match in _ENTITY_RE.finditer(sentence):
            name = self._clean_entity_name(match.group(0))
            if not name or name in _ENTITY_STOPWORDS:
                continue
            if len(name) < 2 or name.isupper() and len(name) == 1:
                continue
            found.append(self._entity_input(name))
            if len(found) >= self.max_entities:
                break
        return found

    @staticmethod
    def _entity_input(name: str) -> EntityInput:
        return EntityInput(
            name=name,
            entity_type=HeuristicTripleExtractor._infer_entity_type(name),
            confidence=0.35,
            metadata={"extracted_by": "heuristic-triple-extractor"},
        )

    @staticmethod
    def _infer_entity_type(name: str) -> str:
        lowered = name.lower()
        tokens = [token.strip(".").lower() for token in name.split()]
        if tokens and tokens[0] in _PERSON_PREFIXES:
            return "Person"
        if any(marker in lowered.split() for marker in _ORG_MARKERS):
            return "Organization"
        if len(tokens) >= 2 and all(token[:1].isalpha() for token in tokens):
            return "Person"
        if any(marker in lowered for marker in _ORG_MARKERS):
            return "Organization"
        return "Entity"

    @staticmethod
    def _clean_entity_name(value: str) -> str:
        return re.sub(r"\s+", " ", value.strip(" ,.;:()[]{}"))

    @staticmethod
    def _sentences(text: str) -> list[str]:
        return [
            part.strip()
            for part in _SENTENCE_SPLIT_RE.split(text)
            if part and part.strip()
        ]

    @staticmethod
    def _entity_key(name: str) -> str:
        return name.casefold()

    @staticmethod
    def _relation_key(relation: RelationInput) -> tuple[str, str, str]:
        return (
            relation.relation_type.casefold(),
            relation.source_entity_name.casefold(),
            relation.target_entity_name.casefold(),
        )
