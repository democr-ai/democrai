from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Any, Optional

from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.app import req_ctx


class Knowledge:
    """Expose document extraction and ingestion helpers to modules."""

    def __init__(self, sdk) -> None:
        """Create the knowledge facade for the current SDK instance."""
        self.sdk = sdk

    def _request_identity(self, *, operation: str) -> tuple[int, int | None, int]:
        """Return the current request identity for scoped knowledge operations."""
        try:
            request_context = req_ctx()
        except LookupError as exc:
            raise RuntimeError(
                f"knowledge_{operation}_missing_request_context"
            ) from exc
        user_id = request_context.user
        if user_id is None:
            raise RuntimeError(f"knowledge_{operation}_missing_user_id")
        organization_id = request_context.organization_id
        access_level = request_context.access_level
        return user_id, organization_id, access_level if access_level is not None else 3

    def get_runtime_config(self) -> dict[str, Any]:
        """Return the persisted knowledge runtime configuration."""
        from democrai.core.application.knowledge.configuration import (
            get_knowledge_runtime_config,
        )

        return get_knowledge_runtime_config()

    def runtime_config_form_model(self) -> list[dict[str, Any]]:
        """Return the UI form model for configuring knowledge runtime."""
        from democrai.core.application.knowledge.configuration import (
            knowledge_config_form_model,
        )

        return knowledge_config_form_model()

    def update_runtime_config(
        self,
        payload: dict[str, Any],
        *,
        confirm_embedding_model_change: bool = False,
    ) -> dict[str, Any]:
        """Persist the knowledge runtime configuration."""
        from democrai.core.application.knowledge.configuration import (
            update_knowledge_runtime_config,
        )
        from democrai.core.application.knowledge.runtime_reload import (
            reload_knowledge_runtime,
        )

        config = update_knowledge_runtime_config(
            payload,
            confirm_embedding_model_change=confirm_embedding_model_change,
        )
        reload_knowledge_runtime()
        return config

    def count_existing_embeddings(self) -> int:
        """Return how many knowledge items already store embedding vectors."""
        from democrai.core.application.knowledge.configuration import (
            count_existing_embeddings,
        )

        return count_existing_embeddings()

    def delete_source(self, source_id: str) -> tuple[str, ...]:
        """Soft-delete one owned knowledge source and enqueue projection cleanup."""
        resolved_source_id = str(source_id or "").strip()
        if not resolved_source_id:
            raise ValueError("source_id is required")
        knowledge_service = getattr(app_ctx(), "knowledge_service", None)
        if knowledge_service is None:
            raise RuntimeError("knowledge_service_unavailable")
        user_id, organization_id, _access_level = self._request_identity(
            operation="source_delete"
        )
        return knowledge_service.delete_source(
            user_id=user_id,
            organization_id=organization_id,
            source_id=resolved_source_id,
        )

    def delete_by_metadata(
        self,
        filters: dict[str, Any],
        *,
        force: bool = False,
    ) -> dict[str, Any]:
        """Delete owned knowledge records matching module-scoped metadata."""
        caller_filters = dict(filters or {})
        if not caller_filters:
            raise ValueError("metadata filters are required")
        if "module_name" in caller_filters:
            raise ValueError("module_name is injected by the SDK")
        module_name = str(getattr(self.sdk, "module_name", "") or "").strip()
        if not module_name:
            raise RuntimeError("knowledge_metadata_delete_missing_module_name")
        metadata_filters = {"module_name": module_name, **caller_filters}
        user_id, organization_id, _access_level = self._request_identity(
            operation="metadata_delete"
        )
        knowledge_service = getattr(app_ctx(), "knowledge_service", None)
        if knowledge_service is not None:
            return knowledge_service.delete_by_metadata(
                user_id=user_id,
                organization_id=organization_id,
                metadata_filters=metadata_filters,
                force=force,
            )

        db = getattr(app_ctx(), "db", None)
        if db is None:
            raise RuntimeError("knowledge_repository_unavailable")
        from democrai.core.application.knowledge.repository import KnowledgeRepository
        from democrai.core.application.knowledge.service_helper.ingestion import (
            delete_by_metadata_with_repository,
        )

        repository = KnowledgeRepository(db.get_session)
        return delete_by_metadata_with_repository(
            repository,
            user_id=user_id,
            organization_id=organization_id,
            metadata_filters=metadata_filters,
            force=force,
        )

    def get_extraction_status(self, request_id: str) -> dict[str, Any]:
        """Return scoped status for one durable extraction request."""
        from democrai.core.application.knowledge.extraction_access import (
            get_extraction_status,
        )

        resolved_request_id = str(request_id or "").strip()
        if not resolved_request_id:
            raise ValueError("request_id is required")
        user_id, organization_id, _access_level = self._request_identity(
            operation="extraction_status"
        )
        status = get_extraction_status(
            request_id=resolved_request_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if status is None:
            raise RuntimeError("knowledge_extraction_request_not_found")
        return status

    def list_extraction_statuses(self, request_ids: list[str]) -> dict[str, Any]:
        """Return scoped status records for multiple extraction requests."""
        from democrai.core.application.knowledge.extraction_access import (
            list_extraction_statuses,
        )

        user_id, organization_id, _access_level = self._request_identity(
            operation="extraction_status"
        )
        return list_extraction_statuses(
            request_ids=request_ids,
            user_id=user_id,
            organization_id=organization_id,
        )

    def get_extracted_document(self, request_id: str) -> dict[str, Any]:
        """Return the complete extracted markdown document for one request."""
        from democrai.core.application.knowledge.extraction_access import (
            get_extracted_document,
        )

        resolved_request_id = str(request_id or "").strip()
        if not resolved_request_id:
            raise ValueError("request_id is required")
        user_id, organization_id, _access_level = self._request_identity(
            operation="extracted_document"
        )
        payload = get_extracted_document(
            request_id=resolved_request_id,
            user_id=user_id,
            organization_id=organization_id,
        )
        if payload is None:
            raise RuntimeError("knowledge_extraction_request_not_found")
        if str(payload.get("extraction_status") or "") != "completed":
            raise RuntimeError("knowledge_extraction_request_not_completed")
        if not str(payload.get("markdown_content") or "").strip():
            raise RuntimeError("knowledge_extracted_document_markdown_missing")
        return payload

    def read_document_blocks(
        self,
        *,
        request_id: str,
        max_chars: int,
        blocks: list[int] | None = None,
        kind: str = "chunk",
    ) -> dict[str, Any]:
        """Read an extracted document for analysis within the caller scope.

        Every result carries ``counts`` (items per type, e.g. how many tables).
        Index mode (``blocks`` omitted) returns the whole document when it fits
        ``max_chars`` (for ``kind="chunk"``), otherwise the index of ``kind``
        items. Block mode returns the requested ordinals up to ``max_chars``
        without silent truncation. ``kind`` selects what to read: ``chunk``
        (default), ``table``, ``formula`` or ``image``.
        """
        from democrai.core.application.knowledge.extraction_access import (
            list_extracted_blocks,
        )

        resolved_request_id = str(request_id or "").strip()
        if not resolved_request_id:
            raise ValueError("request_id is required")
        user_id, organization_id, _access_level = self._request_identity(
            operation="extracted_blocks"
        )
        payload = list_extracted_blocks(
            request_id=resolved_request_id,
            user_id=user_id,
            organization_id=organization_id,
            max_chars=max_chars,
            blocks=blocks,
            kind=kind,
        )
        if payload is None:
            raise RuntimeError("knowledge_extraction_request_not_found")
        return payload

    def list_items_for_summary(
        self,
        *,
        request_id: str,
        item_type: str = "chunk",
    ) -> list[dict[str, Any]]:
        """Items of ``item_type`` in order with text and cached summary state,
        scoped to the caller. ``fresh`` marks items whose summary is up to date."""
        from democrai.core.application.knowledge.extraction_access import (
            list_extracted_items_for_summary,
        )

        resolved_request_id = str(request_id or "").strip()
        if not resolved_request_id:
            raise ValueError("request_id is required")
        user_id, organization_id, _access_level = self._request_identity(
            operation="extracted_summary"
        )
        return list_extracted_items_for_summary(
            request_id=resolved_request_id,
            user_id=user_id,
            organization_id=organization_id,
            item_type=item_type,
        )

    def store_item_summary(self, *, item_id: str, summary: str) -> bool:
        """Persist a summary on one extracted item (cached, hash-invalidated)."""
        from democrai.core.application.knowledge.extraction_access import (
            store_item_summary,
        )

        user_id, organization_id, _access_level = self._request_identity(
            operation="extracted_summary_write"
        )
        return store_item_summary(
            item_id=item_id,
            user_id=user_id,
            organization_id=organization_id,
            summary=summary,
        )

    def search_extracted_items(
        self,
        *,
        query_text: str,
        limit: int = 8,
        extraction_request_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search extracted markdown/chunks inside the current request scope."""
        from democrai.core.application.knowledge.extraction_access import (
            search_extracted_items,
        )

        resolved_query = str(query_text or "").strip()
        if not resolved_query:
            raise ValueError("query_text is required")
        user_id, organization_id, access_level = self._request_identity(
            operation="extracted_item_search"
        )
        return search_extracted_items(
            query_text=resolved_query,
            user_id=user_id,
            organization_id=organization_id,
            access_level=access_level,
            limit=limit,
            extraction_request_ids=extraction_request_ids,
        )

    async def retrieve(
        self,
        *,
        query_text: str,
        query_vector: list[float] | None = None,
        top_k: int = 8,
        lexical_limit: int = 8,
        graph_neighbors_limit: int = 4,
        metadata_filters: Optional[dict[str, Any]] = None,
    ):
        """Run scoped knowledge retrieval for the current request user."""
        from democrai.core.application.knowledge.models import KnowledgeRetrieveRequest

        user_id, organization_id, access_level = self._request_identity(
            operation="retrieval"
        )
        resolved_query_text = str(query_text or "").strip()
        if not resolved_query_text:
            raise ValueError("query_text is required")
        request = KnowledgeRetrieveRequest(
            user_id=user_id,
            organization_id=organization_id,
            access_level=access_level,
            query_text=resolved_query_text,
            query_vector=query_vector,
            top_k=top_k,
            lexical_limit=lexical_limit,
            graph_neighbors_limit=graph_neighbors_limit,
            metadata_filters=metadata_filters if metadata_filters is not None else {},
        )
        knowledge_service = getattr(app_ctx(), "knowledge_service", None)
        if (
            os.environ.get("DEMOCRAI_KNOWLEDGE_QUERY_SERVICE") == "1"
            and knowledge_service is not None
        ):
            return await knowledge_service.retrieve(request)
        from democrai.core.application.knowledge.query.client import (
            KnowledgeQueryClient,
        )

        client = KnowledgeQueryClient()
        try:
            return await client.retrieve(request)
        finally:
            await client.close()

    def extract_document_data(
        self,
        path: str,
        force_path_resolved: bool = False,
        chunker_override: Optional[str] = None,
        chunker_max_tokens: Optional[int] = None,
        ocr_enabled: Optional[bool] = None,
    ):
        """Extract structured document data from a local or materialized path."""
        if force_path_resolved:
            raise RuntimeError(
                "legacy media path resolution was removed from the public SDK; "
                "rewrite this extraction flow against the new media API"
            )
        file_path = Path(path)

        extracted = self.sdk.extractors.extract(
            path=str(file_path),
            mime_type=self._guess_mime_type(str(file_path)),
            config={
                "chunker": chunker_override,
                "chunker_max_tokens": chunker_max_tokens,
                "ocr_enabled": ocr_enabled,
            },
        )
        if extracted is None:
            raise RuntimeError(
                "registered_extractor_not_found "
                f"path={str(file_path)} "
                f"mime_type={self._guess_mime_type(str(file_path)) or '-'}"
            )
        return extracted

    def resolve_registered_extractor(
        self,
        *,
        path: str | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve the active extractor through ``sdk.extractors``.

        :param path: Optional filesystem or media-backed path.
        :param filename: Optional filename.
        :param mime_type: Optional mime type.
        :return: The resolved extractor payload or ``None``.
        """
        resolved_path = str(path or "").strip() or None
        resolved_filename = str(filename or "").strip() or None
        resolved_mime_type = str(mime_type or "").strip().lower() or None
        return self.sdk.extractors.resolve(
            path=resolved_path,
            filename=resolved_filename,
            mime_type=resolved_mime_type,
        )

    def extract_with_registered_extractor(
        self,
        *,
        path: str | None = None,
        data: bytes | None = None,
        filename: str | None = None,
        mime_type: str | None = None,
        config: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any] | None:
        """Run the active registered extractor through ``sdk.extractors``.

        :param path: Optional filesystem or media-backed path.
        :param data: Optional in-memory payload.
        :param filename: Optional filename for in-memory payloads.
        :param mime_type: Optional mime type.
        :param config: Optional runtime overrides passed to the extractor.
        :return: The extraction payload or ``None``.
        """
        resolved_path = str(path or "").strip() or None
        resolved_filename = str(filename or "").strip() or None
        resolved_mime_type = str(mime_type or "").strip().lower() or None
        return self.sdk.extractors.extract(
            path=resolved_path,
            data=bytes(data) if data is not None else None,
            filename=resolved_filename,
            mime_type=resolved_mime_type,
            config=config,
        )

    def enqueue_extraction(
        self,
        *,
        storage_path: str,
        filename: str | None = None,
        mime_type: str | None = None,
        metadata: Optional[dict[str, Any]] = None,
        source_context: Optional[dict[str, Any]] = None,
        is_public: bool = False,
        ingest: bool = True,
        priority: int = 0,
    ) -> str:
        """Create a durable extraction request for an existing media object."""
        from democrai.core.application.services.media_uploads import (
            can_access_media_upload,
            enqueue_media_extraction,
        )
        from democrai.core.infrastructure.database.media_uploads import (
            get_media_upload_by_storage_path,
        )

        user_id, organization_id, owner_access_level = self._request_identity(
            operation="extraction"
        )
        resolved_storage_path = str(storage_path or "").strip()
        if not resolved_storage_path:
            raise ValueError("storage_path is required")
        upload = get_media_upload_by_storage_path(storage_path=resolved_storage_path)
        if upload is None:
            raise RuntimeError("knowledge_extraction_media_upload_not_found")
        if not can_access_media_upload(
            owner_user_id=upload.owner_user_id,
            organization_id=to_optional_int(upload.organization_id),
            user_id=user_id,
            user_access_level=owner_access_level,
            user_organization_id=organization_id,
        ):
            raise PermissionError("knowledge_extraction_media_upload_denied")
        resolved_filename = (
            str(filename or "").strip()
            or str(upload.original_filename or "").strip()
            or Path(resolved_storage_path).name
            or "media.bin"
        )
        resolved_mime_type = (
            str(mime_type or "").strip()
            or str(upload.content_type or "").strip()
            or self._guess_mime_type(resolved_filename)
        )
        resolved_context = {
            "kind": "manual_sdk",
            "module_name": self.sdk.module_name,
        }
        if source_context is not None:
            resolved_context.update(source_context)
        resolved_context.setdefault("file_id", str(upload.file_id))
        return enqueue_media_extraction(
            media_upload_id=upload.id,
            module_name=self.sdk.module_name,
            storage_path=resolved_storage_path,
            original_filename=resolved_filename,
            mime_type=resolved_mime_type,
            user_id=user_id,
            organization_id=organization_id,
            owner_access_level=owner_access_level,
            source_context=resolved_context,
            metadata=metadata,
            is_public=is_public,
            ingest_enabled=ingest,
            priority=priority,
        )

    def ingest_document(
        self,
        *,
        path: str,
        source_type: str = "document",
        title: Optional[str] = None,
        external_ref: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_public: bool = False,
        persist: bool = True,
    ):
        """Ingest a document that already exists at a readable path."""
        ingestion_facade = getattr(app_ctx(), "knowledge_ingestion", None)
        if ingestion_facade is None:
            raise RuntimeError("knowledge_ingestion_unavailable")

        user_id, organization_id, _access_level = self._request_identity(
            operation="ingestion"
        )

        resolved_path = str(path or "").strip()
        if not resolved_path:
            raise ValueError("path is required")

        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("module_name", self.sdk.module_name)

        return ingestion_facade.ingest_document(
            user_id=user_id,
            organization_id=organization_id,
            path=resolved_path,
            source_type=source_type,
            title=title,
            external_ref=external_ref,
            metadata=merged_metadata,
            is_public=is_public,
            persist=persist,
        )

    def ingest_document_bytes(
        self,
        *,
        filename: str,
        data: bytes,
        source_type: str = "document",
        title: Optional[str] = None,
        external_ref: Optional[str] = None,
        media_uri: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        is_public: bool = False,
        persist: bool = True,
    ):
        """Ingest an in-memory document payload as bytes."""
        ingestion_facade = getattr(app_ctx(), "knowledge_ingestion", None)
        if ingestion_facade is None:
            raise RuntimeError("knowledge_ingestion_unavailable")

        user_id, organization_id, _access_level = self._request_identity(
            operation="ingestion"
        )

        resolved_filename = str(filename or "").strip()
        if not resolved_filename:
            raise ValueError("filename is required")
        if not isinstance(data, (bytes, bytearray)):
            raise ValueError("data must be bytes")

        merged_metadata = dict(metadata or {})
        merged_metadata.setdefault("module_name", self.sdk.module_name)

        return ingestion_facade.ingest_document_bytes(
            user_id=user_id,
            organization_id=organization_id,
            filename=resolved_filename,
            data=bytes(data),
            source_type=source_type,
            title=title,
            external_ref=external_ref,
            media_uri=media_uri,
            metadata=merged_metadata,
            is_public=is_public,
            persist=persist,
        )

    @staticmethod
    def _guess_mime_type(path_or_name: str) -> str | None:
        guessed, _ = mimetypes.guess_type(str(path_or_name or ""))
        return str(guessed or "").strip().lower() or None
