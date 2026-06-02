"""allow direct mcp transport

Revision ID: c7d8e9f01234
Revises: b6c7d8e9f012
Create Date: 2026-05-13 10:05:00.000000

"""

from typing import Sequence, Union

from alembic import op


revision: str = "c7d8e9f01234"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TRANSPORT_CHECK_NAME = "ck_mcp_server_registry_transport"


def upgrade() -> None:
    if op.get_context().dialect.name == "postgresql":
        op.drop_constraint(
            _TRANSPORT_CHECK_NAME,
            "mcp_server_registry",
            type_="check",
        )
        op.create_check_constraint(
            _TRANSPORT_CHECK_NAME,
            "mcp_server_registry",
            "transport IN ('http', 'direct')",
        )
        return

    with op.batch_alter_table("mcp_server_registry") as batch_op:
        batch_op.drop_constraint(_TRANSPORT_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(
            _TRANSPORT_CHECK_NAME,
            "transport IN ('http', 'direct')",
        )


def downgrade() -> None:
    op.execute("UPDATE mcp_server_registry SET transport = 'http' WHERE transport = 'direct'")
    if op.get_context().dialect.name == "postgresql":
        op.drop_constraint(
            _TRANSPORT_CHECK_NAME,
            "mcp_server_registry",
            type_="check",
        )
        op.create_check_constraint(
            _TRANSPORT_CHECK_NAME,
            "mcp_server_registry",
            "transport = 'http'",
        )
        return

    with op.batch_alter_table("mcp_server_registry") as batch_op:
        batch_op.drop_constraint(_TRANSPORT_CHECK_NAME, type_="check")
        batch_op.create_check_constraint(
            _TRANSPORT_CHECK_NAME,
            "transport = 'http'",
        )
