"""add knowledge item classifications

Revision ID: 9c4e8b2d1f30
Revises: 8b1d3f5a7c20
Create Date: 2026-05-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c4e8b2d1f30"
down_revision: Union[str, Sequence[str], None] = "8b1d3f5a7c20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "knowledge_item_classifications",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("model_registry_id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("scores_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "item_id",
            "model_registry_id",
            name="uq_knowledge_item_classification_model",
        ),
    )
    op.create_index(
        op.f("ix_knowledge_item_classifications_item_id"),
        "knowledge_item_classifications",
        ["item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_item_classifications_user_id"),
        "knowledge_item_classifications",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_item_classifications_organization_id"),
        "knowledge_item_classifications",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_item_classifications_model_registry_id"),
        "knowledge_item_classifications",
        ["model_registry_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_item_classifications_label"),
        "knowledge_item_classifications",
        ["label"],
        unique=False,
    )
    op.create_index(
        op.f("ix_knowledge_item_classifications_status"),
        "knowledge_item_classifications",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_knowledge_item_classifications_scope_label",
        "knowledge_item_classifications",
        ["user_id", "organization_id", "label"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_item_classifications_scope_label",
        table_name="knowledge_item_classifications",
    )
    op.drop_index(
        op.f("ix_knowledge_item_classifications_status"),
        table_name="knowledge_item_classifications",
    )
    op.drop_index(
        op.f("ix_knowledge_item_classifications_label"),
        table_name="knowledge_item_classifications",
    )
    op.drop_index(
        op.f("ix_knowledge_item_classifications_model_registry_id"),
        table_name="knowledge_item_classifications",
    )
    op.drop_index(
        op.f("ix_knowledge_item_classifications_organization_id"),
        table_name="knowledge_item_classifications",
    )
    op.drop_index(
        op.f("ix_knowledge_item_classifications_user_id"),
        table_name="knowledge_item_classifications",
    )
    op.drop_index(
        op.f("ix_knowledge_item_classifications_item_id"),
        table_name="knowledge_item_classifications",
    )
    op.drop_table("knowledge_item_classifications")
