"""merge heads

Revision ID: 51cad5333f91
Revises: d97fd2fdedb3, e41f8298aa3d
Create Date: 2026-02-17 15:23:45.727338

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "51cad5333f91"
down_revision: Union[str, Sequence[str], None] = ("d97fd2fdedb3", "e41f8298aa3d")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
