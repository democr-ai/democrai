"""add auth login rate limits

Revision ID: 7b6e5f4a3c21
Revises: 5a9c1e4d7f32
Create Date: 2026-06-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7b6e5f4a3c21"
down_revision: Union[str, Sequence[str], None] = "5a9c1e4d7f32"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_login_rate_limits",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bucket_type", sa.String(length=32), nullable=False),
        sa.Column("bucket_value", sa.String(length=255), nullable=False),
        sa.Column("failures", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_failed_at", sa.DateTime(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket_type",
            "bucket_value",
            name="uq_auth_login_rate_limit_bucket",
        ),
    )
    op.create_index(
        op.f("ix_auth_login_rate_limits_bucket_type"),
        "auth_login_rate_limits",
        ["bucket_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_login_rate_limits_bucket_value"),
        "auth_login_rate_limits",
        ["bucket_value"],
        unique=False,
    )
    op.create_index(
        op.f("ix_auth_login_rate_limits_locked_until"),
        "auth_login_rate_limits",
        ["locked_until"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_auth_login_rate_limits_locked_until"),
        table_name="auth_login_rate_limits",
    )
    op.drop_index(
        op.f("ix_auth_login_rate_limits_bucket_value"),
        table_name="auth_login_rate_limits",
    )
    op.drop_index(
        op.f("ix_auth_login_rate_limits_bucket_type"),
        table_name="auth_login_rate_limits",
    )
    op.drop_table("auth_login_rate_limits")
