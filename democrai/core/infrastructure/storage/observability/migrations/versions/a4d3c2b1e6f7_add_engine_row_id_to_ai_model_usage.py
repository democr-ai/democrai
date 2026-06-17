"""add engine_row_id to ai_model_usage

Revision ID: a4d3c2b1e6f7
Revises: c2a9d7e4b6f1
Create Date: 2026-06-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a4d3c2b1e6f7"
down_revision: Union[str, Sequence[str], None] = "c2a9d7e4b6f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.add_column(sa.Column("engine_row_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_ai_model_usage_events_engine_row_id"),
            ["engine_row_id"],
            unique=False,
        )
        batch_op.create_index(
            "idx_ai_model_usage_engine_success_ts",
            ["engine_row_id", "success", "timestamp"],
            unique=False,
        )
        batch_op.create_index(
            "idx_ai_model_usage_engine_user_success_ts",
            ["engine_row_id", "user_id", "success", "timestamp"],
            unique=False,
        )
        batch_op.create_index(
            "idx_ai_model_usage_engine_org_success_ts",
            ["engine_row_id", "organization_id", "success", "timestamp"],
            unique=False,
        )
        batch_op.create_index(
            "idx_ai_model_usage_engine_session_success_ts",
            ["engine_row_id", "session_id", "success", "timestamp"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.drop_index("idx_ai_model_usage_engine_session_success_ts")
        batch_op.drop_index("idx_ai_model_usage_engine_org_success_ts")
        batch_op.drop_index("idx_ai_model_usage_engine_user_success_ts")
        batch_op.drop_index("idx_ai_model_usage_engine_success_ts")
        batch_op.drop_index(batch_op.f("ix_ai_model_usage_events_engine_row_id"))
        batch_op.drop_column("engine_row_id")
