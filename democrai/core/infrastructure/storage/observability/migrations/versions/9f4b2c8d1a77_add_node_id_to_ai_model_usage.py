"""add_node_id_to_ai_model_usage

Revision ID: 9f4b2c8d1a77
Revises: 7c4e9b2a1d11
Create Date: 2026-05-03 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9f4b2c8d1a77"
down_revision: Union[str, Sequence[str], None] = "7c4e9b2a1d11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("node_id", sa.String(length=255), nullable=True))
        batch_op.create_index("idx_ai_model_usage_node", ["node_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.drop_index("idx_ai_model_usage_node")
        batch_op.drop_column("node_id")
