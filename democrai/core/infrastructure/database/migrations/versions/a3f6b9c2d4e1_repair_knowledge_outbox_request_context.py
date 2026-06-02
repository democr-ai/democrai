"""repair knowledge outbox request context

Revision ID: a3f6b9c2d4e1
Revises: 9c4e8b2d1f30
Create Date: 2026-05-17 14:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a3f6b9c2d4e1"
down_revision: Union[str, Sequence[str], None] = "9c4e8b2d1f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(table_name)
    )


def upgrade() -> None:
    if not _has_column("knowledge_outbox", "request_context"):
        with op.batch_alter_table("knowledge_outbox") as batch_op:
            batch_op.add_column(
                sa.Column(
                    "request_context",
                    sa.Text(),
                    nullable=False,
                    server_default="{}",
                )
            )


def downgrade() -> None:
    if _has_column("knowledge_outbox", "request_context"):
        with op.batch_alter_table("knowledge_outbox") as batch_op:
            batch_op.drop_column("request_context")
