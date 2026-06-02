"""include session_key in external_access_requests unique constraint

Revision ID: e8b1c2d3f4a5
Revises: c2f4b6a8d1e3
Create Date: 2026-04-20 21:50:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "e8b1c2d3f4a5"
down_revision: Union[str, Sequence[str], None] = "c2f4b6a8d1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("external_access_requests") as batch_op:
        batch_op.drop_constraint(
            "uq_external_access_request_per_user",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_external_access_request_per_user_session",
            ["request_key", "requested_by", "session_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("external_access_requests") as batch_op:
        batch_op.drop_constraint(
            "uq_external_access_request_per_user_session",
            type_="unique",
        )
        batch_op.create_unique_constraint(
            "uq_external_access_request_per_user",
            ["request_key", "requested_by"],
        )
