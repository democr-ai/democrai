"""ORM records backing the canonical knowledge database schema.

These tables store the source-of-truth representation for ingested knowledge
before it is projected into vector or graph stores. Projection status is kept
explicitly so asynchronous workers can rebuild or delete downstream state
without losing the original semantic content.
"""

from __future__ import annotations

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Float
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import text
from sqlalchemy import Text
from sqlalchemy import UniqueConstraint
from sqlalchemy import String

from democrai.core.infrastructure.database.models import Base
from democrai.core.platform.utils.timezone import utc_now_naive


class KnowledgeSourceRecord(Base):
    """Persistent source grouping a family of knowledge items."""
    __tablename__ = "knowledge_sources"

    id = Column(String(36), primary_key=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    source_type = Column(String(64), nullable=False, index=True)
    title = Column(String(512), nullable=True)
    mime_type = Column(String(255), nullable=True)
    external_ref = Column(String(512), nullable=True)
    media_uri = Column(String(1024), nullable=True)
    checksum = Column(String(255), nullable=True)
    owner_access_level = Column(Integer, nullable=False, default=3, index=True)
    is_public = Column(Integer, nullable=False, default=0, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    version = Column(Integer, nullable=False, default=1)
    status = Column(String(32), nullable=False, default="active", index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "ix_knowledge_sources_scope_type",
            "user_id",
            "organization_id",
            "source_type",
        ),
    )


class KnowledgeItemRecord(Base):
    """Persistent knowledge item used for retrieval and projection."""
    __tablename__ = "knowledge_items"

    id = Column(String(36), primary_key=True)
    source_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(64), nullable=False, index=True)
    title = Column(String(512), nullable=True)
    content = Column(Text, nullable=False)
    summary = Column(Text, nullable=True)
    embedding_text = Column(Text, nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    media_file_id = Column(String(64), nullable=True, index=True)
    external_ref = Column(String(512), nullable=True)
    owner_access_level = Column(Integer, nullable=False, default=3, index=True)
    is_public = Column(Integer, nullable=False, default=0, index=True)
    content_hash = Column(String(64), nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    vector_status = Column(String(32), nullable=False, default="pending", index=True)
    kg_status = Column(String(32), nullable=False, default="pending", index=True)
    embedding_model_id = Column(String(255), nullable=True)
    embedding_model_version = Column(String(255), nullable=True)
    embedding_dim = Column(Integer, nullable=True)
    embedding_vector_json = Column(Text, nullable=True)
    embedding_updated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "ix_knowledge_items_scope_kind",
            "user_id",
            "organization_id",
            "kind",
        ),
        Index(
            "ix_knowledge_items_scope_source",
            "user_id",
            "organization_id",
            "source_id",
        ),
    )


