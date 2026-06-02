"""allow_null_correlation_ids

Revision ID: 3e2c1f7a9b44
Revises: d1b8d8f9c4a2
Create Date: 2026-03-04 18:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3e2c1f7a9b44"
down_revision: Union[str, Sequence[str], None] = "d1b8d8f9c4a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.alter_column(
            "correlation_id",
            existing_type=sa.String(length=255),
            nullable=True,
        )

    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.alter_column(
            "correlation_id",
            existing_type=sa.String(length=255),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.alter_column(
            "correlation_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )

    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.alter_column(
            "correlation_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )
