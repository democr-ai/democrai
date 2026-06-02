"""add extractor registry tables

Revision ID: 4a8c1d2e3f90
Revises: 2f6d4f9d9c31
Create Date: 2026-04-13 21:30:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4a8c1d2e3f90"
down_revision: Union[str, Sequence[str], None] = "2f6d4f9d9c31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "extractor_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("extractor_id", sa.String(length=100), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("file_extensions", sa.JSON(), nullable=False),
        sa.Column("mime_types", sa.JSON(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="uninstalled"),
        sa.Column("supported", sa.Boolean(), nullable=True, server_default=sa.true()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_extractor_registry_extractor_id"),
        "extractor_registry",
        ["extractor_id"],
        unique=False,
    )

    op.create_table(
        "extractor_node_install_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("extractor_id", sa.String(length=255), nullable=False),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("last_event_id", sa.String(length=255), nullable=True),
        sa.Column("install_started_at", sa.DateTime(), nullable=True),
        sa.Column("install_completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("manifest_version", sa.String(length=50), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extractor_id",
            "node_id",
            name="uq_extractor_node_install_registry_extractor_node",
        ),
    )
    op.create_index(
        op.f("ix_extractor_node_install_registry_extractor_id"),
        "extractor_node_install_registry",
        ["extractor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extractor_node_install_registry_node_id"),
        "extractor_node_install_registry",
        ["node_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extractor_node_install_registry_status"),
        "extractor_node_install_registry",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_extractor_node_install_registry_last_event_id"),
        "extractor_node_install_registry",
        ["last_event_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_extractor_node_install_registry_last_event_id"),
        table_name="extractor_node_install_registry",
    )
    op.drop_index(
        op.f("ix_extractor_node_install_registry_status"),
        table_name="extractor_node_install_registry",
    )
    op.drop_index(
        op.f("ix_extractor_node_install_registry_node_id"),
        table_name="extractor_node_install_registry",
    )
    op.drop_index(
        op.f("ix_extractor_node_install_registry_extractor_id"),
        table_name="extractor_node_install_registry",
    )
    op.drop_table("extractor_node_install_registry")

    op.drop_index(op.f("ix_extractor_registry_extractor_id"), table_name="extractor_registry")
    op.drop_table("extractor_registry")
