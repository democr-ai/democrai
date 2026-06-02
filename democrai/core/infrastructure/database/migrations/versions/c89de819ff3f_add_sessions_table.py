"""add sessions table

Revision ID: c89de819ff3g
Revises: 9110114990f1
Create Date: 2026-02-16 20:14:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c89de819ff3f"
down_revision: Union[str, Sequence[str], None] = "9110114990f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_key", sa.String(length=255), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_key"),
    )
    op.create_index("ix_sessions_user_key", "sessions", ["user_key"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_sessions_user_key", "sessions")
    op.drop_table("sessions")
