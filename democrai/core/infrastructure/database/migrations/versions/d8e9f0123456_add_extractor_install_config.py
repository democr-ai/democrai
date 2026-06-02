"""add extractor install config

Revision ID: d8e9f0123456
Revises: c7d8e9f01234
Create Date: 2026-05-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e9f0123456"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f01234"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "extractor_registry",
        sa.Column("install_config", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("extractor_registry", "install_config")
