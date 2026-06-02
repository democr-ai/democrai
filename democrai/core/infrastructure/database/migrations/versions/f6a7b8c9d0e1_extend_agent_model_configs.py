"""extend agent model configs

Revision ID: f6a7b8c9d0e1
Revises: c5d6e7f8a9b0
Create Date: 2026-05-18 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("agent_model_configs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extra_tools", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("extra_skills", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("extra_mcp_servers", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("extra_agents", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("max_iterations", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("agent_model_configs", schema=None) as batch_op:
        batch_op.drop_column("max_iterations")
        batch_op.drop_column("extra_agents")
        batch_op.drop_column("extra_mcp_servers")
        batch_op.drop_column("extra_skills")
        batch_op.drop_column("extra_tools")
