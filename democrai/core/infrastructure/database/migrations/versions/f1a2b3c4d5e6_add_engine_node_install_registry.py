"""add engine_node_install_registry

Revision ID: f1a2b3c4d5e6
Revises: c3d4e5f6a7b8
Create Date: 2026-04-11 15:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "engine_node_install_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("engine_id", sa.String(length=255), nullable=False),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("last_event_id", sa.String(length=255), nullable=True),
        sa.Column("install_started_at", sa.DateTime(), nullable=True),
        sa.Column("install_completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("manifest_version", sa.String(length=50), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "engine_id",
            "node_id",
            name="uq_engine_node_install_registry_engine_node",
        ),
    )
    with op.batch_alter_table("engine_node_install_registry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_engine_node_install_registry_engine_id"),
            ["engine_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_install_registry_node_id"),
            ["node_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_install_registry_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_install_registry_last_event_id"),
            ["last_event_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("engine_node_install_registry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_engine_node_install_registry_last_event_id"))
        batch_op.drop_index(batch_op.f("ix_engine_node_install_registry_status"))
        batch_op.drop_index(batch_op.f("ix_engine_node_install_registry_node_id"))
        batch_op.drop_index(batch_op.f("ix_engine_node_install_registry_engine_id"))
    op.drop_table("engine_node_install_registry")
