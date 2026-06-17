"""add engine quota limits

Revision ID: e6a1b2c3d4f5
Revises: 4a8c1d2e3f90, 7b6e5f4a3c21, f1a2b3c4d5e6
Create Date: 2026-06-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e6a1b2c3d4f5"
down_revision: Union[str, Sequence[str], None] = (
    "4a8c1d2e3f90",
    "7b6e5f4a3c21",
    "f1a2b3c4d5e6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "engine_quota_counters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("period_unit", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    with op.batch_alter_table("engine_quota_counters", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_engine_quota_counters_period_unit"),
            ["period_unit"],
            unique=False,
        )

    op.create_table(
        "engine_quota_limits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("counter_id", sa.Integer(), nullable=False),
        sa.Column("engine_row_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.Integer(), nullable=True),
        sa.Column("limit_total_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["counter_id"], ["engine_quota_counters.id"]),
        sa.ForeignKeyConstraint(["engine_row_id"], ["engine_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "counter_id",
            "engine_row_id",
            "scope_type",
            "scope_id",
            name="uq_engine_quota_limit_scope",
        ),
    )
    with op.batch_alter_table("engine_quota_limits", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_engine_quota_limits_counter_id"),
            ["counter_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_quota_limits_engine_row_id"),
            ["engine_row_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_quota_limits_scope_type"),
            ["scope_type"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_quota_limits_scope_id"),
            ["scope_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_engine_quota_limits_engine_scope",
            ["engine_row_id", "scope_type", "scope_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("engine_quota_limits", schema=None) as batch_op:
        batch_op.drop_index("ix_engine_quota_limits_engine_scope")
        batch_op.drop_index(batch_op.f("ix_engine_quota_limits_scope_id"))
        batch_op.drop_index(batch_op.f("ix_engine_quota_limits_scope_type"))
        batch_op.drop_index(batch_op.f("ix_engine_quota_limits_engine_row_id"))
        batch_op.drop_index(batch_op.f("ix_engine_quota_limits_counter_id"))
    op.drop_table("engine_quota_limits")

    with op.batch_alter_table("engine_quota_counters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_engine_quota_counters_period_unit"))
    op.drop_table("engine_quota_counters")
