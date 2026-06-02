"""add organization agent and mcp links

Revision ID: ca9f2d8e7b61
Revises: 4d9e2a1b7c33
Create Date: 2026-05-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ca9f2d8e7b61"
down_revision: Union[str, Sequence[str], None] = "4d9e2a1b7c33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_agent",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "agent_name",
            name="uq_organization_agent_organization_agent",
        ),
    )
    op.create_index(
        op.f("ix_organization_agent_organization_id"),
        "organization_agent",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_agent_agent_name"),
        "organization_agent",
        ["agent_name"],
        unique=False,
    )

    op.create_table(
        "organization_mcp",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("mcp_server_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["mcp_server_id"], ["mcp_server_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "mcp_server_id",
            name="uq_organization_mcp_organization_server",
        ),
    )
    op.create_index(
        op.f("ix_organization_mcp_organization_id"),
        "organization_mcp",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_mcp_mcp_server_id"),
        "organization_mcp",
        ["mcp_server_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_organization_mcp_mcp_server_id"), table_name="organization_mcp")
    op.drop_index(op.f("ix_organization_mcp_organization_id"), table_name="organization_mcp")
    op.drop_table("organization_mcp")
    op.drop_index(op.f("ix_organization_agent_agent_name"), table_name="organization_agent")
    op.drop_index(op.f("ix_organization_agent_organization_id"), table_name="organization_agent")
    op.drop_table("organization_agent")
