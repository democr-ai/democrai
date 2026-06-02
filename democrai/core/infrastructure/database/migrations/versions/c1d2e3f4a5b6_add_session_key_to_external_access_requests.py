"""add session_key to external_access_requests

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-03-25 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "external_access_requests",
        sa.Column("session_key", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_external_access_requests_session_key",
        "external_access_requests",
        ["session_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_external_access_requests_session_key", table_name="external_access_requests")
    op.drop_column("external_access_requests", "session_key")
