"""add_trace_archive_queue

Revision ID: c2a9d7e4b6f1
Revises: f8c6a2d91e44
Create Date: 2026-05-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2a9d7e4b6f1"
down_revision: Union[str, Sequence[str], None] = "f8c6a2d91e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_pipeline_steps", schema=None) as batch_op:
        batch_op.add_column(sa.Column("input_hash", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("output_hash", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("input_size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_size_bytes", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("archive_status", sa.String(length=32), server_default="none", nullable=False))
        batch_op.add_column(sa.Column("archive_media_path", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("archive_error", sa.Text(), nullable=True))
        batch_op.create_index(batch_op.f("ix_ai_model_pipeline_steps_archive_status"), ["archive_status"], unique=False)

    op.create_table(
        "obs_trace_archive_queue",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("pipeline_step_db_id", sa.Integer(), nullable=True),
        sa.Column("pipeline_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("payload_kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("archived_media_path", sa.Text(), nullable=True),
        sa.Column("payload_hash", sa.String(length=80), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("obs_trace_archive_queue", schema=None) as batch_op:
        batch_op.create_index("idx_obs_trace_archive_pipeline_step", ["pipeline_id", "step_id"], unique=False)
        batch_op.create_index("idx_obs_trace_archive_status_next", ["status", "next_attempt_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_locked_at"), ["locked_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_locked_by"), ["locked_by"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_next_attempt_at"), ["next_attempt_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_payload_hash"), ["payload_hash"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_payload_kind"), ["payload_kind"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_pipeline_id"), ["pipeline_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_pipeline_step_db_id"), ["pipeline_step_db_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_request_id"), ["request_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_status"), ["status"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_step_id"), ["step_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_obs_trace_archive_queue_timestamp"), ["timestamp"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("obs_trace_archive_queue", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_timestamp"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_step_id"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_status"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_request_id"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_pipeline_step_db_id"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_pipeline_id"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_payload_kind"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_payload_hash"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_next_attempt_at"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_locked_by"))
        batch_op.drop_index(batch_op.f("ix_obs_trace_archive_queue_locked_at"))
        batch_op.drop_index("idx_obs_trace_archive_status_next")
        batch_op.drop_index("idx_obs_trace_archive_pipeline_step")
    op.drop_table("obs_trace_archive_queue")

    with op.batch_alter_table("ai_model_pipeline_steps", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_ai_model_pipeline_steps_archive_status"))
        batch_op.drop_column("archive_error")
        batch_op.drop_column("archive_media_path")
        batch_op.drop_column("archive_status")
        batch_op.drop_column("output_size_bytes")
        batch_op.drop_column("input_size_bytes")
        batch_op.drop_column("output_hash")
        batch_op.drop_column("input_hash")
