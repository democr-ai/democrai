"""add extractor mime type bindings

Revision ID: 7a9c2e4f6b10
Revises: f2a3b4c5d6e7
Create Date: 2026-05-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7a9c2e4f6b10"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extractor_mime_type_binding",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("mime_type", sa.String(length=255), nullable=False),
        sa.Column("extractor_id", sa.String(length=100), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mime_type"),
    )
    op.create_index(
        op.f("ix_extractor_mime_type_binding_mime_type"),
        "extractor_mime_type_binding",
        ["mime_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extractor_mime_type_binding_extractor_id"),
        "extractor_mime_type_binding",
        ["extractor_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_extractor_mime_type_binding_extractor_id"),
        table_name="extractor_mime_type_binding",
    )
    op.drop_index(
        op.f("ix_extractor_mime_type_binding_mime_type"),
        table_name="extractor_mime_type_binding",
    )
    op.drop_table("extractor_mime_type_binding")
