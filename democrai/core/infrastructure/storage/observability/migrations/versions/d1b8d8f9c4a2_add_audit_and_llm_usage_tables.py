"""add_audit_and_ai_model_usage_tables

Revision ID: d1b8d8f9c4a2
Revises: 07f885fd6398
Create Date: 2026-03-04 15:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1b8d8f9c4a2"
down_revision: Union[str, Sequence[str], None] = "07f885fd6398"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=255), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("client_ip", sa.String(length=255), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("entity_type", sa.String(length=255), nullable=True),
        sa.Column("entity_id", sa.String(length=255), nullable=True),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.create_index("idx_audit_events_ts", ["timestamp"], unique=False)
        batch_op.create_index("idx_audit_events_actor", ["actor_user_id", "timestamp"], unique=False)
        batch_op.create_index("idx_audit_events_entity", ["entity_type", "entity_id"], unique=False)
        batch_op.create_index("idx_audit_events_request", ["request_id"], unique=False)
        batch_op.create_index("idx_audit_events_corr", ["correlation_id"], unique=False)

    op.create_table(
        "ai_model_usage_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("client_ip", sa.String(length=255), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("objective", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("engine", sa.String(length=255), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("deployment_mode", sa.String(length=32), nullable=True),
        sa.Column("request_kind", sa.String(length=64), nullable=False),
        sa.Column("agent_id", sa.String(length=255), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True),
        sa.Column("completion_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.create_index("idx_ai_model_usage_ts", ["timestamp"], unique=False)
        batch_op.create_index("idx_ai_model_usage_user", ["user_id", "timestamp"], unique=False)
        batch_op.create_index("idx_ai_model_usage_model", ["model_name", "timestamp"], unique=False)
        batch_op.create_index("idx_ai_model_usage_request", ["request_id"], unique=False)
        batch_op.create_index("idx_ai_model_usage_corr", ["correlation_id"], unique=False)

    op.create_table(
        "ai_model_runtime_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("organization_id", sa.Integer(), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("request_id", sa.String(length=255), nullable=True),
        sa.Column("correlation_id", sa.String(length=255), nullable=True),
        sa.Column("client_ip", sa.String(length=255), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=255), nullable=True),
        sa.Column("engine", sa.String(length=255), nullable=True),
        sa.Column("engine_row_id", sa.Integer(), nullable=True),
        sa.Column("model_registry_id", sa.Integer(), nullable=True),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("node_id", sa.String(length=255), nullable=True),
        sa.Column("config_signature", sa.Text(), nullable=True),
        sa.Column("warmup_ms", sa.Float(), nullable=True),
        sa.Column("model_weight_vram_mb", sa.Integer(), nullable=True),
        sa.Column("vram_before_mb", sa.Integer(), nullable=True),
        sa.Column("vram_after_mb", sa.Integer(), nullable=True),
        sa.Column("vram_delta_mb", sa.Integer(), nullable=True),
        sa.Column("runtime_allocated_vram_mb", sa.Integer(), nullable=True),
        sa.Column("ram_before_mb", sa.Integer(), nullable=True),
        sa.Column("ram_after_mb", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("ai_model_runtime_events", schema=None) as batch_op:
        batch_op.create_index("idx_ai_model_runtime_ts", ["timestamp"], unique=False)
        batch_op.create_index("idx_ai_model_runtime_model", ["model_name", "timestamp"], unique=False)
        batch_op.create_index("idx_ai_model_runtime_engine", ["engine_row_id", "timestamp"], unique=False)
        batch_op.create_index("idx_ai_model_runtime_request", ["request_id"], unique=False)
        batch_op.create_index("idx_ai_model_runtime_corr", ["correlation_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("ai_model_runtime_events", schema=None) as batch_op:
        batch_op.drop_index("idx_ai_model_runtime_corr")
        batch_op.drop_index("idx_ai_model_runtime_request")
        batch_op.drop_index("idx_ai_model_runtime_engine")
        batch_op.drop_index("idx_ai_model_runtime_model")
        batch_op.drop_index("idx_ai_model_runtime_ts")
    op.drop_table("ai_model_runtime_events")

    with op.batch_alter_table("ai_model_usage_events", schema=None) as batch_op:
        batch_op.drop_index("idx_ai_model_usage_corr")
        batch_op.drop_index("idx_ai_model_usage_request")
        batch_op.drop_index("idx_ai_model_usage_model")
        batch_op.drop_index("idx_ai_model_usage_user")
        batch_op.drop_index("idx_ai_model_usage_ts")
    op.drop_table("ai_model_usage_events")

    with op.batch_alter_table("audit_events", schema=None) as batch_op:
        batch_op.drop_index("idx_audit_events_corr")
        batch_op.drop_index("idx_audit_events_request")
        batch_op.drop_index("idx_audit_events_entity")
        batch_op.drop_index("idx_audit_events_actor")
        batch_op.drop_index("idx_audit_events_ts")
    op.drop_table("audit_events")
