"""add runtime node registry

Revision ID: b6c7d8e9f012
Revises: e5a1c2f7b9d0
Create Date: 2026-05-10 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "b6c7d8e9f012"
down_revision: Union[str, Sequence[str], None] = "e5a1c2f7b9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "runtime_node_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("hostname", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("has_nvidia_gpu", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("node_id", name="uq_runtime_node_registry_node_id"),
    )
    with op.batch_alter_table("runtime_node_registry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_runtime_node_registry_node_id"),
            ["node_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_runtime_node_registry_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_runtime_node_registry_last_seen_at"),
            ["last_seen_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("runtime_node_registry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_runtime_node_registry_last_seen_at"))
        batch_op.drop_index(batch_op.f("ix_runtime_node_registry_status"))
        batch_op.drop_index(batch_op.f("ix_runtime_node_registry_node_id"))
    op.drop_table("runtime_node_registry")
