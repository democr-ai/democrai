"""add organization tool links

Revision ID: d1b7a38e0c42
Revises: ca9f2d8e7b61
Create Date: 2026-05-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1b7a38e0c42"
down_revision: Union[str, Sequence[str], None] = "ca9f2d8e7b61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_tool",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("organization_id", sa.Integer(), nullable=False),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "organization_id",
            "tool_name",
            name="uq_organization_tool_organization_tool",
        ),
    )
    op.create_index(
        op.f("ix_organization_tool_organization_id"),
        "organization_tool",
        ["organization_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_organization_tool_tool_name"),
        "organization_tool",
        ["tool_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_organization_tool_tool_name"), table_name="organization_tool")
    op.drop_index(
        op.f("ix_organization_tool_organization_id"),
        table_name="organization_tool",
    )
    op.drop_table("organization_tool")
