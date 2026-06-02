"""add subject_chain to external_access_requests

Revision ID: c2f4b6a8d1e3
Revises: 1c7e4a9d2b11
Create Date: 2026-04-20 18:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c2f4b6a8d1e3"
down_revision: Union[str, Sequence[str], None] = "1c7e4a9d2b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_access_requests",
        sa.Column("subject_chain", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("external_access_requests", "subject_chain")
