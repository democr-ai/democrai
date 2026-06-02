"""add external access resume metadata

Revision ID: d4e5f6a7b8c9
Revises: e8b1c2d3f4a5
Create Date: 2026-04-26 14:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "e8b1c2d3f4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_access_requests",
        sa.Column("resume_action", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "external_access_requests",
        sa.Column("resume_context", sa.Text(), nullable=True),
    )
    op.add_column(
        "external_access_requests",
        sa.Column("resume_context_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("external_access_requests", "resume_context_hash")
    op.drop_column("external_access_requests", "resume_context")
    op.drop_column("external_access_requests", "resume_action")
