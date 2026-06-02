"""add agent model configs

Revision ID: 4d9e2a1b7c33
Revises: e2f3a4b5c6d7
Create Date: 2026-05-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d9e2a1b7c33"
down_revision: Union[str, Sequence[str], None] = "e2f3a4b5c6d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_model_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("model_policy", sa.String(length=32), nullable=False),
        sa.Column("model_registry_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["model_registry_id"], ["model_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_name"),
    )
    with op.batch_alter_table("agent_model_configs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_agent_model_configs_agent_name"), ["agent_name"], unique=True)
        batch_op.create_index(batch_op.f("ix_agent_model_configs_model_policy"), ["model_policy"], unique=False)
        batch_op.create_index(batch_op.f("ix_agent_model_configs_model_registry_id"), ["model_registry_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("agent_model_configs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_agent_model_configs_model_registry_id"))
        batch_op.drop_index(batch_op.f("ix_agent_model_configs_model_policy"))
        batch_op.drop_index(batch_op.f("ix_agent_model_configs_agent_name"))
    op.drop_table("agent_model_configs")
