"""add model capability priority table

Revision ID: 5f6a7b8c9d10
Revises: 363272cf7eb6
Create Date: 2026-03-29 20:40:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5f6a7b8c9d10"
down_revision: Union[str, Sequence[str], None] = "363272cf7eb6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "model_capability_priority",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("capability", sa.String(length=100), nullable=False),
        sa.Column("model_id", sa.Integer(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["model_id"], ["model_registry.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("capability", "model_id", name="uq_capability_model_priority"),
        sa.UniqueConstraint("capability", "priority", name="uq_capability_priority_rank"),
    )
    with op.batch_alter_table("model_capability_priority", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_model_capability_priority_capability"), ["capability"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_model_capability_priority_model_id"), ["model_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_model_capability_priority_priority"), ["priority"], unique=False
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("model_capability_priority", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_model_capability_priority_priority"))
        batch_op.drop_index(batch_op.f("ix_model_capability_priority_model_id"))
        batch_op.drop_index(batch_op.f("ix_model_capability_priority_capability"))

    op.drop_table("model_capability_priority")
