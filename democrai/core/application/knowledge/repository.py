"""Repository façade for knowledge persistence and projection coordination.

The knowledge repository is the source of truth for sources, items, extracted
entities, extracted relations, outbox jobs, and projection states. Graph and
vector backends are derived projections; they must never become the canonical
storage for the domain. This module exposes a thin façade and delegates the
actual SQL operations to focused helper modules.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import and_, or_

from democrai.core.application.knowledge.records import (
    KnowledgeEntityRecord,
    KnowledgeExtractedItemRecord,
    KnowledgeExtractionRequestRecord,
    KnowledgeChatUploadContextRecord,
    KnowledgeIngestionRequestRecord,
    KnowledgeItemRecord,
    KnowledgeItemClassificationRecord,
    KnowledgeOutboxRecord,
    KnowledgeProjectionStateRecord,
    KnowledgeRelationRecord,
    KnowledgeSourceRecord,
)
from democrai.core.application.knowledge.visibility import normalize_public_flag
from democrai.core.application.observability.service import attach_session_audit_actor
from democrai.core.platform.utils.identity import to_optional_int
from democrai.core.platform.utils.timezone import utc_now_naive

from .repository_helper import read as _read_ops
from .repository_helper import extraction_queue as _extraction_queue_ops
from .repository_helper import extraction_results as _extraction_result_ops
from .repository_helper import media_context as _media_context_ops
from .repository_helper import ingestion_queue as _ingestion_queue_ops
from .repository_helper import metadata_delete as _metadata_delete_ops
from .repository_helper import mutation as _mut_ops
from .repository_helper import outbox as _outbox_ops


def _json_dump(payload: Any) -> str:
    return json.dumps(payload or {}, sort_keys=True, default=str)


def _json_load(payload: Optional[str]) -> dict[str, Any]:
    if not payload:
        return {}
    return json.loads(payload)


def build_content_hash(*parts: str) -> str:
    """Return a stable hash for the semantic content of an ingested item.

    The hash is used to detect meaningful changes across item updates, taking
    into account both raw content and the explicit text chosen for embeddings.
    """

    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


@dataclass(frozen=True)
class ClaimedOutboxJob:
    """Outbox job leased by a projection worker."""

    id: str
    topic: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    payload: dict[str, Any]
    request_context: dict[str, Any]


@dataclass(frozen=True)
class ClaimedExtractionRequest:
    """Extraction request leased by one worker instance."""

    id: str
    media_upload_id: int | None
    user_id: int
    organization_id: int | None
    owner_access_level: int
    module_name: str
    storage_path: str
    original_filename: str
    mime_type: str | None
    source_context: dict[str, Any]
    metadata: dict[str, Any]
    request_context: dict[str, Any]
    is_public: bool
    ingest_enabled: bool
    extractor_id: str | None
    extractor_config: dict[str, Any]
    attempts: int


@dataclass(frozen=True)
class ClaimedIngestionRequest:
    """Ingestion request leased by one worker instance."""

    id: str
    extraction_request_id: str | None
    origin_type: str
    user_id: int
    organization_id: int | None
    source: dict[str, Any]
    items: list[dict[str, Any]]
    request_context: dict[str, Any]
    attempts: int


class KnowledgeRepository:
    """High-level repository used by :class:`KnowledgeService`.

    The class intentionally exposes coarse operations such as ``upsert_item`` or
    ``claim_outbox_jobs`` rather than leaking ORM details into the service
    layer. Each method preserves actor/audit metadata when a request context is
    available.
    """

    KnowledgeEntityRecord = KnowledgeEntityRecord
    KnowledgeExtractedItemRecord = KnowledgeExtractedItemRecord
    KnowledgeExtractionRequestRecord = KnowledgeExtractionRequestRecord
    KnowledgeChatUploadContextRecord = KnowledgeChatUploadContextRecord
    KnowledgeIngestionRequestRecord = KnowledgeIngestionRequestRecord
    KnowledgeItemRecord = KnowledgeItemRecord
    KnowledgeItemClassificationRecord = KnowledgeItemClassificationRecord
    KnowledgeOutboxRecord = KnowledgeOutboxRecord
    KnowledgeProjectionStateRecord = KnowledgeProjectionStateRecord
    KnowledgeRelationRecord = KnowledgeRelationRecord
    KnowledgeSourceRecord = KnowledgeSourceRecord
    ClaimedOutboxJob = ClaimedOutboxJob
    ClaimedExtractionRequest = ClaimedExtractionRequest
    ClaimedIngestionRequest = ClaimedIngestionRequest
    or_ = staticmethod(or_)
    normalize_public_flag = staticmethod(normalize_public_flag)
    _organization_id = staticmethod(to_optional_int)
    _json_dump = staticmethod(_json_dump)
    _json_load = staticmethod(_json_load)
    build_content_hash = staticmethod(build_content_hash)
    utc_now_naive = staticmethod(utc_now_naive)

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def _attach_actor(
        self,
        session: Any,
        *,
        user_id: Optional[int] = None,
        organization_id: Optional[int] = None,
    ) -> None:
        """Attach audit metadata to the SQLAlchemy session.

        The helper merges explicit actor information with the current request
        context so mutations performed by background workers and request-bound
        flows remain traceable in audit tables.
        """

        request_ctx = None
        try:
            from democrai.core.runtime.foundation.app import req_ctx

            request_ctx = req_ctx()
        except LookupError:
            request_ctx = None
        actor_user_id = user_id
        actor_role = None
        actor_organization_id = organization_id
        session_id = None
        request_id = None
        client_ip = None
        channel = None
        if request_ctx is not None:
            actor_user_id = (
                user_id if user_id is not None else request_ctx.user
            )
            actor_role = request_ctx.role
            actor_organization_id = (
                organization_id
                if organization_id is not None
                else request_ctx.organization_id
            )
            session_id = request_ctx.session_key
            request_id = request_ctx.request_id
            client_ip = request_ctx.client_ip
            channel = request_ctx.channel
        attach_session_audit_actor(
            session,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            organization_id=to_optional_int(actor_organization_id),
            session_id=session_id,
            request_id=request_id,
            correlation_id=request_id,
            client_ip=client_ip,
            channel=channel,
        )

    def upsert_source(self, **kwargs):
        return _mut_ops.upsert_source(self, **kwargs)

    def upsert_item(self, **kwargs):
        return _mut_ops.upsert_item(self, **kwargs)

    def replace_entities_and_relations(
        self, *, item_id: str, user_id: int, organization_id: Optional[int], item
    ):
        return self.replace_item_graph(
            item_id=item_id,
            user_id=user_id,
            organization_id=organization_id,
            entities=item.entities,
            relations=item.relations,
        )

    def replace_item_graph(self, **kwargs):
        return _mut_ops.replace_item_graph(self, **kwargs)

    def enqueue_projection_job(self, **kwargs):
        return _mut_ops.enqueue_projection_job(self, **kwargs)

    def enqueue_extraction_request(self, **kwargs):
        return _extraction_queue_ops.enqueue_extraction_request(self, **kwargs)

    def get_extraction_request_metadata(self, request_id: str) -> dict[str, Any]:
        return _extraction_queue_ops.get_extraction_request_metadata(self, request_id)

    def claim_extraction_requests(self, **kwargs):
        return _extraction_queue_ops.claim_extraction_requests(self, **kwargs)

    def complete_extraction_request(self, request_id: str) -> None:
        return _extraction_queue_ops.complete_extraction_request(self, request_id)

    def fail_extraction_request(self, request_id: str, **kwargs) -> None:
        return _extraction_queue_ops.fail_extraction_request(self, request_id, **kwargs)

    def release_extraction_request(self, request_id: str, **kwargs) -> None:
        return _extraction_queue_ops.release_extraction_request(
            self, request_id, **kwargs
        )

    def complete_extraction_with_items(self, **kwargs) -> None:
        return _extraction_result_ops.complete_extraction_with_items(self, **kwargs)

    def enqueue_ingestion_request(self, **kwargs):
        return _ingestion_queue_ops.enqueue_ingestion_request(self, **kwargs)

    def claim_ingestion_requests(self, **kwargs):
        return _ingestion_queue_ops.claim_ingestion_requests(self, **kwargs)

    def build_ingestion_request_payload(self, **kwargs):
        return _ingestion_queue_ops.build_ingestion_request_payload(self, **kwargs)

    def complete_ingestion_request(self, request_id: str) -> None:
        return _ingestion_queue_ops.complete_ingestion_request(self, request_id)

    def fail_ingestion_request(self, request_id: str, **kwargs) -> None:
        return _ingestion_queue_ops.fail_ingestion_request(self, request_id, **kwargs)

    def link_chat_upload_context(self, **kwargs):
        return _media_context_ops.link_chat_upload_context(self, **kwargs)

    def list_chat_upload_contexts(self, **kwargs):
        return _media_context_ops.list_chat_upload_contexts(self, **kwargs)

    def get_item(self, item_id: str):
        return _read_ops.get_item(self, item_id)

    def get_source(self, source_id: str):
        return _read_ops.get_source(self, source_id)

    def get_source_for_owner(self, **kwargs):
        return _read_ops.get_source_for_owner(self, **kwargs)

    def list_sources(self, **kwargs):
        return _read_ops.list_sources(self, **kwargs)

    def list_entities(self, item_id: str):
        return _read_ops.list_entities(self, item_id)

    def list_relations(self, item_id: str):
        return _read_ops.list_relations(self, item_id)

    def list_items_for_source(self, **kwargs):
        return _read_ops.list_items_for_source(self, **kwargs)

    def soft_delete_source(self, **kwargs):
        return _mut_ops.soft_delete_source(self, **kwargs)

    def delete_by_metadata(self, **kwargs):
        return _metadata_delete_ops.delete_by_metadata(self, **kwargs)

    def purge_deleted_item_if_ready(self, **kwargs):
        return _metadata_delete_ops.purge_deleted_item_if_ready(self, **kwargs)

    def set_item_embedding(self, **kwargs):
        return _mut_ops.set_item_embedding(self, **kwargs)

    def upsert_item_classification(self, **kwargs):
        return _mut_ops.upsert_item_classification(self, **kwargs)

    def delete_item_classifications(self, **kwargs):
        return _mut_ops.delete_item_classifications(self, **kwargs)

    def mark_item_status(self, **kwargs):
        return _mut_ops.mark_item_status(self, **kwargs)

    def upsert_projection_state(self, **kwargs):
        return _mut_ops.upsert_projection_state(self, **kwargs)

    def claim_outbox_jobs(self, **kwargs):
        return _outbox_ops.claim_outbox_jobs(self, **kwargs)

    def complete_outbox_job(self, job_id: str) -> None:
        return _outbox_ops.complete_outbox_job(self, job_id)

    def fail_outbox_job(self, job_id: str, **kwargs) -> None:
        return _outbox_ops.fail_outbox_job(self, job_id, **kwargs)

    def search_items(self, **kwargs):
        return _read_ops.search_items(self, **kwargs)

    def get_items_by_ids(self, **kwargs):
        return _read_ops.get_items_by_ids(self, **kwargs)

    def search_items_by_media_file_ids(self, **kwargs):
        return _read_ops.search_items_by_media_file_ids(self, **kwargs)

    def list_visible_source_module_names(self, **kwargs):
        return _read_ops.list_visible_source_module_names(self, **kwargs)

    def _owner_filter(self, model, *, user_id: int, organization_id: int | None):
        """Build the ownership predicate for tenant-bound knowledge records."""
        org_id = self._organization_id(organization_id)
        return and_(
            model.user_id == user_id,
            model.organization_id == org_id,
        )

    def _is_owned_by(
        self,
        row: Any,
        *,
        user_id: int,
        organization_id: int | None,
    ) -> bool:
        """Return whether a loaded tenant-bound row belongs to the owner scope."""
        org_id = self._organization_id(organization_id)
        return (
            row.user_id == user_id
            and row.organization_id == org_id
        )

    def _visibility_filter(
        self, model, *, user_id: int, organization_id: int | None, access_level: int
    ):
        """Build the SQL visibility predicate for records in the current scope.

        The predicate mirrors the same ownership/public-scope model later used
        for vector and knowledge-graph projections.
        """
        own_items = model.user_id == user_id
        if access_level <= 1:
            public_items = and_(
                model.is_public == 1,
                model.owner_access_level > access_level,
            )
            return or_(own_items, public_items)
        if access_level == 2:
            org_id = self._organization_id(organization_id)
            public_items = and_(
                model.organization_id == org_id,
                model.is_public == 1,
                model.owner_access_level > access_level,
            )
            return or_(own_items, public_items)
        return own_items
