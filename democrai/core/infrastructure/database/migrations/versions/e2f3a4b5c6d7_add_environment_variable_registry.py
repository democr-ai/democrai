"""add environment_variable_registry

Revision ID: e2f3a4b5c6d7
Revises: a9b8c7d6e5f4
Create Date: 2026-04-30 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op


revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "environment_variable_registry",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_kind", sa.String(length=50), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("value_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_kind",
            "subject",
            "name",
            name="uq_environment_variable_registry_subject_name",
        ),
    )
    with op.batch_alter_table("environment_variable_registry", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_environment_variable_registry_subject_kind"),
            ["subject_kind"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_environment_variable_registry_subject"),
            ["subject"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_environment_variable_registry_name"),
            ["name"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_environment_variable_registry_enabled"),
            ["enabled"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("environment_variable_registry", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_environment_variable_registry_enabled"))
        batch_op.drop_index(batch_op.f("ix_environment_variable_registry_name"))
        batch_op.drop_index(batch_op.f("ix_environment_variable_registry_subject"))
        batch_op.drop_index(batch_op.f("ix_environment_variable_registry_subject_kind"))
    op.drop_table("environment_variable_registry")
