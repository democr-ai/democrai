"""create background_tasks table

Revision ID: e41f8298aa3d
Revises: c89de819ff3g
Create Date: 2026-02-17 15:08:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "e41f8298aa3d"
down_revision = "c89de819ff3f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "background_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("module", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("checkpoint", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_background_tasks_user_id"),
        "background_tasks",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "pending_notifications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("delivered", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pending_notifications_user_id"),
        "pending_notifications",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_pending_notifications_user_id"), table_name="pending_notifications"
    )
    op.drop_table("pending_notifications")
    op.drop_index(op.f("ix_background_tasks_user_id"), table_name="background_tasks")
    op.drop_table("background_tasks")
