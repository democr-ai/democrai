from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from democrai.core.infrastructure.database.sqlite_tuning import install_sqlite_engine_pragmas
from democrai.core.infrastructure.database.sqlite_tuning import sqlite_connect_args
from democrai.core.infrastructure.storage.observability.providers.base import ObsStorageProvider
from democrai.core.infrastructure.storage.observability.providers.sqlalchemy_obs_provider import (
    SQLAlchemyObsProviderMixin,
)
from democrai.core.runtime.foundation.paths import get_data_dir


class SqliteObsStorage(SQLAlchemyObsProviderMixin, ObsStorageProvider):
    """SQLite implementation for observability event storage."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(get_data_dir(), "observability.db")
        self.db_path = db_path
        self.url = f"sqlite:///{db_path}"
        self.engine = create_engine(self.url, connect_args=sqlite_connect_args())
        install_sqlite_engine_pragmas(self.engine)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def _session(self):
        session = self.SessionLocal()
        session.info["skip_observability_audit"] = True
        return session
