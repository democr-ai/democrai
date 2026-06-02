"""merge extractor and engine heads

Revision ID: 0f1e2d3c4b5a
Revises: 4a8c1d2e3f90, f1a2b3c4d5e6
Create Date: 2026-04-14 08:12:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0f1e2d3c4b5a"
down_revision: Union[str, Sequence[str], None] = (
    "4a8c1d2e3f90",
    "f1a2b3c4d5e6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
