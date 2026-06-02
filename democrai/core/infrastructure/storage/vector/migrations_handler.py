import os
from alembic.config import Config
from alembic import command
from democrai.core.runtime.foundation.app import app_ctx
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.infrastructure.storage.errors import MigrationError


def run_vector_migrations() -> None:
    """
    Runs alembic migrations for the Vector Storage database.
    """
    base_dir = get_base_dir()
    # Path to our vector-specific alembic.ini
    alembic_cfg_path = os.path.join(
        base_dir, "core", "infrastructure", "storage", "vector", "alembic.ini"
    )

    app_ctx().logger.info(f"[VECTOR DB] Running migrations from {alembic_cfg_path}...")

    alembic_cfg = Config(alembic_cfg_path)

    # Ensure migrations folder is found using absolute path
    migrations_dir = os.path.join(
        base_dir, "core", "infrastructure", "storage", "vector", "migrations"
    )
    alembic_cfg.set_main_option("script_location", migrations_dir)

    # Set the database URL and metadata dynamically, injecting them into context
    from democrai.core.infrastructure.storage.vector.models import Base
    from democrai.core.runtime.foundation.paths import get_data_dir

    db_path = os.path.join(get_data_dir(), "vector.db")
    database_url = f"sqlite:///{db_path}"
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    # Injected attributes for env.py (prevents imports in env.py)
    alembic_cfg.attributes["target_metadata"] = Base.metadata
    alembic_cfg.attributes["db_url"] = database_url

    # Run the equivalent of 'alembic upgrade head'
    try:
        command.upgrade(alembic_cfg, "head")
        app_ctx().logger.info("[VECTOR DB] Migrations completed successfully.")
    except Exception as e:
        app_ctx().logger.error(f"[VECTOR DB] Error during migrations: {e}")
        raise MigrationError(f"Vector migrations failed: {e}") from e
