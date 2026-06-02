from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from democrai.core.application.ai.engine.schemas.kg import (
    ExtractedKnowledgeGraph,
    KGExtractionOptions,
)


def kg_extraction_options(value: Any) -> KGExtractionOptions:
    if value is None:
        return KGExtractionOptions()
    if isinstance(value, KGExtractionOptions):
        return value
    if isinstance(value, dict):
        return KGExtractionOptions(**value)
    raise TypeError("kg_extraction_options_expected")


class KGProvider(ABC):
    """Knowledge graph extraction capability contract."""

    def __init__(self, config: dict):
        self.config = config
        self.model_name = config.get("model")
        self.model_revision = config.get("model_revision")

    async def extract_triples(
        self,
        *,
        kind: str,
        title: str | None = None,
        summary: str | None = None,
        content: str,
        options: KGExtractionOptions | dict[str, Any] | None = None,
    ) -> ExtractedKnowledgeGraph:
        return await self._extract_triples(
            kind=kind,
            title=title,
            summary=summary,
            content=content,
            options=kg_extraction_options(options),
        )

    @abstractmethod
    async def _extract_triples(
        self,
        *,
        kind: str,
        title: str | None,
        summary: str | None,
        content: str,
        options: KGExtractionOptions,
    ) -> ExtractedKnowledgeGraph:
        raise NotImplementedError
