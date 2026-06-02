"""Require sqlite-vec backend for local vector storage.

Revision ID: 9f2b6c1d4e11
Revises: c1e98e4ef305
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9f2b6c1d4e11"
down_revision = "c1e98e4ef305"
branch_labels = None
depends_on = None


def _assert_sqlite_vec_available() -> None:
    from democrai.core.infrastructure.storage.vector.sqlite_vec_store import sqlite_vec_available

    ok, reason = sqlite_vec_available()
    if not ok:
        raise RuntimeError(
            "sqlite-vec is required for vector storage but is unavailable: "
            f"{reason or 'unknown reason'}"
        )


def upgrade() -> None:
    _assert_sqlite_vec_available()

    op.create_table(
        "vector_backend_meta",
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("updated_at", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.execute(
        sa.text(
            "INSERT INTO vector_backend_meta (key, value, updated_at) "
            "VALUES (:k, :v, CAST(strftime('%s','now') AS INTEGER))"
        ).bindparams(k="backend", v="sqlite-vec")
    )


def downgrade() -> None:
    op.drop_table("vector_backend_meta")
