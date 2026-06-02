"""add_obs_export_outbox

Revision ID: 7c4e9b2a1d11
Revises: 3e2c1f7a9b44
Create Date: 2026-03-05 18:20:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c4e9b2a1d11"
down_revision: Union[str, Sequence[str], None] = "3e2c1f7a9b44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "obs_export_outbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event_kind", sa.String(length=32), nullable=False),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("source_node_id", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("exported_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("obs_export_outbox", schema=None) as batch_op:
        batch_op.create_index("idx_obs_export_outbox_status_next", ["status", "next_attempt_at"], unique=False)
        batch_op.create_index("idx_obs_export_outbox_kind_ts", ["event_kind", "timestamp"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_correlation_id", ["correlation_id"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_dedupe_key", ["dedupe_key"], unique=True)
        batch_op.create_index("ix_obs_export_outbox_event_kind", ["event_kind"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_exported_at", ["exported_at"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_next_attempt_at", ["next_attempt_at"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_source_node_id", ["source_node_id"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_status", ["status"], unique=False)
        batch_op.create_index("ix_obs_export_outbox_timestamp", ["timestamp"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("obs_export_outbox", schema=None) as batch_op:
        batch_op.drop_index("ix_obs_export_outbox_timestamp")
        batch_op.drop_index("ix_obs_export_outbox_status")
        batch_op.drop_index("ix_obs_export_outbox_source_node_id")
        batch_op.drop_index("ix_obs_export_outbox_next_attempt_at")
        batch_op.drop_index("ix_obs_export_outbox_exported_at")
        batch_op.drop_index("ix_obs_export_outbox_event_kind")
        batch_op.drop_index("ix_obs_export_outbox_dedupe_key")
        batch_op.drop_index("ix_obs_export_outbox_correlation_id")
        batch_op.drop_index("idx_obs_export_outbox_kind_ts")
        batch_op.drop_index("idx_obs_export_outbox_status_next")
    op.drop_table("obs_export_outbox")
