"""extend engine quota metrics

Revision ID: a7e5c9d2f4b8
Revises: e6a1b2c3d4f5
Create Date: 2026-06-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7e5c9d2f4b8"
down_revision: Union[str, Sequence[str], None] = "e6a1b2c3d4f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("engine_quota_counters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("period_count", sa.Integer(), nullable=True))
    op.execute("UPDATE engine_quota_counters SET period_count = 1 WHERE period_count IS NULL")
    with op.batch_alter_table("engine_quota_counters", schema=None) as batch_op:
        batch_op.alter_column("period_count", existing_type=sa.Integer(), nullable=False)

    with op.batch_alter_table("engine_quota_limits", schema=None) as batch_op:
        batch_op.add_column(sa.Column("metric_type", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("limit_value", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE engine_quota_limits "
        "SET metric_type = 'total_tokens', limit_value = limit_total_tokens "
        "WHERE metric_type IS NULL OR limit_value IS NULL"
    )
    with op.batch_alter_table("engine_quota_limits", schema=None) as batch_op:
        batch_op.drop_constraint("uq_engine_quota_limit_scope", type_="unique")
        batch_op.alter_column("metric_type", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("limit_value", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("limit_total_tokens")
        batch_op.create_index(
            batch_op.f("ix_engine_quota_limits_metric_type"),
            ["metric_type"],
            unique=False,
        )
        batch_op.create_unique_constraint(
            "uq_engine_quota_limit_scope",
            ["counter_id", "engine_row_id", "scope_type", "scope_id", "metric_type"],
        )


def downgrade() -> None:
    with op.batch_alter_table("engine_quota_limits", schema=None) as batch_op:
        batch_op.add_column(sa.Column("limit_total_tokens", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE engine_quota_limits "
        "SET limit_total_tokens = limit_value "
        "WHERE limit_total_tokens IS NULL"
    )
    with op.batch_alter_table("engine_quota_limits", schema=None) as batch_op:
        batch_op.drop_constraint("uq_engine_quota_limit_scope", type_="unique")
        batch_op.drop_index(batch_op.f("ix_engine_quota_limits_metric_type"))
        batch_op.alter_column(
            "limit_total_tokens",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_column("limit_value")
        batch_op.drop_column("metric_type")
        batch_op.create_unique_constraint(
            "uq_engine_quota_limit_scope",
            ["counter_id", "engine_row_id", "scope_type", "scope_id"],
        )

    with op.batch_alter_table("engine_quota_counters", schema=None) as batch_op:
        batch_op.drop_column("period_count")
