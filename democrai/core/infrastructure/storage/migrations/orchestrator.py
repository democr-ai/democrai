from __future__ import annotations

from democrai.core.infrastructure.storage.data.migrations_handler import run_data_migrations
from democrai.core.infrastructure.storage.observability.migrations_handler import run_obs_migrations
from democrai.core.infrastructure.storage.vector.migrations_handler import run_vector_migrations
from democrai.core.infrastructure.storage.errors import MigrationError


def run_storage_migrations(ctx) -> None:
    """
    Run storage-domain migrations in deterministic order.
    """
    try:
        ctx.kg_store.run_migrations()
        run_vector_migrations()
        run_data_migrations()
        run_obs_migrations()
    except Exception as exc:
        raise MigrationError(f"Storage migrations failed: {exc}") from exc
