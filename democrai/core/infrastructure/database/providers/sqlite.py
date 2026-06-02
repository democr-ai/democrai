import os
from typing import Any, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from alembic.config import Config
from alembic import command
from democrai.core.runtime.foundation.paths import get_data_dir, get_base_dir
from democrai.core.infrastructure.database.sqlite_tuning import install_sqlite_engine_pragmas
from democrai.core.infrastructure.database.sqlite_tuning import sqlite_connect_args
from .base import PersistenceProvider


class SqlitePersistenceProvider(PersistenceProvider):
    """SQLite implementation of PersistenceProvider."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(get_data_dir(), "democrai.db")
        self.db_path = db_path
        self.url = f"sqlite:///{db_path}"
        self.engine = create_engine(self.url, connect_args=sqlite_connect_args())
        install_sqlite_engine_pragmas(self.engine)

        self.SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        )

    def get_session(self) -> Any:
        return self.SessionLocal()

    def get_url(self) -> str:
        return self.url

    def run_migrations(self) -> None:
        from democrai.core.runtime.foundation.app import app_ctx

        base_dir = get_base_dir()
        alembic_cfg_path = os.path.join(
            base_dir, "core", "infrastructure", "database", "alembic.ini"
        )

        app_ctx().logger.info(
            f"[SqliteDB] Running migrations from {alembic_cfg_path}..."
        )

        alembic_cfg = Config(alembic_cfg_path)
        migrations_dir = os.path.join(
            base_dir, "core", "infrastructure", "database", "migrations"
        )
        alembic_cfg.set_main_option("script_location", migrations_dir)
        alembic_cfg.set_main_option("sqlalchemy.url", self.url)

        try:
            command.upgrade(alembic_cfg, "head")
            app_ctx().logger.info("[SqliteDB] Migrations completed.")
        except Exception as e:
            app_ctx().logger.error(f"[SqliteDB] Error during migrations: {e}")
            raise
