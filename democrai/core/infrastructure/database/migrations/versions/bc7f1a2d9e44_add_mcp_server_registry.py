"""add mcp server registry

Revision ID: bc7f1a2d9e44
Revises: 0f1e2d3c4b5a
Create Date: 2026-04-18 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "bc7f1a2d9e44"
down_revision: Union[str, Sequence[str], None] = "0f1e2d3c4b5a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRANSPORT_CHECK_NAME = "ck_mcp_server_registry_transport"


def upgrade() -> None:
    op.create_table(
        "mcp_server_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=False),
        sa.Column("config_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="15000"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint("transport = 'http'", name=_TRANSPORT_CHECK_NAME),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_mcp_server_registry_name"),
        "mcp_server_registry",
        ["name"],
        unique=True,
    )
    op.create_index(
        op.f("ix_mcp_server_registry_transport"),
        "mcp_server_registry",
        ["transport"],
        unique=False,
    )
    op.create_index(
        op.f("ix_mcp_server_registry_enabled"),
        "mcp_server_registry",
        ["enabled"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_mcp_server_registry_enabled"), table_name="mcp_server_registry")
    op.drop_index(op.f("ix_mcp_server_registry_transport"), table_name="mcp_server_registry")
    op.drop_index(op.f("ix_mcp_server_registry_name"), table_name="mcp_server_registry")
    op.drop_table("mcp_server_registry")
