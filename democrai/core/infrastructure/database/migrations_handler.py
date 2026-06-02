import os
from alembic.config import Config
from alembic import command
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.app import app_ctx


def run_migrations() -> None:
    """
    Runs alembic migrations to bring the database to the latest version.
    """
    # Path to alembic.ini
    base_dir = get_base_dir()
    alembic_cfg_path = os.path.join(
        base_dir, "core", "infrastructure", "database", "alembic.ini"
    )

    app_ctx().logger.info(f"[DB] Running migrations from {alembic_cfg_path}...")

    alembic_cfg = Config(alembic_cfg_path)

    # Ensure migrations folder is found using absolute path
    migrations_dir = os.path.join(
        base_dir, "core", "infrastructure", "database", "migrations"
    )
    alembic_cfg.set_main_option("script_location", migrations_dir)

    # Also set the database URL and metadata here to be injected into env.py
    from democrai.core.infrastructure.database import get_database_url
    from democrai.core.infrastructure.database.models import Base

    db_url = get_database_url()
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Injected attributes for env.py (prevents imports in env.py)
    alembic_cfg.attributes["target_metadata"] = Base.metadata
    alembic_cfg.attributes["db_url"] = db_url

    # Run the equivalent of 'alembic upgrade head'
    try:
        command.upgrade(alembic_cfg, "head")
        app_ctx().logger.info("[DB] Migrations completed successfully.")
    except Exception as e:
        app_ctx().logger.error(f"[DB] Error during migrations: {e}")
        # In development, you might want to know more
        import traceback

        app_ctx().logger.error(traceback.format_exc())
