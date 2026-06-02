"""add external access approvals table

Revision ID: 9d4a7e1b2c55
Revises: 8f3e1c2d4b7a
Create Date: 2026-03-05 16:00:00.000000

"""

from __future__ import annotations

import datetime
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9d4a7e1b2c55"
down_revision: Union[str, Sequence[str], None] = "8f3e1c2d4b7a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _parse_approval_key(value: str) -> tuple[str, str, str] | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split(":", 2)
    if len(parts) != 3:
        return None
    return parts[0], parts[1], parts[2]


def upgrade() -> None:
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
        sa.UniqueConstraint("approval_key"),
    )
    op.create_index(
        op.f("ix_external_access_approvals_approval_key"),
        "external_access_approvals",
        ["approval_key"],
        unique=False,
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

    bind = op.get_bind()
    pref_key = "security.external_access.approvals.v1"
    row = bind.execute(
        sa.text("SELECT value FROM preferences WHERE key = :key"),
        {"key": pref_key},
    ).fetchone()
    if row is None or not row.value:
        return
    try:
        payload = json.loads(row.value)
    except Exception:
        payload = []
    if not isinstance(payload, list):
        payload = []

    now = datetime.datetime.utcnow()
    for item in payload:
        parsed = _parse_approval_key(str(item))
        if parsed is None:
            continue
        resource_type, module_name, target = parsed
        bind.execute(
            sa.text(
                """
                INSERT INTO external_access_approvals (
                    approval_key,
                    resource_type,
                    module_name,
                    target,
                    approved_by,
                    created_at,
                    updated_at
                ) VALUES (
                    :approval_key,
                    :resource_type,
                    :module_name,
                    :target,
                    :approved_by,
                    :created_at,
                    :updated_at
                )
                ON CONFLICT(approval_key) DO NOTHING
                """
            ),
            {
                "approval_key": str(item),
                "resource_type": resource_type,
                "module_name": module_name,
                "target": target,
                "approved_by": None,
                "created_at": now,
                "updated_at": now,
            },
        )

    bind.execute(
        sa.text("DELETE FROM preferences WHERE key = :key"),
        {"key": pref_key},
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_external_access_approvals_module_name"), table_name="external_access_approvals")
    op.drop_index(op.f("ix_external_access_approvals_resource_type"), table_name="external_access_approvals")
    op.drop_index(op.f("ix_external_access_approvals_approval_key"), table_name="external_access_approvals")
    op.drop_table("external_access_approvals")
