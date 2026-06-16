"""add engine_node_instance_registry

Revision ID: 5a9c1e4d7f32
Revises: 4f8b0d3c6e21
Create Date: 2026-06-12 10:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a9c1e4d7f32"
down_revision: Union[str, Sequence[str], None] = "4f8b0d3c6e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "engine_node_instance_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("engine_row_id", sa.Integer(), nullable=False),
        sa.Column("engine_id", sa.String(length=255), nullable=False),
        sa.Column("model_registry_id", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(length=512), nullable=False),
        sa.Column("config_signature", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "node_id",
            "engine_row_id",
            "model_registry_id",
            name="uq_engine_node_instance_registry_node_engine_model",
        ),
    )
    with op.batch_alter_table("engine_node_instance_registry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_engine_node_instance_registry_node_id"),
            ["node_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_instance_registry_engine_row_id"),
            ["engine_row_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_instance_registry_model_registry_id"),
            ["model_registry_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_instance_registry_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_node_instance_registry_last_seen_at"),
            ["last_seen_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("engine_node_instance_registry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_engine_node_instance_registry_last_seen_at"))
        batch_op.drop_index(batch_op.f("ix_engine_node_instance_registry_status"))
        batch_op.drop_index(
            batch_op.f("ix_engine_node_instance_registry_model_registry_id")
        )
        batch_op.drop_index(batch_op.f("ix_engine_node_instance_registry_engine_row_id"))
        batch_op.drop_index(batch_op.f("ix_engine_node_instance_registry_node_id"))
    op.drop_table("engine_node_instance_registry")
