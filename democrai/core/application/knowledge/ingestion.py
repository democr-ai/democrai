"""Facade used by callers that want to ingest files or raw bytes as knowledge."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from democrai.core.application.knowledge.service import KnowledgeService
from democrai.core.runtime.foundation.app import app_ctx


@dataclass(frozen=True)
class KnowledgeIngestionOutput:
    """Returned by ingest_document / ingest_document_bytes.

    Always contains the extracted items.
    source_id / item_ids / outbox_ids are populated only when persist=True.
    """

    extracted_items: tuple[Any, ...] = field(default_factory=tuple)
    source_id: str | None = None
    item_ids: tuple[str, ...] = field(default_factory=tuple)
    outbox_ids: tuple[str, ...] = field(default_factory=tuple)


class KnowledgeIngestionFacade:
    """High-level ingestion entrypoint for files and in-memory payloads."""

    def __init__(
        self,
        *,
        service: KnowledgeService,
    ) -> None:
        self.service = service

    @staticmethod
    def _log_info(message: str, *args: Any) -> None:
        try:
            logger = getattr(app_ctx(), "logger", None)
            if logger is None:
                return
            logger.info(message, *args)
        except Exception:
            return

    @staticmethod
    def _raise_ingestion_placeholder(*, operation: str) -> None:
        raise RuntimeError(
            "knowledge_ingestion_extractor_placeholder "
            f"operation={operation} "
            "reason=legacy_knowledge_extractors_reference_removed"
        )

    def ingest_document(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        path: str | Path,
        source_type: str = "document",
        title: str | None = None,
        external_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_public: bool = False,
        persist: bool = True,
    ) -> KnowledgeIngestionOutput:
        self._raise_ingestion_placeholder(operation="ingest_document")

    def ingest_document_bytes(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        filename: str,
        data: bytes,
        source_type: str = "document",
        title: str | None = None,
        external_ref: str | None = None,
        media_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        is_public: bool = False,
        persist: bool = True,
    ) -> KnowledgeIngestionOutput:
        del (
            user_id,
            organization_id,
            filename,
            data,
            source_type,
            title,
            external_ref,
            media_uri,
            metadata,
            is_public,
            persist,
        )
        self._raise_ingestion_placeholder(operation="ingest_document_bytes")

    def delete_source(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        source_id: str,
    ) -> tuple[str, ...]:
        """Schedule deletion of all projections associated with a source."""
        return self.service.delete_source(
            user_id=user_id,
            organization_id=organization_id,
            source_id=source_id,
        )

    def rebuild_source(
        self,
        *,
        user_id: int,
        organization_id: int | None,
        source_id: str,
    ) -> tuple[str, ...]:
        """Schedule re-projection of every non-deleted item in a source."""
        return self.service.rebuild_source(
            user_id=user_id,
            organization_id=organization_id,
            source_id=source_id,
        )
