"""add engine_invocation_queue

Revision ID: 3e7a9c2b5d10
Revises: a7c9e2f4d6b8
Create Date: 2026-06-12 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3e7a9c2b5d10"
down_revision: Union[str, Sequence[str], None] = "a7c9e2f4d6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "engine_invocation_queue",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("pipeline_id", sa.String(length=64), nullable=True),
        sa.Column("selector_type", sa.String(length=32), nullable=False),
        sa.Column("model_registry_id", sa.Integer(), nullable=True),
        sa.Column("objective", sa.String(length=255), nullable=True),
        sa.Column("capabilities_json", sa.Text(), nullable=False),
        sa.Column("prefer_local", sa.Boolean(), nullable=True),
        sa.Column("confirm_swap", sa.Boolean(), nullable=False),
        sa.Column("method", sa.String(length=128), nullable=False),
        sa.Column("response_mode", sa.String(length=16), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("request_context_json", sa.Text(), nullable=False),
        sa.Column("security_context_json", sa.Text(), nullable=False),
        sa.Column("origin_node_id", sa.String(length=255), nullable=False),
        sa.Column("response_stream_key", sa.String(length=512), nullable=False),
        sa.Column("requires_origin_hitl", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(), nullable=False),
        sa.Column("lease_owner", sa.String(length=255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.Column("first_chunk_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result_summary_json", sa.Text(), nullable=True),
        sa.Column("claimed_by_node_id", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("engine_invocation_queue", schema=None) as batch_op:
        batch_op.create_index(
            "ix_engine_invocation_queue_claim",
            ["status", "available_at", "priority", "created_at"],
            unique=False,
        )
        batch_op.create_index(
            "ix_engine_invocation_queue_lease",
            ["status", "lease_expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_origin_node_id"),
            ["origin_node_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_requires_origin_hitl"),
            ["requires_origin_hitl"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_status"),
            ["status"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_available_at"),
            ["available_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_lease_owner"),
            ["lease_owner"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_lease_expires_at"),
            ["lease_expires_at"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_engine_invocation_queue_created_at"),
            ["created_at"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("engine_invocation_queue", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_created_at"))
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_lease_expires_at"))
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_lease_owner"))
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_available_at"))
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_status"))
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_requires_origin_hitl"))
        batch_op.drop_index(batch_op.f("ix_engine_invocation_queue_origin_node_id"))
        batch_op.drop_index("ix_engine_invocation_queue_lease")
        batch_op.drop_index("ix_engine_invocation_queue_claim")
    op.drop_table("engine_invocation_queue")
