"""add knowledge runtime config

Revision ID: 8b1d3f5a7c20
Revises: 7a9c2e4f6b10
Create Date: 2026-05-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8b1d3f5a7c20"
down_revision: Union[str, Sequence[str], None] = "7a9c2e4f6b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_runtime_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("embedding_model_registry_id", sa.Integer(), nullable=True),
        sa.Column("rerank_model_registry_id", sa.Integer(), nullable=True),
        sa.Column("classification_model_registry_id", sa.Integer(), nullable=True),
        sa.Column("triple_extractor_model_registry_id", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["embedding_model_registry_id"], ["model_registry.id"]),
        sa.ForeignKeyConstraint(["rerank_model_registry_id"], ["model_registry.id"]),
        sa.ForeignKeyConstraint(["classification_model_registry_id"], ["model_registry.id"]),
        sa.ForeignKeyConstraint(["triple_extractor_model_registry_id"], ["model_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_runtime_config_embedding_model_registry_id"),
        "knowledge_runtime_config",
        ["embedding_model_registry_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_runtime_config_rerank_model_registry_id"),
        "knowledge_runtime_config",
        ["rerank_model_registry_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_runtime_config_classification_model_registry_id"),
        "knowledge_runtime_config",
        ["classification_model_registry_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_runtime_config_triple_extractor_model_registry_id"),
        "knowledge_runtime_config",
        ["triple_extractor_model_registry_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_knowledge_runtime_config_triple_extractor_model_registry_id"),
        table_name="knowledge_runtime_config",
    )
    op.drop_index(
        op.f("ix_knowledge_runtime_config_classification_model_registry_id"),
        table_name="knowledge_runtime_config",
    )
    op.drop_index(
        op.f("ix_knowledge_runtime_config_rerank_model_registry_id"),
        table_name="knowledge_runtime_config",
    )
    op.drop_index(
        op.f("ix_knowledge_runtime_config_embedding_model_registry_id"),
        table_name="knowledge_runtime_config",
    )
    op.drop_table("knowledge_runtime_config")
