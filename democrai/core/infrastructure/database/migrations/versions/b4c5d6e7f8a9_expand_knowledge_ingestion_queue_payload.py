"""expand knowledge ingestion queue payload

Revision ID: b4c5d6e7f8a9
Revises: a3f6b9c2d4e1
Create Date: 2026-05-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "a3f6b9c2d4e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_ingestion_requests") as batch_op:
        batch_op.alter_column("extraction_request_id", nullable=True)
        batch_op.add_column(
            sa.Column(
                "origin_type",
                sa.String(length=64),
                nullable=False,
                server_default="extraction",
            )
        )
        batch_op.add_column(
            sa.Column("source", sa.Text(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("items", sa.Text(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column(
                "request_context",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch_op.create_index(
            op.f("ix_knowledge_ingestion_requests_origin_type"),
            ["origin_type"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_ingestion_requests") as batch_op:
        batch_op.drop_index(op.f("ix_knowledge_ingestion_requests_origin_type"))
        batch_op.drop_column("request_context")
        batch_op.drop_column("items")
        batch_op.drop_column("source")
        batch_op.drop_column("origin_type")
        batch_op.alter_column("extraction_request_id", nullable=False)
