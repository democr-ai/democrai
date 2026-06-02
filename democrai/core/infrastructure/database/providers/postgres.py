import os
from typing import Any
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from .base import PersistenceProvider
from democrai.core.runtime.foundation.paths import get_base_dir
from democrai.core.runtime.foundation.app import app_ctx


class PostgresPersistenceProvider(PersistenceProvider):
    """PostgreSQL implementation of PersistenceProvider."""

    def __init__(self, db_url: str):
        self.url = db_url
        self.engine = create_engine(self.url, pool_pre_ping=True)
        self.SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        )

    def get_session(self) -> Any:
        return self.SessionLocal()

    def get_url(self) -> str:
        return self.url

    def run_migrations(self) -> None:
        base_dir = get_base_dir()
        alembic_cfg_path = os.path.join(
            base_dir, "core", "infrastructure", "database", "alembic.ini"
        )

        app_ctx().logger.info(
            f"[Postgres] Running migrations from {alembic_cfg_path}..."
        )

        alembic_cfg = Config(alembic_cfg_path)
        migrations_dir = os.path.join(
            base_dir, "core", "infrastructure", "database", "migrations"
        )
        alembic_cfg.set_main_option("script_location", migrations_dir)
        alembic_cfg.set_main_option("sqlalchemy.url", self.url)

        from democrai.core.infrastructure.database.models import Base

        alembic_cfg.attributes["target_metadata"] = Base.metadata
        alembic_cfg.attributes["db_url"] = self.url

        try:
            command.upgrade(alembic_cfg, "head")
            app_ctx().logger.info("[Postgres] Migrations completed successfully.")
        except Exception as e:
            app_ctx().logger.error(f"[Postgres] Error during migrations: {e}")
            
            import traceback

            app_ctx().logger.error(traceback.format_exc())
            raise Exception(f"Database migration failed: {e}")
