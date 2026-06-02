"""add_tokens_per_second_to_ai_usage

Revision ID: f8c6a2d91e44
Revises: b7a1d4e9c2f3
Create Date: 2026-05-05 22:45:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8c6a2d91e44"
down_revision: Union[str, Sequence[str], None] = "b7a1d4e9c2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tokens_per_second", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.drop_column("tokens_per_second")
