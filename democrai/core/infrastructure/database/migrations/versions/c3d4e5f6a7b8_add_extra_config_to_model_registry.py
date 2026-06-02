"""add extra_config to model_registry

Revision ID: c3d4e5f6a7b8
Revises: 5f6a7b8c9d10
Create Date: 2026-03-31 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "5f6a7b8c9d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("model_registry", schema=None) as batch_op:
        batch_op.add_column(sa.Column("extra_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("model_registry", schema=None) as batch_op:
        batch_op.drop_column("extra_config")
