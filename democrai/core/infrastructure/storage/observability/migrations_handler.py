import os
from alembic.config import Config
from alembic import command
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.infrastructure.storage.errors import MigrationError


def run_obs_migrations() -> None:
    """
    Runs Alembic migrations for the observability database.
    """
    provider_type = str(
        app_ctx().config.get("storage.observability.type", "sqlite")
    ).strip().lower()
    if provider_type == "clickhouse":
        from democrai.core.infrastructure.storage.observability.providers.clickhouse import (
            ClickHouseObsStorage,
        )

        url = app_ctx().config.get("storage.observability.url")
        try:
            ClickHouseObsStorage(url).run_migrations()
            return
        except Exception as e:
            app_ctx().logger.error(f"[Obs DB] Error during ClickHouse bootstrap: {e}")
            raise MigrationError(f"Observability migrations failed: {e}") from e

    # Path to the observability directory
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ini_path = os.path.join(base_dir, "alembic.ini")

    # Configuration for the observability database migration
    alembic_cfg = Config(ini_path)

    # Set DB URL and metadata for injection
    from democrai.core.infrastructure.storage.observability.models import Base
    from democrai.core.runtime.foundation.paths import get_data_dir as get_app_data_dir

    db_url = app_ctx().config.get("storage.observability.url")
    if not db_url:
        db_path = os.path.join(get_app_data_dir(), "observability.db")
        db_url = f"sqlite:///{db_path}"
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Injected attributes for env.py (prevents imports in env.py)
    alembic_cfg.attributes["target_metadata"] = Base.metadata
    alembic_cfg.attributes["db_url"] = db_url

    # Run the migration
    app_ctx().logger.info(f"[Obs DB] Running migrations from {ini_path}...")
    try:
        command.upgrade(alembic_cfg, "head")
        app_ctx().logger.info("[Obs DB] Migrations completed successfully.")
    except Exception as e:
        app_ctx().logger.error(f"[Obs DB] Error during migrations: {e}")
        raise MigrationError(f"Observability migrations failed: {e}") from e
