"""Typed request/response models for the knowledge subsystem.

The dataclasses in this module are the stable contracts exchanged between
ingestion, persistence, projection runtimes, and retrieval flows. They are
intentionally transport-agnostic so the same payloads can represent document
ingestion, chat-memory ingestion, media-derived summaries, and graph-oriented
retrieval results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class EntityInput:
    """Canonical entity extracted or supplied for a knowledge item.

    :param name: Human-readable entity label as it should appear in retrieval
        or graph projections.
    :param entity_type: Semantic type such as ``Person``, ``Organization``,
        ``Location`` or ``Event``.
    :param entity_id: Optional caller-provided identifier reused when replacing
        the item graph.
    :param metadata: Grounded scalar or descriptive metadata associated with
        the entity. This is later reused to project attribute/event nodes into
        the knowledge graph.
    :param confidence: Optional extraction confidence in the ``0..1`` range.
    """

    name: str
    entity_type: str
    entity_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None


@dataclass(frozen=True)
class RelationInput:
    """Directed relation between two extracted entities.

    :param relation_type: Semantic edge type, for example ``WORKS_AT`` or
        ``PARTNERS_WITH``.
    :param source_entity_name: Canonical name of the source entity.
    :param target_entity_name: Canonical name of the target entity.
    :param relation_id: Optional caller-provided identifier reused when
        replacing relations for the same item.
    :param metadata: Additional grounded metadata carried on the relation.
    :param confidence: Optional extraction confidence.
    :param weight: Optional edge weight used by graph backends that support it.
    """

    relation_type: str
    source_entity_name: str
    target_entity_name: str
    relation_id: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    weight: Optional[float] = None


@dataclass(frozen=True)
class KnowledgeIngestItem:
    """Single unit ingested into the knowledge pipeline.

    A single source can produce many items at different granularities. For
    example a PDF may produce a ``document_summary``, multiple
    ``chapter_summary`` items, and several ``document_chunk`` items. Chat
    memory, image descriptions, transcripts, and agent traces all reuse the
    same shape.

    :param kind: Semantic item kind used for retrieval weighting, visibility
        rules, and selective graph extraction.
    :param content: Canonical content stored and returned by retrieval.
    :param item_id: Optional stable identifier used during updates.
    :param title: Optional human-readable label for graph and retrieval output.
    :param summary: Optional compact summary shown in retrieval results and
        reused as fallback embedding text.
    :param embedding_text: Optional explicit text to embed. When omitted the
        repository falls back to ``summary`` and then ``content``.
    :param metadata: Arbitrary metadata later enriched with normalized
        cross-media and temporal fields by the ingestion helpers.
    :param external_ref: Optional external identifier associated with the item.
    :param vector: Optional precomputed embedding vector.
    :param is_public: Visibility flag later normalized according to item kind.
    :param entities: Explicit entities already known for the item.
    :param relations: Explicit relations already known for the item.
    """

    kind: str
    content: str
    item_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    embedding_text: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    external_ref: Optional[str] = None
    vector: Optional[list[float]] = None
    is_public: bool = False
    entities: tuple[EntityInput, ...] = ()
    relations: tuple[RelationInput, ...] = ()


@dataclass(frozen=True)
class KnowledgeSourceInput:
    """Logical source from which knowledge items originate.

    The source groups items that belong to the same uploaded file, media asset,
    chat session, or agent run. Source-level metadata is also used to resolve
    vector index partitioning and to derive cross-item hierarchy links.
    """

    source_type: str
    source_id: Optional[str] = None
    title: Optional[str] = None
    mime_type: Optional[str] = None
    external_ref: Optional[str] = None
    media_uri: Optional[str] = None
    checksum: Optional[str] = None
    is_public: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeIngestRequest:
    """Request used to persist a source and all of its extracted items."""

    user_id: int
    organization_id: Optional[int]
    source: KnowledgeSourceInput
    items: tuple[KnowledgeIngestItem, ...]


@dataclass(frozen=True)
class KnowledgeIngestResult:
    """Persistence result returned after an ingestion request is accepted."""

    source_id: str
    item_ids: tuple[str, ...]
    outbox_ids: tuple[str, ...]


@dataclass(frozen=True)
class KnowledgeRetrieveRequest:
    """Input parameters for hybrid lexical/vector/graph retrieval."""

    user_id: int
    organization_id: Optional[int]
    query_text: str
    query_vector: Optional[list[float]] = None
    top_k: int = 8
    lexical_limit: int = 8
    graph_neighbors_limit: int = 4
    access_level: int = 3
    metadata_filters: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeRetrieveMatch:
    """Normalized retrieval result enriched with graph neighbors."""

    item_id: str
    source_id: str
    kind: str
    title: Optional[str]
    content: str
    summary: Optional[str]
    score: float
    metadata: Mapping[str, Any]
    graph_neighbors: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class KnowledgeRetrieveResult:
    """Collection of retrieval matches returned to the caller."""

    matches: tuple[KnowledgeRetrieveMatch, ...]


@dataclass(frozen=True)
class KnowledgeRebuildResult:
    """Administrative result for source rebuild scheduling."""

    source_id: str
    user_id: int
    organization_id: Optional[int]
    source_type: str
    outbox_ids: tuple[str, ...]
