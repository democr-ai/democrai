"""add module command state table

Revision ID: 2f6d4f9d9c31
Revises: 7c4f2d9b8e31
Create Date: 2026-03-01 11:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2f6d4f9d9c31"
down_revision: Union[str, Sequence[str], None] = "7c4f2d9b8e31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "module_command_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("command_name", sa.String(length=255), nullable=False),
        sa.Column("lifecycle", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("run_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_finished_at", sa.DateTime(), nullable=True),
        sa.Column("next_run_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_name"),
    )
    op.create_index(
        op.f("ix_module_command_states_module_name"),
        "module_command_states",
        ["module_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_module_command_states_command_name"),
        "module_command_states",
        ["command_name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_module_command_states_lifecycle"),
        "module_command_states",
        ["lifecycle"],
        unique=False,
    )
    op.create_index(
        op.f("ix_module_command_states_status"),
        "module_command_states",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_module_command_states_next_run_at"),
        "module_command_states",
        ["next_run_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_module_command_states_lease_owner"),
        "module_command_states",
        ["lease_owner"],
        unique=False,
    )
    op.create_index(
        op.f("ix_module_command_states_lease_expires_at"),
        "module_command_states",
        ["lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_module_command_states_lease_expires_at"),
        table_name="module_command_states",
    )
    op.drop_index(
        op.f("ix_module_command_states_lease_owner"),
        table_name="module_command_states",
    )
    op.drop_index(
        op.f("ix_module_command_states_next_run_at"),
        table_name="module_command_states",
    )
    op.drop_index(
        op.f("ix_module_command_states_status"),
        table_name="module_command_states",
    )
    op.drop_index(
        op.f("ix_module_command_states_lifecycle"),
        table_name="module_command_states",
    )
    op.drop_index(
        op.f("ix_module_command_states_command_name"),
        table_name="module_command_states",
    )
    op.drop_index(
        op.f("ix_module_command_states_module_name"),
        table_name="module_command_states",
    )
    op.drop_table("module_command_states")
