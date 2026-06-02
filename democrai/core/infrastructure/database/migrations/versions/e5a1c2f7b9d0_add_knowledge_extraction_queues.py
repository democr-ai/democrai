"""add knowledge extraction queues

Revision ID: e5a1c2f7b9d0
Revises: d1b7a38e0c42
Create Date: 2026-05-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5a1c2f7b9d0"
down_revision: Union[str, Sequence[str], None] = "d1b7a38e0c42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_EXISTING_KNOWLEDGE_TABLES = (
    "knowledge_sources",
    "knowledge_items",
    "knowledge_entities",
    "knowledge_relations",
)


def upgrade() -> None:
    for table_name in _EXISTING_KNOWLEDGE_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "metadata",
                new_column_name="metadata_json",
                existing_type=sa.Text(),
                existing_nullable=False,
            )
            batch_op.alter_column(
                "organization_id",
                existing_type=sa.Integer(),
                nullable=True,
                existing_server_default="0",
            )

    op.create_table(
        "knowledge_extraction_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("media_upload_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("owner_access_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("source_context", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ingest_enabled", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("extractor_id", sa.String(length=100), nullable=True),
        sa.Column("extractor_config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_extraction_requests_media_upload_id"), "knowledge_extraction_requests", ["media_upload_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_user_id"), "knowledge_extraction_requests", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_organization_id"), "knowledge_extraction_requests", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_owner_access_level"), "knowledge_extraction_requests", ["owner_access_level"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_module_name"), "knowledge_extraction_requests", ["module_name"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_mime_type"), "knowledge_extraction_requests", ["mime_type"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_ingest_enabled"), "knowledge_extraction_requests", ["ingest_enabled"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_extractor_id"), "knowledge_extraction_requests", ["extractor_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_status"), "knowledge_extraction_requests", ["status"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_priority"), "knowledge_extraction_requests", ["priority"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_available_at"), "knowledge_extraction_requests", ["available_at"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_lease_owner"), "knowledge_extraction_requests", ["lease_owner"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_lease_expires_at"), "knowledge_extraction_requests", ["lease_expires_at"], unique=False)
    op.create_index(op.f("ix_knowledge_extraction_requests_created_at"), "knowledge_extraction_requests", ["created_at"], unique=False)
    op.create_index("ix_knowledge_extraction_requests_claim", "knowledge_extraction_requests", ["status", "available_at", "priority", "created_at"], unique=False)
    op.create_index("ix_knowledge_extraction_requests_scope", "knowledge_extraction_requests", ["user_id", "organization_id", "module_name"], unique=False)

    op.create_table(
        "knowledge_extracted_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_request_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("item_type", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("content_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("ingestion_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("ingested_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_request_id",
            "item_type",
            "ordinal",
            name="uq_knowledge_extracted_items_request_type_ordinal",
        ),
    )
    op.create_index(op.f("ix_knowledge_extracted_items_extraction_request_id"), "knowledge_extracted_items", ["extraction_request_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extracted_items_user_id"), "knowledge_extracted_items", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extracted_items_organization_id"), "knowledge_extracted_items", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_extracted_items_item_type"), "knowledge_extracted_items", ["item_type"], unique=False)
    op.create_index(op.f("ix_knowledge_extracted_items_ordinal"), "knowledge_extracted_items", ["ordinal"], unique=False)
    op.create_index(op.f("ix_knowledge_extracted_items_ingestion_status"), "knowledge_extracted_items", ["ingestion_status"], unique=False)
    op.create_index(op.f("ix_knowledge_extracted_items_created_at"), "knowledge_extracted_items", ["created_at"], unique=False)
    op.create_index("ix_knowledge_extracted_items_ingestion", "knowledge_extracted_items", ["ingestion_status", "created_at"], unique=False)

    op.create_table(
        "knowledge_ingestion_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("extraction_request_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("embedding_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model_id", sa.String(length=255), nullable=True),
        sa.Column("embedding_config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("kg_enabled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("kg_model_id", sa.String(length=255), nullable=True),
        sa.Column("kg_config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_ingestion_requests_extraction_request_id"), "knowledge_ingestion_requests", ["extraction_request_id"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_user_id"), "knowledge_ingestion_requests", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_organization_id"), "knowledge_ingestion_requests", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_embedding_enabled"), "knowledge_ingestion_requests", ["embedding_enabled"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_kg_enabled"), "knowledge_ingestion_requests", ["kg_enabled"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_status"), "knowledge_ingestion_requests", ["status"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_priority"), "knowledge_ingestion_requests", ["priority"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_available_at"), "knowledge_ingestion_requests", ["available_at"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_lease_owner"), "knowledge_ingestion_requests", ["lease_owner"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_lease_expires_at"), "knowledge_ingestion_requests", ["lease_expires_at"], unique=False)
    op.create_index(op.f("ix_knowledge_ingestion_requests_created_at"), "knowledge_ingestion_requests", ["created_at"], unique=False)
    op.create_index("ix_knowledge_ingestion_requests_claim", "knowledge_ingestion_requests", ["status", "available_at", "priority", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_ingestion_requests_claim", table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_created_at"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_lease_expires_at"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_lease_owner"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_available_at"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_priority"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_status"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_kg_enabled"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_embedding_enabled"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_organization_id"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_user_id"), table_name="knowledge_ingestion_requests")
    op.drop_index(op.f("ix_knowledge_ingestion_requests_extraction_request_id"), table_name="knowledge_ingestion_requests")
    op.drop_table("knowledge_ingestion_requests")

    op.drop_index("ix_knowledge_extracted_items_ingestion", table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_created_at"), table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_ingestion_status"), table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_ordinal"), table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_item_type"), table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_organization_id"), table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_user_id"), table_name="knowledge_extracted_items")
    op.drop_index(op.f("ix_knowledge_extracted_items_extraction_request_id"), table_name="knowledge_extracted_items")
    op.drop_table("knowledge_extracted_items")

    op.drop_index("ix_knowledge_extraction_requests_scope", table_name="knowledge_extraction_requests")
    op.drop_index("ix_knowledge_extraction_requests_claim", table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_created_at"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_lease_expires_at"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_lease_owner"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_available_at"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_priority"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_status"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_extractor_id"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_ingest_enabled"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_mime_type"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_module_name"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_owner_access_level"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_organization_id"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_user_id"), table_name="knowledge_extraction_requests")
    op.drop_index(op.f("ix_knowledge_extraction_requests_media_upload_id"), table_name="knowledge_extraction_requests")
    op.drop_table("knowledge_extraction_requests")

    for table_name in _EXISTING_KNOWLEDGE_TABLES:
        with op.batch_alter_table(table_name) as batch_op:
            batch_op.alter_column(
                "organization_id",
                existing_type=sa.Integer(),
                nullable=False,
                server_default="0",
            )
            batch_op.alter_column(
                "metadata_json",
                new_column_name="metadata",
                existing_type=sa.Text(),
                existing_nullable=False,
            )