class KnowledgeEntityRecord(Base):
    """Entity extracted or supplied for a specific knowledge item."""
    __tablename__ = "knowledge_entities"

    id = Column(String(36), primary_key=True)
    item_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    entity_type = Column(String(64), nullable=False, index=True)
    canonical_name = Column(String(512), nullable=False, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    confidence = Column(Float, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index(
            "ix_knowledge_entities_scope_name",
            "user_id",
            "organization_id",
            "canonical_name",
        ),
    )


class KnowledgeRelationRecord(Base):
    """Directed relation extracted between entities inside an item."""
    __tablename__ = "knowledge_relations"

    id = Column(String(36), primary_key=True)
    item_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    relation_type = Column(String(64), nullable=False, index=True)
    source_entity_id = Column(String(36), nullable=False, index=True)
    target_entity_id = Column(String(36), nullable=False, index=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    confidence = Column(Float, nullable=True)
    weight = Column(Float, nullable=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "relation_type",
            "source_entity_id",
            "target_entity_id",
            name="uq_knowledge_relations_active",
        ),
    )


class KnowledgeItemClassificationRecord(Base):
    """Classification result derived for one knowledge item and model."""
    __tablename__ = "knowledge_item_classifications"

    id = Column(String(36), primary_key=True)
    item_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    model_registry_id = Column(Integer, nullable=False, index=True)
    model_version = Column(String(255), nullable=True)
    label = Column(String(255), nullable=False, index=True)
    score = Column(Float, nullable=True)
    scores_json = Column(Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="synced", index=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint(
            "item_id",
            "model_registry_id",
            name="uq_knowledge_item_classification_model",
        ),
        Index(
            "ix_knowledge_item_classifications_scope_label",
            "user_id",
            "organization_id",
            "label",
        ),
    )


class KnowledgeOutboxRecord(Base):
    """Outbox entry driving asynchronous vector and KG projections."""
    __tablename__ = "knowledge_outbox"

    id = Column(String(36), primary_key=True)
    topic = Column(String(64), nullable=False, index=True)
    dedupe_key = Column(String(255), nullable=False, unique=True)
    aggregate_type = Column(String(64), nullable=False, index=True)
    aggregate_id = Column(String(36), nullable=False, index=True)
    aggregate_version = Column(Integer, nullable=False)
    payload_json = Column("payload", Text, nullable=False, default="{}")
    request_context_json = Column("request_context", Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="pending", index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    lease_owner = Column(String(255), nullable=True, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)


class KnowledgeExtractionRequestRecord(Base):
    """Queue entry for extracting structured content from uploaded media."""
    __tablename__ = "knowledge_extraction_requests"

    id = Column(String(36), primary_key=True)
    media_upload_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    owner_access_level = Column(Integer, nullable=False, default=3, index=True)
    module_name = Column(String(255), nullable=False, index=True)
    storage_path = Column(Text, nullable=False)
    original_filename = Column(String(512), nullable=False)
    mime_type = Column(String(255), nullable=True, index=True)
    source_context_json = Column("source_context", Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")
    request_context_json = Column("request_context", Text, nullable=False, default="{}")
    is_public = Column(Integer, nullable=False, default=0, index=True)
    ingest_enabled = Column(Integer, nullable=False, default=1, index=True)
    extractor_id = Column(String(100), nullable=True, index=True)
    extractor_config_json = Column("extractor_config", Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="pending", index=True)
    priority = Column(Integer, nullable=False, default=0, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    lease_owner = Column(String(255), nullable=True, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        Index(
            "ix_knowledge_extraction_requests_claim",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
        Index(
            "ix_knowledge_extraction_requests_scope",
            "user_id",
            "organization_id",
            "module_name",
        ),
    )


class KnowledgeChatUploadContextRecord(Base):
    """Pipeline context associated with an uploaded media file."""
    __tablename__ = "knowledge_chat_upload_contexts"

    id = Column(String(36), primary_key=True)
    file_id = Column(String(64), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    owner_access_level = Column(Integer, nullable=False, default=3, index=True)
    pipeline_id = Column(String(255), nullable=False, index=True)
    context_json = Column("context", Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        Index(
            "uq_knowledge_chat_upload_contexts_file_user_org_pipeline",
            "file_id",
            "user_id",
            "organization_id",
            "pipeline_id",
            unique=True,
            postgresql_where=text("organization_id IS NOT NULL"),
            sqlite_where=text("organization_id IS NOT NULL"),
        ),
        Index(
            "uq_knowledge_chat_upload_contexts_file_user_pipeline_no_org",
            "file_id",
            "user_id",
            "pipeline_id",
            unique=True,
            postgresql_where=text("organization_id IS NULL"),
            sqlite_where=text("organization_id IS NULL"),
        ),
    )


class KnowledgeExtractedItemRecord(Base):
    """Extracted item persisted before optional knowledge ingestion."""
    __tablename__ = "knowledge_extracted_items"

    id = Column(String(36), primary_key=True)
    extraction_request_id = Column(String(36), nullable=False, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    item_type = Column(String(64), nullable=False, index=True)
    ordinal = Column(Integer, nullable=False, default=0, index=True)
    title = Column(String(512), nullable=True)
    content_text = Column(Text, nullable=True)
    content_json = Column(Text, nullable=False, default="{}")
    metadata_json = Column(Text, nullable=False, default="{}")
    is_public = Column(Integer, nullable=False, default=0, index=True)
    ingestion_status = Column(String(32), nullable=False, default="pending", index=True)
    ingested_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint(
            "extraction_request_id",
            "item_type",
            "ordinal",
            name="uq_knowledge_extracted_items_request_type_ordinal",
        ),
        Index(
            "ix_knowledge_extracted_items_ingestion",
            "ingestion_status",
            "created_at",
        ),
    )


class KnowledgeIngestionRequestRecord(Base):
    """Queue entry for ingesting extracted items into knowledge projections."""
    __tablename__ = "knowledge_ingestion_requests"

    id = Column(String(36), primary_key=True)
    extraction_request_id = Column(String(36), nullable=True, index=True)
    origin_type = Column(String(64), nullable=False, default="extraction", index=True)
    user_id = Column(Integer, nullable=False, index=True)
    organization_id = Column(Integer, nullable=True, index=True)
    source_json = Column("source", Text, nullable=False, default="{}")
    items_json = Column("items", Text, nullable=False, default="[]")
    request_context_json = Column("request_context", Text, nullable=False, default="{}")
    embedding_enabled = Column(Integer, nullable=False, default=0, index=True)
    embedding_model_id = Column(String(255), nullable=True)
    embedding_config_json = Column("embedding_config", Text, nullable=False, default="{}")
    kg_enabled = Column(Integer, nullable=False, default=0, index=True)
    kg_model_id = Column(String(255), nullable=True)
    kg_config_json = Column("kg_config", Text, nullable=False, default="{}")
    status = Column(String(32), nullable=False, default="pending", index=True)
    priority = Column(Integer, nullable=False, default=0, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    available_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    lease_owner = Column(String(255), nullable=True, index=True)
    lease_expires_at = Column(DateTime, nullable=True, index=True)
    last_error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        Index(
            "ix_knowledge_ingestion_requests_claim",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
    )


class KnowledgeProjectionStateRecord(Base):
    """Last known synchronization state for a downstream projection."""
    __tablename__ = "knowledge_projection_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    aggregate_type = Column(String(64), nullable=False)
    aggregate_id = Column(String(36), nullable=False)
    projection = Column(String(64), nullable=False)
    backend = Column(String(64), nullable=False)
    backend_key = Column(String(512), nullable=True)
    synced_version = Column(Integer, nullable=False, default=0)
    status = Column(String(32), nullable=False, default="pending", index=True)
    last_error = Column(Text, nullable=True)
    synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            "projection",
            "backend",
            name="uq_knowledge_projection_state",
        ),
    )
