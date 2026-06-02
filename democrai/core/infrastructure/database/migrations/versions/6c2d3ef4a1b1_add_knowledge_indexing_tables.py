"""add knowledge indexing tables

Revision ID: 6c2d3ef4a1b1
Revises: 3b9a2f8d1c44
Create Date: 2026-03-04 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6c2d3ef4a1b1"
down_revision: Union[str, Sequence[str], None] = "3b9a2f8d1c44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("mime_type", sa.String(length=255), nullable=True),
        sa.Column("external_ref", sa.String(length=512), nullable=True),
        sa.Column("media_uri", sa.String(length=1024), nullable=True),
        sa.Column("checksum", sa.String(length=255), nullable=True),
        sa.Column("owner_access_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_public", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_sources_user_id"), "knowledge_sources", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_sources_organization_id"), "knowledge_sources", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_sources_source_type"), "knowledge_sources", ["source_type"], unique=False)
    op.create_index(op.f("ix_knowledge_sources_owner_access_level"), "knowledge_sources", ["owner_access_level"], unique=False)
    op.create_index(op.f("ix_knowledge_sources_is_public"), "knowledge_sources", ["is_public"], unique=False)
    op.create_index("ix_knowledge_sources_scope_type", "knowledge_sources", ["user_id", "organization_id", "source_type"], unique=False)

    op.create_table(
        "knowledge_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("embedding_text", sa.Text(), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("external_ref", sa.String(length=512), nullable=True),
        sa.Column("owner_access_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_public", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("vector_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("kg_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("embedding_model_id", sa.String(length=255), nullable=True),
        sa.Column("embedding_model_version", sa.String(length=255), nullable=True),
        sa.Column("embedding_dim", sa.Integer(), nullable=True),
        sa.Column("embedding_vector_json", sa.Text(), nullable=True),
        sa.Column("embedding_updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_items_source_id"), "knowledge_items", ["source_id"], unique=False)
    op.create_index(op.f("ix_knowledge_items_user_id"), "knowledge_items", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_items_organization_id"), "knowledge_items", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_items_kind"), "knowledge_items", ["kind"], unique=False)
    op.create_index(op.f("ix_knowledge_items_owner_access_level"), "knowledge_items", ["owner_access_level"], unique=False)
    op.create_index(op.f("ix_knowledge_items_is_public"), "knowledge_items", ["is_public"], unique=False)
    op.create_index(op.f("ix_knowledge_items_content_hash"), "knowledge_items", ["content_hash"], unique=False)
    op.create_index(op.f("ix_knowledge_items_vector_status"), "knowledge_items", ["vector_status"], unique=False)
    op.create_index(op.f("ix_knowledge_items_kg_status"), "knowledge_items", ["kg_status"], unique=False)
    op.create_index("ix_knowledge_items_scope_kind", "knowledge_items", ["user_id", "organization_id", "kind"], unique=False)
    op.create_index("ix_knowledge_items_scope_source", "knowledge_items", ["user_id", "organization_id", "source_id"], unique=False)

    op.create_table(
        "knowledge_entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("canonical_name", sa.String(length=512), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_knowledge_entities_item_id"), "knowledge_entities", ["item_id"], unique=False)
    op.create_index(op.f("ix_knowledge_entities_user_id"), "knowledge_entities", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_entities_organization_id"), "knowledge_entities", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_entities_entity_type"), "knowledge_entities", ["entity_type"], unique=False)
    op.create_index(op.f("ix_knowledge_entities_canonical_name"), "knowledge_entities", ["canonical_name"], unique=False)
    op.create_index("ix_knowledge_entities_scope_name", "knowledge_entities", ["user_id", "organization_id", "canonical_name"], unique=False)

    op.create_table(
        "knowledge_relations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("relation_type", sa.String(length=64), nullable=False),
        sa.Column("source_entity_id", sa.String(length=36), nullable=False),
        sa.Column("target_entity_id", sa.String(length=36), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "item_id",
            "relation_type",
            "source_entity_id",
            "target_entity_id",
            name="uq_knowledge_relations_active",
        ),
    )
    op.create_index(op.f("ix_knowledge_relations_item_id"), "knowledge_relations", ["item_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_user_id"), "knowledge_relations", ["user_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_organization_id"), "knowledge_relations", ["organization_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_relation_type"), "knowledge_relations", ["relation_type"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_source_entity_id"), "knowledge_relations", ["source_entity_id"], unique=False)
    op.create_index(op.f("ix_knowledge_relations_target_entity_id"), "knowledge_relations", ["target_entity_id"], unique=False)

    op.create_table(
        "knowledge_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic", sa.String(length=64), nullable=False),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(op.f("ix_knowledge_outbox_topic"), "knowledge_outbox", ["topic"], unique=False)
    op.create_index(op.f("ix_knowledge_outbox_aggregate_type"), "knowledge_outbox", ["aggregate_type"], unique=False)
    op.create_index(op.f("ix_knowledge_outbox_aggregate_id"), "knowledge_outbox", ["aggregate_id"], unique=False)
    op.create_index(op.f("ix_knowledge_outbox_status"), "knowledge_outbox", ["status"], unique=False)
    op.create_index(op.f("ix_knowledge_outbox_available_at"), "knowledge_outbox", ["available_at"], unique=False)
    op.create_index(op.f("ix_knowledge_outbox_lease_owner"), "knowledge_outbox", ["lease_owner"], unique=False)
    op.create_index(op.f("ix_knowledge_outbox_lease_expires_at"), "knowledge_outbox", ["lease_expires_at"], unique=False)

    op.create_table(
        "knowledge_projection_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("projection", sa.String(length=64), nullable=False),
        sa.Column("backend", sa.String(length=64), nullable=False),
        sa.Column("backend_key", sa.String(length=512), nullable=True),
        sa.Column("synced_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "aggregate_type",
            "aggregate_id",
            "projection",
            "backend",
            name="uq_knowledge_projection_state",
        ),
    )
    op.create_index(op.f("ix_knowledge_projection_states_status"), "knowledge_projection_states", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_projection_states_status"), table_name="knowledge_projection_states")
    op.drop_table("knowledge_projection_states")

    op.drop_index(op.f("ix_knowledge_outbox_lease_expires_at"), table_name="knowledge_outbox")
    op.drop_index(op.f("ix_knowledge_outbox_lease_owner"), table_name="knowledge_outbox")
    op.drop_index(op.f("ix_knowledge_outbox_available_at"), table_name="knowledge_outbox")
    op.drop_index(op.f("ix_knowledge_outbox_status"), table_name="knowledge_outbox")
    op.drop_index(op.f("ix_knowledge_outbox_aggregate_id"), table_name="knowledge_outbox")
    op.drop_index(op.f("ix_knowledge_outbox_aggregate_type"), table_name="knowledge_outbox")
    op.drop_index(op.f("ix_knowledge_outbox_topic"), table_name="knowledge_outbox")
    op.drop_table("knowledge_outbox")

    op.drop_index(op.f("ix_knowledge_relations_target_entity_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_source_entity_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_relation_type"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_organization_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_user_id"), table_name="knowledge_relations")
    op.drop_index(op.f("ix_knowledge_relations_item_id"), table_name="knowledge_relations")
    op.drop_table("knowledge_relations")

    op.drop_index("ix_knowledge_entities_scope_name", table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_canonical_name"), table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_entity_type"), table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_organization_id"), table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_user_id"), table_name="knowledge_entities")
    op.drop_index(op.f("ix_knowledge_entities_item_id"), table_name="knowledge_entities")
    op.drop_table("knowledge_entities")

    op.drop_index("ix_knowledge_items_scope_source", table_name="knowledge_items")
    op.drop_index("ix_knowledge_items_scope_kind", table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_is_public"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_owner_access_level"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_kg_status"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_vector_status"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_content_hash"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_kind"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_organization_id"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_user_id"), table_name="knowledge_items")
    op.drop_index(op.f("ix_knowledge_items_source_id"), table_name="knowledge_items")
    op.drop_table("knowledge_items")

    op.drop_index("ix_knowledge_sources_scope_type", table_name="knowledge_sources")
    op.drop_index(op.f("ix_knowledge_sources_is_public"), table_name="knowledge_sources")
    op.drop_index(op.f("ix_knowledge_sources_owner_access_level"), table_name="knowledge_sources")
    op.drop_index(op.f("ix_knowledge_sources_source_type"), table_name="knowledge_sources")
    op.drop_index(op.f("ix_knowledge_sources_organization_id"), table_name="knowledge_sources")
    op.drop_index(op.f("ix_knowledge_sources_user_id"), table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
