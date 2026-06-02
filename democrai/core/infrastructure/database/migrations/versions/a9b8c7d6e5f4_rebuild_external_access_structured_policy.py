"""rebuild external access tables with structured access policy fields

Revision ID: a9b8c7d6e5f4
Revises: d4e5f6a7b8c9
Create Date: 2026-04-27 10:30:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("external_access_approvals")
    op.drop_table("external_access_requests")
    _create_external_access_requests()
    _create_external_access_approvals()


def downgrade() -> None:
    op.drop_table("external_access_approvals")
    op.drop_table("external_access_requests")
    op.create_table(
        "external_access_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=1024), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("subject_chain", sa.JSON(), nullable=True),
        sa.Column("session_key", sa.String(length=512), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("resume_action", sa.String(length=255), nullable=True),
        sa.Column("resume_context", sa.Text(), nullable=True),
        sa.Column("resume_context_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_requested_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "request_key",
            "requested_by",
            "session_key",
            name="uq_external_access_request_per_user_session",
        ),
    )
    op.create_index(
        op.f("ix_external_access_requests_request_key"),
        "external_access_requests",
        ["request_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_access_requests_resource_type"),
        "external_access_requests",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_access_requests_module_name"),
        "external_access_requests",
        ["module_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_access_requests_requested_by"),
        "external_access_requests",
        ["requested_by"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_access_requests_session_key"),
        "external_access_requests",
        ["session_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_access_requests_status"),
        "external_access_requests",
        ["status"],
        unique=False,
    )
    op.create_table(
        "external_access_approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("approval_key", sa.String(length=1024), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_external_access_approvals_approval_key"),
        "external_access_approvals",
        ["approval_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_external_access_approvals_resource_type"),
        "external_access_approvals",
        ["resource_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_external_access_approvals_module_name"),
        "external_access_approvals",
        ["module_name"],
        unique=False,
    )


def _create_external_access_requests() -> None:
    op.create_table(
        "external_access_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_name", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("normalized_target", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("subject_chain", sa.JSON(), nullable=True),
        sa.Column("session_key", sa.String(length=512), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("resume_action", sa.String(length=255), nullable=True),
        sa.Column("resume_context", sa.Text(), nullable=True),
        sa.Column("resume_context_hash", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_requested_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_type",
            "subject_name",
            "resource_type",
            "operation",
            "normalized_target",
            "requested_by",
            "session_key",
            name="uq_external_access_request_per_user_session",
        ),
    )
    for column in (
        "subject_type",
        "subject_name",
        "resource_type",
        "operation",
        "scope",
        "requested_by",
        "session_key",
        "task_id",
        "status",
    ):
        op.create_index(
            op.f(f"ix_external_access_requests_{column}"),
            "external_access_requests",
            [column],
            unique=False,
        )


def _create_external_access_approvals() -> None:
    op.create_table(
        "external_access_approvals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_name", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("normalized_target", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("session_key", sa.String(length=512), nullable=True),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "subject_type",
            "subject_name",
            "resource_type",
            "operation",
            "normalized_target",
            "scope",
            "session_key",
            name="uq_external_access_approval_structured",
        ),
    )
    for column in (
        "subject_type",
        "subject_name",
        "resource_type",
        "operation",
        "scope",
        "session_key",
    ):
        op.create_index(
            op.f(f"ix_external_access_approvals_{column}"),
            "external_access_approvals",
            [column],
            unique=False,
        )
