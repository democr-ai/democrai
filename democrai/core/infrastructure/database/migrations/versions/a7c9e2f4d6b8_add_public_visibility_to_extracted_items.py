"""add public visibility to extracted items

Revision ID: a7c9e2f4d6b8
Revises: f6a7b8c9d0e1
Create Date: 2026-05-24 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c9e2f4d6b8"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_extraction_requests") as batch_op:
        batch_op.add_column(
            sa.Column("is_public", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index(
            op.f("ix_knowledge_extraction_requests_is_public"), ["is_public"]
        )
    with op.batch_alter_table("knowledge_extracted_items") as batch_op:
        batch_op.add_column(
            sa.Column("is_public", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.create_index(
            op.f("ix_knowledge_extracted_items_is_public"), ["is_public"]
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_extracted_items") as batch_op:
        batch_op.drop_index(op.f("ix_knowledge_extracted_items_is_public"))
        batch_op.drop_column("is_public")
    with op.batch_alter_table("knowledge_extraction_requests") as batch_op:
        batch_op.drop_index(op.f("ix_knowledge_extraction_requests_is_public"))
        batch_op.drop_column("is_public")
