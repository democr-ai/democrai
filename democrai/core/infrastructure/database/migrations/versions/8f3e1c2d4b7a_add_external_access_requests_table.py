"""add external access requests table

Revision ID: 8f3e1c2d4b7a
Revises: 6c2d3ef4a1b1
Create Date: 2026-03-05 14:30:00.000000

"""

from __future__ import annotations

import datetime
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f3e1c2d4b7a"
down_revision: Union[str, Sequence[str], None] = "6c2d3ef4a1b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _as_int(value) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None


def _as_datetime(value) -> datetime.datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return datetime.datetime.utcfromtimestamp(float(value))
    return None


def upgrade() -> None:
    op.create_table(
        "external_access_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("request_key", sa.String(length=1024), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("module_name", sa.String(length=255), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("request_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_requested_at", sa.DateTime(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_mode", sa.String(length=32), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_key"),
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
        op.f("ix_external_access_requests_status"),
        "external_access_requests",
        ["status"],
        unique=False,
    )

    bind = op.get_bind()
    pref_key = "security.external_access.pending_requests.v1"
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
        if not isinstance(item, dict):
            continue
        request_key = str(item.get("request_key") or "").strip()
        if not request_key:
            continue
        bind.execute(
            sa.text(
                """
                INSERT INTO external_access_requests (
                    request_key,
                    resource_type,
                    module_name,
                    target,
                    requested_by,
                    organization_id,
                    status,
                    request_count,
                    created_at,
                    last_requested_at,
                    approved_by,
                    approved_mode,
                    approved_at,
                    updated_at
                ) VALUES (
                    :request_key,
                    :resource_type,
                    :module_name,
                    :target,
                    :requested_by,
                    :organization_id,
                    :status,
                    :request_count,
                    :created_at,
                    :last_requested_at,
                    :approved_by,
                    :approved_mode,
                    :approved_at,
                    :updated_at
                )
                ON CONFLICT(request_key) DO NOTHING
                """
            ),
            {
                "request_key": request_key,
                "resource_type": str(item.get("resource_type") or ""),
                "module_name": str(item.get("module_name") or ""),
                "target": str(item.get("target") or ""),
                "requested_by": _as_int(item.get("requested_by")),
                "organization_id": _as_int(item.get("organization_id")),
                "status": str(item.get("status") or "pending"),
                "request_count": int(item.get("request_count") or 1),
                "created_at": _as_datetime(item.get("created_at")) or now,
                "last_requested_at": _as_datetime(item.get("last_requested_at")) or now,
                "approved_by": _as_int(item.get("approved_by")),
                "approved_mode": str(item.get("approved_mode") or ""),
                "approved_at": _as_datetime(item.get("approved_at")),
                "updated_at": now,
            },
        )

    bind.execute(
        sa.text("DELETE FROM preferences WHERE key = :key"),
        {"key": pref_key},
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_external_access_requests_status"), table_name="external_access_requests")
    op.drop_index(op.f("ix_external_access_requests_module_name"), table_name="external_access_requests")
    op.drop_index(op.f("ix_external_access_requests_resource_type"), table_name="external_access_requests")
    op.drop_index(op.f("ix_external_access_requests_request_key"), table_name="external_access_requests")
    op.drop_table("external_access_requests")
