import os
from typing import Any, Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from democrai.core.infrastructure.database.sqlite_tuning import install_sqlite_engine_pragmas
from democrai.core.infrastructure.database.sqlite_tuning import sqlite_connect_args
from democrai.core.runtime.foundation.paths import get_data_dir
from .base import DataStorageProvider


class SqliteDataStorage(DataStorageProvider):
    """SQLite implementation for secondary data storage."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(get_data_dir(), "data.db")
        self.url = f"sqlite:///{db_path}"
        self.engine = create_engine(self.url, connect_args=sqlite_connect_args())
        install_sqlite_engine_pragmas(self.engine)
        self.SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        )

    def get_session(self) -> Any:
        return self.SessionLocal()

    def run_migrations(self) -> None:
        # Placeholder for data-specific migrations (using alembic if needed)
        pass
