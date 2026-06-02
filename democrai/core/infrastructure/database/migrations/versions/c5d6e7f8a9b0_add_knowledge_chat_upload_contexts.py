"""add knowledge chat upload contexts

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-05-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "b4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS vw_knowledge_retrieval_items")
    op.execute("DROP TABLE IF EXISTS knowledge_media_context_links")
    op.add_column(
        "knowledge_items",
        sa.Column("media_file_id", sa.String(length=64), nullable=True),
    )
    op.create_index(
        op.f("ix_knowledge_items_media_file_id"),
        "knowledge_items",
        ["media_file_id"],
        unique=False,
    )
    op.create_table(
        "knowledge_chat_upload_contexts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("owner_access_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("pipeline_id", sa.String(length=255), nullable=False),
        sa.Column("context", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_knowledge_chat_upload_contexts_file_user_org_pipeline",
        "knowledge_chat_upload_contexts",
        ["file_id", "user_id", "organization_id", "pipeline_id"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NOT NULL"),
        sqlite_where=sa.text("organization_id IS NOT NULL"),
    )
    op.create_index(
        "uq_knowledge_chat_upload_contexts_file_user_pipeline_no_org",
        "knowledge_chat_upload_contexts",
        ["file_id", "user_id", "pipeline_id"],
        unique=True,
        postgresql_where=sa.text("organization_id IS NULL"),
        sqlite_where=sa.text("organization_id IS NULL"),
    )
    op.create_index(
        op.f("ix_knowledge_chat_upload_contexts_file_id"),
        "knowledge_chat_upload_contexts",
        ["file_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chat_upload_contexts_user_id"),
        "knowledge_chat_upload_contexts",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chat_upload_contexts_organization_id"),
        "knowledge_chat_upload_contexts",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chat_upload_contexts_owner_access_level"),
        "knowledge_chat_upload_contexts",
        ["owner_access_level"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chat_upload_contexts_pipeline_id"),
        "knowledge_chat_upload_contexts",
        ["pipeline_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_chat_upload_contexts_created_at"),
        "knowledge_chat_upload_contexts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_knowledge_chat_upload_contexts_file_user_pipeline_no_org",
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        "uq_knowledge_chat_upload_contexts_file_user_org_pipeline",
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        op.f("ix_knowledge_chat_upload_contexts_created_at"),
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        op.f("ix_knowledge_chat_upload_contexts_pipeline_id"),
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        op.f("ix_knowledge_chat_upload_contexts_file_id"),
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        op.f("ix_knowledge_chat_upload_contexts_owner_access_level"),
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        op.f("ix_knowledge_chat_upload_contexts_organization_id"),
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_index(
        op.f("ix_knowledge_chat_upload_contexts_user_id"),
        table_name="knowledge_chat_upload_contexts",
    )
    op.drop_table("knowledge_chat_upload_contexts")
    op.drop_index(
        op.f("ix_knowledge_items_media_file_id"),
        table_name="knowledge_items",
    )
    op.drop_column("knowledge_items", "media_file_id")
