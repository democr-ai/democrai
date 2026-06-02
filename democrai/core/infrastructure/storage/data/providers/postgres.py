from typing import Any
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from .base import DataStorageProvider


class PostgresDataStorage(DataStorageProvider):
    """Postgres implementation for secondary data storage."""

    def __init__(self, connection_url: str):
        self.url = connection_url
        self.engine = create_engine(self.url, pool_pre_ping=True)
        self.SessionLocal = scoped_session(
            sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        )

    def get_session(self) -> Any:
        return self.SessionLocal()

    def run_migrations(self) -> None:
        """Runs migrations for this domain."""
        from ..mixins import Base

        # For simplicity, we create tables if they don't exist.
        # In a production environment, this should use Alembic.
        Base.metadata.create_all(bind=self.engine)
