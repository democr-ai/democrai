from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from democrai.core.infrastructure.database.models import Base
from democrai.core.runtime.foundation.paths import get_base_dir


def _alembic_config(db_url: str) -> Config:
    base_dir = get_base_dir()
    cfg = Config(
        os.path.join(base_dir, "core", "infrastructure", "database", "alembic.ini")
    )
    cfg.set_main_option(
        "script_location",
        os.path.join(base_dir, "core", "infrastructure", "database", "migrations"),
    )
    cfg.set_main_option("sqlalchemy.url", db_url)
    cfg.attributes["target_metadata"] = Base.metadata
    cfg.attributes["db_url"] = db_url
    return cfg


def test_upgrade_head_creates_cluster_tables(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    command.upgrade(_alembic_config(db_url), "head")

    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert "engine_invocation_queue" in tables
    assert "engine_node_instance_registry" in tables

    queue_columns = {
        column["name"] for column in inspector.get_columns("engine_invocation_queue")
    }
    assert {
        "id",
        "selector_type",
        "method",
        "response_mode",
        "origin_node_id",
        "response_stream_key",
        "requires_origin_hitl",
        "status",
        "available_at",
        "lease_owner",
        "lease_expires_at",
        "cancel_requested",
        "first_chunk_at",
    } <= queue_columns

    node_columns = {
        column["name"] for column in inspector.get_columns("runtime_node_registry")
    }
    assert {
        "orchestrator_last_seen_at",
        "cpu_percent",
        "ram_total_mb",
        "ram_free_mb",
        "vram_total_mb",
        "vram_free_mb",
        "gpu_inventory_json",
        "resources_updated_at",
    } <= node_columns

    queue_indexes = {
        index["name"] for index in inspector.get_indexes("engine_invocation_queue")
    }
    assert "ix_engine_invocation_queue_claim" in queue_indexes
    assert "ix_engine_invocation_queue_lease" in queue_indexes
    engine.dispose()


def test_cluster_migrations_downgrade(tmp_path):
    db_url = f"sqlite:///{tmp_path / 'migrations.db'}"
    cfg = _alembic_config(db_url)
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "a7c9e2f4d6b8")

    engine = sa.create_engine(db_url)
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert "engine_invocation_queue" not in tables
    assert "engine_node_instance_registry" not in tables
    node_columns = {
        column["name"] for column in inspector.get_columns("runtime_node_registry")
    }
    assert "orchestrator_last_seen_at" not in node_columns
    engine.dispose()
