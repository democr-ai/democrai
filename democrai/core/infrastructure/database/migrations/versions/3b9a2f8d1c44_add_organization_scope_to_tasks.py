"""add organization scope to background tasks and notifications

Revision ID: 3b9a2f8d1c44
Revises: 2f6d4f9d9c31
Create Date: 2026-03-02 18:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b9a2f8d1c44"
down_revision: Union[str, Sequence[str], None] = "2f6d4f9d9c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("background_tasks") as batch_op:
        batch_op.add_column(
            sa.Column(
                "organization_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_index(
            "ix_background_tasks_organization_id", ["organization_id"], unique=False
        )

    with op.batch_alter_table("pending_notifications") as batch_op:
        batch_op.add_column(
            sa.Column(
                "organization_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_index(
            "ix_pending_notifications_organization_id", ["organization_id"], unique=False
        )


def downgrade() -> None:
    with op.batch_alter_table("pending_notifications") as batch_op:
        batch_op.drop_index("ix_pending_notifications_organization_id")
        batch_op.drop_column("organization_id")

    with op.batch_alter_table("background_tasks") as batch_op:
        batch_op.drop_index("ix_background_tasks_organization_id")
        batch_op.drop_column("organization_id")
