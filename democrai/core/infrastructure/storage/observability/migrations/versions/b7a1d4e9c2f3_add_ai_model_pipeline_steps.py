"""add_ai_model_pipeline_steps

Revision ID: b7a1d4e9c2f3
Revises: 2d6e4f8a0b91
Create Date: 2026-05-05 18:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7a1d4e9c2f3"
down_revision: Union[str, Sequence[str], None] = "2d6e4f8a0b91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_model_pipeline_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("pipeline_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("step_id", sa.String(length=64), nullable=False),
        sa.Column("parent_step_id", sa.String(length=64), nullable=True),
        sa.Column("root_method", sa.String(length=64), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("provider", sa.String(length=128), nullable=True),
        sa.Column("engine", sa.String(length=128), nullable=True),
        sa.Column("engine_row_id", sa.Integer(), nullable=True),
        sa.Column("model_registry_id", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("node_id", sa.String(length=255), nullable=True),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False),
        sa.Column("stats_json", sa.Text(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ai_model_pipeline_id_ts", "ai_model_pipeline_steps", ["pipeline_id", "timestamp"])
    op.create_index("idx_ai_model_pipeline_parent", "ai_model_pipeline_steps", ["parent_step_id"])
    op.create_index("idx_ai_model_pipeline_request", "ai_model_pipeline_steps", ["request_id"])
    op.create_index("idx_ai_model_pipeline_status", "ai_model_pipeline_steps", ["status"])
    op.create_index("idx_ai_model_pipeline_step", "ai_model_pipeline_steps", ["step_id"])
    op.create_index("idx_ai_model_pipeline_ts", "ai_model_pipeline_steps", ["timestamp"])
    op.create_index("idx_ai_model_pipeline_type", "ai_model_pipeline_steps", ["type"])


def downgrade() -> None:
    op.drop_index("idx_ai_model_pipeline_type", table_name="ai_model_pipeline_steps")
    op.drop_index("idx_ai_model_pipeline_ts", table_name="ai_model_pipeline_steps")
    op.drop_index("idx_ai_model_pipeline_step", table_name="ai_model_pipeline_steps")
    op.drop_index("idx_ai_model_pipeline_status", table_name="ai_model_pipeline_steps")
    op.drop_index("idx_ai_model_pipeline_request", table_name="ai_model_pipeline_steps")
    op.drop_index("idx_ai_model_pipeline_parent", table_name="ai_model_pipeline_steps")
    op.drop_index("idx_ai_model_pipeline_id_ts", table_name="ai_model_pipeline_steps")
    op.drop_table("ai_model_pipeline_steps")
