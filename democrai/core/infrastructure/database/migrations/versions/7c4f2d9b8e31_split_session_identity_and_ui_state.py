"""split session identity and ui state

Revision ID: 7c4f2d9b8e31
Revises: f4f76dd35410
Create Date: 2026-02-28 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import json


revision: str = "7c4f2d9b8e31"
down_revision: Union[str, Sequence[str], None] = "f4f76dd35410"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "session_identities",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key"),
    )
    op.create_index(
        op.f("ix_session_identities_session_key"),
        "session_identities",
        ["session_key"],
        unique=False,
    )

    op.create_table(
        "session_ui_states",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_key", sa.String(length=255), nullable=False),
        sa.Column("data", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_key"),
    )
    op.create_index(
        op.f("ix_session_ui_states_session_key"),
        "session_ui_states",
        ["session_key"],
        unique=False,
    )

    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT user_key, data, updated_at FROM sessions")).fetchall()
    for row in rows:
        raw = json.loads(row.data) if row.data else {}
        identity = {"user": raw.get("user")}
        ui_state = {k: v for k, v in raw.items() if k != "user" and not str(k).startswith("_")}
        bind.execute(
            sa.text(
                """
                INSERT INTO session_identities (session_key, data, updated_at)
                VALUES (:session_key, :data, :updated_at)
                """
            ),
            {
                "session_key": row.user_key,
                "data": json.dumps(identity, default=str),
                "updated_at": row.updated_at,
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO session_ui_states (session_key, data, updated_at)
                VALUES (:session_key, :data, :updated_at)
                """
            ),
            {
                "session_key": row.user_key,
                "data": json.dumps(ui_state, default=str),
                "updated_at": row.updated_at,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    identities = {
        row.session_key: json.loads(row.data)
        for row in bind.execute(
            sa.text("SELECT session_key, data FROM session_identities")
        ).fetchall()
    }
    ui_states = {
        row.session_key: json.loads(row.data)
        for row in bind.execute(
            sa.text("SELECT session_key, data FROM session_ui_states")
        ).fetchall()
    }

    for session_key, identity in identities.items():
        merged = {}
        if isinstance(identity, dict):
            merged.update(identity)
        state = ui_states.get(session_key, {})
        if isinstance(state, dict):
            merged.update(state)
        bind.execute(
            sa.text(
                """
                UPDATE sessions
                SET data = :data
                WHERE user_key = :session_key
                """
            ),
            {"session_key": session_key, "data": json.dumps(merged, default=str)},
        )

    op.drop_index(op.f("ix_session_ui_states_session_key"), table_name="session_ui_states")
    op.drop_table("session_ui_states")
    op.drop_index(op.f("ix_session_identities_session_key"), table_name="session_identities")
    op.drop_table("session_identities")
