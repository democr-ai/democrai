"""add available model registry

Revision ID: 1c7e4a9d2b11
Revises: bc7f1a2d9e44
Create Date: 2026-04-19 18:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1c7e4a9d2b11"
down_revision: Union[str, Sequence[str], None] = "bc7f1a2d9e44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "available_model_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("catalog_model_id", sa.String(length=255), nullable=True),
        sa.Column("source_kind", sa.String(length=50), nullable=False),
        sa.Column("provider_hint", sa.String(length=100), nullable=True),
        sa.Column("format", sa.String(length=100), nullable=True),
        sa.Column("family", sa.String(length=100), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("storage_ref", sa.String(length=512), nullable=True),
        sa.Column("remote_url", sa.String(length=512), nullable=True),
        sa.Column("version", sa.String(length=100), nullable=True),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("extended_capabilities", sa.Text(), nullable=True),
        sa.Column("interfaces", sa.Text(), nullable=True),
        sa.Column("tags", sa.Text(), nullable=True),
        sa.Column("requirements", sa.JSON(), nullable=True),
        sa.Column("artifacts", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("source_payload", sa.JSON(), nullable=True),
        sa.Column("extra_config", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "ix_available_model_registry_catalog_model_id",
        "available_model_registry",
        ["catalog_model_id"],
        unique=False,
    )
    op.create_index(
        "ix_available_model_registry_format",
        "available_model_registry",
        ["format"],
        unique=False,
    )
    op.create_index(
        "ix_available_model_registry_name",
        "available_model_registry",
        ["name"],
        unique=False,
    )
    op.create_index(
        "ix_available_model_registry_provider_hint",
        "available_model_registry",
        ["provider_hint"],
        unique=False,
    )
    op.create_index(
        "ix_available_model_registry_status",
        "available_model_registry",
        ["status"],
        unique=False,
    )

    with op.batch_alter_table("model_registry", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("available_model_id", sa.Integer(), nullable=True)
        )
        batch_op.create_index(
            "ix_model_registry_available_model_id",
            ["available_model_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_model_registry_available_model_id",
            "available_model_registry",
            ["available_model_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("model_registry", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_model_registry_available_model_id",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_model_registry_available_model_id")
        batch_op.drop_column("available_model_id")

    op.drop_index("ix_available_model_registry_status", table_name="available_model_registry")
    op.drop_index("ix_available_model_registry_provider_hint", table_name="available_model_registry")
    op.drop_index("ix_available_model_registry_name", table_name="available_model_registry")
    op.drop_index("ix_available_model_registry_format", table_name="available_model_registry")
    op.drop_index("ix_available_model_registry_catalog_model_id", table_name="available_model_registry")
    op.drop_table("available_model_registry")
