"""add request context to knowledge workers

Revision ID: f2a3b4c5d6e7
Revises: d8e9f0123456
Create Date: 2026-05-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "d8e9f0123456"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("knowledge_outbox") as batch_op:
        batch_op.add_column(
            sa.Column(
                "request_context",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
    with op.batch_alter_table("knowledge_extraction_requests") as batch_op:
        batch_op.add_column(
            sa.Column(
                "request_context",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("knowledge_extraction_requests") as batch_op:
        batch_op.drop_column("request_context")
    with op.batch_alter_table("knowledge_outbox") as batch_op:
        batch_op.drop_column("request_context")
