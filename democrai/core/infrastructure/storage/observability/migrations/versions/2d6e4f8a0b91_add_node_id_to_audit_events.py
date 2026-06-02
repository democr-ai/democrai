"""add_node_id_to_audit_events

Revision ID: 2d6e4f8a0b91
Revises: 9f4b2c8d1a77
Create Date: 2026-05-03 15:36:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d6e4f8a0b91"
down_revision: Union[str, Sequence[str], None] = "9f4b2c8d1a77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("node_id", sa.String(length=255), nullable=True))
        batch_op.create_index("idx_audit_events_node", ["node_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("idx_audit_events_node")
        batch_op.drop_column("node_id")
