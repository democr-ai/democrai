from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class KGEntity(BaseModel):
    name: str
    entity_type: str = "Entity"
    entity_id: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KGRelation(BaseModel):
    relation_type: str
    source_entity_name: str
    target_entity_name: str
    relation_id: Optional[str] = None
    confidence: Optional[float] = None
    weight: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KGExtractionOptions(BaseModel):
    max_entities: int = 24
    max_relations: int = 48
    temperature: float = 0.0
    max_tokens: Optional[int] = None
    entity_labels: List[str] = Field(default_factory=list)
    relation_labels: List[str] = Field(default_factory=list)
    threshold: Optional[float] = None
    top_k: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class ExtractedKnowledgeGraph(BaseModel):
    entities: List[KGEntity] = Field(default_factory=list)
    relations: List[KGRelation] = Field(default_factory=list)
