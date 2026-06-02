"""per-user external access requests

Revision ID: b1c2d3e4f5a6
Revises: ab12cd34ef56
Create Date: 2026-03-25 00:00:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "ab12cd34ef56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("external_access_requests")
    op.create_table(
        "external_access_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=1024), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_requested_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key", "requested_by", name="uq_external_access_request_per_user"),
    )
    op.create_index("ix_external_access_requests_request_key", "external_access_requests", ["request_key"])
    op.create_index("ix_external_access_requests_resource_type", "external_access_requests", ["resource_type"])
    op.create_index("ix_external_access_requests_module_name", "external_access_requests", ["module_name"])
    op.create_index("ix_external_access_requests_requested_by", "external_access_requests", ["requested_by"])
    op.create_index("ix_external_access_requests_status", "external_access_requests", ["status"])


def downgrade() -> None:
    op.drop_table("external_access_requests")
    op.create_table(
        "external_access_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=1024), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_requested_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_mode", sa.String(length=32), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key"),
    )
