"""extend runtime_node_registry with orchestrator resources

Revision ID: 4f8b0d3c6e21
Revises: 3e7a9c2b5d10
Create Date: 2026-06-12 10:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f8b0d3c6e21"
down_revision: Union[str, Sequence[str], None] = "3e7a9c2b5d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("runtime_node_registry", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("orchestrator_last_seen_at", sa.DateTime(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "cpu_percent", sa.Float(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "ram_total_mb", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "ram_free_mb", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "vram_total_mb", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "vram_free_mb", sa.Integer(), nullable=False, server_default="0"
            )
        )
        batch_op.add_column(
            sa.Column(
                "gpu_inventory_json", sa.Text(), nullable=False, server_default="[]"
            )
        )
        batch_op.add_column(
            sa.Column("resources_updated_at", sa.DateTime(), nullable=True)
        )
        batch_op.create_index(
            batch_op.f("ix_runtime_node_registry_orchestrator_last_seen_at"),
            ["orchestrator_last_seen_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("runtime_node_registry", schema=None) as batch_op:
        batch_op.drop_index(
            batch_op.f("ix_runtime_node_registry_orchestrator_last_seen_at")
        )
        batch_op.drop_column("resources_updated_at")
        batch_op.drop_column("gpu_inventory_json")
        batch_op.drop_column("vram_free_mb")
        batch_op.drop_column("vram_total_mb")
        batch_op.drop_column("ram_free_mb")
        batch_op.drop_column("ram_total_mb")
        batch_op.drop_column("cpu_percent")
        batch_op.drop_column("orchestrator_last_seen_at")
